"""Exercise actual assembled PPC: normal reply, timeout and late callback races."""
import json
import struct
import unittest
from pathlib import Path
from kwce.channel_ipc_deadline import code,patch
from kwce.ppc_patch import to_file


def signed(v,bits=32):
    return v-(1<<bits) if v&(1<<(bits-1)) else v


class Machine:
    def __init__(self,row,native_ioctls=(),long_ioctls=()):
        self.row=row;self.blob,self.labels=code(row,polls=3,native_ioctls=native_ioctls,long_ioctls=long_ioctls)
        self.base=self.labels['ioctl'];self.mem={self.base+i:b for i,b in enumerate(self.blob)}
        self.r=[0]*32;self.r[1]=0x81700000;self.r[24:]=range(24,32)
        self.cr=[False]*32;self.lr=0;self.polls=0;self.io=None;self.close=None
        self.reply_at=1;self.result=0;self.enqueue=0;self.close_enqueue=0
        self.calls={int(row[k],16):k for k in ('ioctl_async','close_async','disable','restore','sleep')}
        self.native=False;self.output=0x81601000
        self.write(0x800000f8,243000000)
    def read(self,a):return int.from_bytes(bytes(self.mem.get(a+i,0)for i in range(4)),'big')
    def write(self,a,v):
        for i,b in enumerate(struct.pack('>I',v&0xffffffff)):self.mem[a+i]=b
    def bytes(self,a,n):return bytes(self.mem.get(a+i,0)for i in range(n))
    def invoke_callback(self,call,result):
        # IOS callback execution preserves the interrupted thread's context.
        saved=(self.r[:],self.cr[:],self.lr)
        self.r[3]=result&0xffffffff;self.r[4]=call['context']
        self.run(call['callback']);self.r,self.cr,self.lr=saved
    def reply(self):
        if not self.io:return
        call=self.io
        for i in range(call['size']):self.mem[call['output']+i]=(i*3+7)&255
        self.invoke_callback(call,self.result)
    def sdk(self,name):
        if name=='disable':self.r[3]=1
        elif name=='restore':self.r[3]=1
        elif name=='sleep':
            self.polls+=1
            if self.reply_at==self.polls:self.reply()
            self.r[3]=0
        elif name=='ioctl_async':
            self.io=dict(fd=self.r[3],command=self.r[4],input=self.r[5],input_size=self.r[6],
                         output=self.r[7],size=self.r[8],callback=self.r[9],context=self.r[10])
            self.r[3]=self.enqueue&0xffffffff
        elif name=='close_async':
            self.close=dict(fd=self.r[3],callback=self.r[4],context=self.r[5]);self.r[3]=self.close_enqueue&0xffffffff
        # SDK routines may destroy caller-volatile registers.
        for i in range(4,13):self.r[i]=0xdead0000+i
    def call(self,input_size=32,output_size=32,command=14):
        self.r[3:10]=[0,17,command,0x81600000,input_size,self.output,output_size]
        for i in range(32):self.mem[0x81600000+i]=i
        return self.run(self.labels['ioctl'])
    def call_close(self,fd=17):
        self.r[3:5]=[0,fd];return self.run(self.labels['close'])
    def run(self,start):
        pc=start;self.lr=0x81000000
        for _ in range(100000):
            if not self.base<=pc<self.base+len(self.blob):return pc
            w=self.read(pc);op=w>>26;rt=w>>21&31;ra=w>>16&31;rb=w>>11&31
            imm=signed(w&65535,16);nxt=pc+4
            if op in (14,15):self.r[rt]=((self.r[ra]if ra else 0)+(imm<<(16 if op==15 else 0)))&0xffffffff
            elif op==7:self.r[rt]=(self.r[ra]*imm)&0xffffffff
            elif op==24:self.r[ra]=self.r[rt]|(w&65535)
            elif op in (32,34,36,37,38):
                a=((self.r[ra]if ra else 0)+imm)&0xffffffff
                if op==32:self.r[rt]=self.read(a)
                elif op==34:self.r[rt]=self.mem.get(a,0)
                elif op==38:self.mem[a]=self.r[rt]&255
                else:self.write(a,self.r[rt])
                if op==37:self.r[ra]=a
            elif op in (46,47):
                a=(self.r[ra]+imm)&0xffffffff
                for reg in range(rt,32):
                    if op==46:self.r[reg]=self.read(a)
                    else:self.write(a,self.r[reg])
                    a+=4
            elif op in (10,11):
                a,b=self.r[ra],w&65535
                if op==11:a,b=signed(a),imm
                self.cr[:3]=[a<b,a>b,a==b]
            elif op==16:
                assert rt in (4,12)
                if self.cr[ra]==(rt==12):nxt=pc+signed(w&0xfffc,16)
            elif op==18:
                target=pc+signed(w&0x3fffffc,26)
                if w&1:self.lr=pc+4
                if target in self.calls:self.sdk(self.calls[target])
                else:nxt=target
            elif op==19 and (w>>1)&1023==16:nxt=self.lr
            elif op==21:
                sh=w>>11&31;mb=w>>6&31;me=w>>1&31
                v=((self.r[rt]<<sh)|(self.r[rt]>>(32-sh if sh else 32)))&0xffffffff
                mask=sum(1<<(31-i)for i in range(32)if (mb<=i<=me if mb<=me else i>=mb or i<=me))
                self.r[ra]=v&mask
            elif op==31:
                xo=w>>1&1023
                if xo==339:self.r[rt]=self.lr
                elif xo==467:self.lr=self.r[rt]
                elif xo==444:self.r[ra]=self.r[rt]|self.r[rb]
                elif xo==11:self.r[rt]=(self.r[ra]*self.r[rb]>>32)&0xffffffff
                elif xo in (0,32):
                    a,b=self.r[ra],self.r[rb]
                    if xo==0:a,b=signed(a),signed(b)
                    self.cr[:3]=[a<b,a>b,a==b]
                else:raise AssertionError(f'Unexpected extended opcode {xo}')
            else:raise AssertionError(f'Unexpected opcode {op}')
            pc=nxt
        raise AssertionError('Adapter failed to return')


class ChannelIpcCodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rows=json.loads(Path('configs/channel-ipc-deadline-v1.lock.json').read_text())['channels']
    def test_real_code_preserves_normal_data_abi_and_registers(self):
        for row in self.rows.values():
            for size in (0,32,256):
                m=Machine(row);sp=m.r[1];regs=m.r[24:];m.call(output_size=size)
                self.assertEqual(signed(m.r[3]),0);self.assertEqual(m.r[1],sp);self.assertEqual(m.r[24:],regs)
                self.assertEqual(m.bytes(m.output,size),bytes((i*3+7)&255 for i in range(size)))
                self.assertEqual(m.bytes(m.io['input'],32),bytes(range(32)))
                self.assertNotEqual(m.io['input'],0x81600000);self.assertNotEqual(m.io['output'],m.output)
                self.assertEqual(m.io['input']%32,0);self.assertEqual(m.io['output']%32,0)
    def test_timeout_never_copies_out_and_late_callbacks_both_orders(self):
        for row in self.rows.values():
            for close_first in (False,True):
                m=Machine(row);m.reply_at=None;m.call();s=m.labels['state']
                self.assertEqual(signed(m.r[3]),-42);self.assertEqual(m.polls,3);self.assertEqual(m.read(s),1)
                self.assertEqual(m.bytes(m.output,32),bytes(32))
                m.call_close();self.assertEqual(signed(m.r[3]),0)
                if close_first:m.invoke_callback(m.close,0)
                else:m.reply()
                self.assertEqual(m.read(s),1)
                if close_first:m.reply()
                else:m.invoke_callback(m.close,0)
                self.assertEqual(m.read(s),0);self.assertEqual(m.bytes(m.output,32),bytes(32))
    def test_timeout_occupied_slot_is_not_reused(self):
        for row in self.rows.values():
            m=Machine(row);m.reply_at=None;m.call();first=m.io.copy();m.call()
            self.assertEqual(signed(m.r[3]),-42);self.assertEqual(m.io,first)
            self.assertEqual(m.call_close(fd=18),int(row['close'],16)+4)
    def test_errors_do_not_report_success_or_copy_result(self):
        for row in self.rows.values():
            for result,enqueued in ((-6,0),(0,-22)):
                m=Machine(row);m.result=result;m.enqueue=enqueued;m.call()
                self.assertEqual(signed(m.r[3]),-42);self.assertEqual(m.read(m.labels['state']),0)
                self.assertEqual(m.bytes(m.output,32),bytes(32))
    def test_large_requests_keep_original_native_path(self):
        for row in self.rows.values():
            for ins,outs in ((33,32),(32,257)):
                m=Machine(row);self.assertEqual(m.call(ins,outs),int(row['ioctl'],16)+4);self.assertIsNone(m.io)
    def test_exempt_ioctl_routes_native_and_others_stay_bounded(self):
        # News error 107242: the download (ioctl 14) is small but slow, so the
        # 30s cap wrongly bounds it. Exempting it must send ONLY that command to
        # the native retail path, while every other small ioctl stays bounded.
        for row in self.rows.values():
            m=Machine(row,native_ioctls=[14])
            self.assertEqual(m.call(command=14),int(row['ioctl'],16)+4)
            self.assertIsNone(m.io);self.assertEqual(m.polls,0)
            m=Machine(row,native_ioctls=[14]);m.call(command=13)
            self.assertEqual(signed(m.r[3]),0);self.assertIsNotNone(m.io);self.assertEqual(m.io['command'],13)
            m=Machine(row);m.call(command=14)
            self.assertEqual(signed(m.r[3]),0);self.assertIsNotNone(m.io)
    def test_long_ioctl_gets_its_own_finite_bound(self):
        # News v24: the download (ioctl 14) keeps a bound, but a longer one (10 min on hardware);
        # a stalled download must still end in -42 (107242), never wait forever like v23.
        for row in self.rows.values():
            m=Machine(row,long_ioctls=[(14,7)]);m.reply_at=None;m.call(command=14)
            self.assertEqual(signed(m.r[3]),-42);self.assertEqual(m.polls,7)
            m=Machine(row,long_ioctls=[(14,7)]);m.reply_at=None;m.call(command=13)
            self.assertEqual(signed(m.r[3]),-42);self.assertEqual(m.polls,3)
            m=Machine(row,long_ioctls=[(14,7)]);m.call(command=14)
            self.assertEqual(signed(m.r[3]),0);self.assertIsNotNone(m.io)
    def test_several_long_ioctls_each_get_the_long_bound(self):
        # News v25: KD ioctl 6 (StartupSocket; 050330 when cut at 30 s), 14 (DownloadNowEx) and
        # 30 (scheduler status) all get the long finite bound; any other small ioctl keeps 3 polls.
        longs=[(6,7),(14,7),(30,7)]
        for row in self.rows.values():
            for command in (6,14,30):
                m=Machine(row,long_ioctls=longs);m.reply_at=None;m.call(command=command)
                self.assertEqual(signed(m.r[3]),-42);self.assertEqual(m.polls,7)
                m=Machine(row,long_ioctls=longs);m.call(command=command)
                self.assertEqual(signed(m.r[3]),0);self.assertIsNotNone(m.io)
            for command in (5,13,29,31):
                m=Machine(row,long_ioctls=longs);m.reply_at=None;m.call(command=command)
                self.assertEqual(signed(m.r[3]),-42);self.assertEqual(m.polls,3)
    def test_failed_close_retains_buffer_ownership(self):
        for row in self.rows.values():
            m=Machine(row);m.reply_at=None;m.call();m.call_close();m.reply();m.invoke_callback(m.close,-6)
            self.assertEqual(m.read(m.labels['state']),1)

class ChannelIpcArtifacts(unittest.TestCase):
    def test_shipped_executable_reproduction_and_other_contents_preserved(self):
        from kwce.channels import load_library
        from kwce.channel_socket_startup import patch as socket_patch
        from kwce.wiiroom_formats import decompress_lz11
        for channel,oldv,newv,name,count in [('news',16,20,'news-ko-personal.wad',12),('wiiroom',47,51,'wiiroom-ko-local-test.wad',16)]:
            base=Path('workspace/channels')/channel
            if not (base/f'build-v{newv}'/name).exists():self.skipTest('Private built channels required')
            lib=load_library();old,new=lib.title.Title(),lib.title.Title()
            old.load_wad((base/f'build-v{oldv}'/name).read_bytes());new.load_wad((base/f'build-v{newv}'/name).read_bytes())
            self.assertEqual([i for i in range(count)if old.get_content_by_index(i)!=new.get_content_by_index(i)],[1])
            a,b=old.get_content_by_index(1),new.get_content_by_index(1)
            if channel=='wiiroom':a,b=decompress_lz11(a),decompress_lz11(b)
            prepared=socket_patch(a,channel)[0]
            self.assertEqual(patch(prepared,channel)[0],b)
            row=json.loads(Path('configs/channel-ipc-deadline-v1.lock.json').read_text())['channels'][channel]
            corrupt=bytearray(prepared);corrupt[to_file(prepared,int(row['ioctl_async'],16))]^=1
            with self.assertRaises(ValueError):patch(bytes(corrupt),channel)


if __name__=='__main__':unittest.main()

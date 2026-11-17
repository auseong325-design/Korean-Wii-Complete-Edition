"""Read local native HOME sound bank/sequences and render deterministic UI PCM.

Format definitions: the pinned wii-ipl NW4R SoundArchiveFile/BankFile/WaveFile
and MmlParser sources. Only HOME sound IDs 0..21 are read. No console data,
network or other music/sound assets are used or exported.
"""
import array,hashlib,math,struct

class HomeSounds:
    def __init__(self,data):
        self.d=data;self.base=self.u(0x18)+8;self.waves={}
        if data[:4]!=b'RSAR':raise ValueError('Expected native UI RSAR')
    def u(self,at):return struct.unpack_from('>I',self.d,at)[0]
    def ref(self,at,base=None):
        if self.d[at]!=1:raise ValueError('Expected relative native sound reference')
        return (self.base if base is None else base)+self.u(at+4)
    def table(self,field,index):
        t=self.ref(self.base+field)
        if index>=self.u(t):raise ValueError('UI sound table bounds')
        return self.ref(t+4+index*8)
    def file(self,index):
        f=self.table(24,index);positions=self.ref(f+20);position=self.ref(positions+4)
        g=self.table(32,self.u(position));items=self.ref(g+32);item=self.ref(items+4+self.u(position+4)*8)
        return self.u(g+16)+self.u(item+4),self.u(g+24)+self.u(item+12)
    def instrument(self,bank,program):
        b=self.table(8,bank);f,wave=self.file(self.u(b+4));base=f+self.u(f+16)+8
        if self.d[f:f+4]!=b'RBNK' or program>=self.u(base):raise ValueError('HOME instrument bounds')
        at=base+4+program*8
        if self.d[at+1]!=1:raise ValueError('HOME instrument requires unsupported region selection')
        p=self.ref(at,base);return f,wave,p
    def samples(self,bank,program):
        key=(bank,program)
        if key in self.waves:return self.waves[key]
        f,wave,p=self.instrument(bank,program);index=self.u(p);base=f+self.u(f+24)+8
        if index>=self.u(base):raise ValueError('HOME wave bounds')
        wi=self.ref(base+4+index*8,base);fmt,loop,channels,hi=self.d[wi:wi+4]
        rate=(hi<<16)|struct.unpack_from('>H',self.d,wi+4)[0];start,end=self.u(wi+8),self.u(wi+12)
        # NW4R stores DSP nibble addresses, not PCM frame counts (WaveFileReader).
        if fmt==2:
            start=(start//16)*14+start%16-2;end=(end//16)*14+end%16-2
        end+=1
        if not 8000<=rate<=96000 or channels not in (1,2) or end>rate*10:raise ValueError('Unreviewed HOME wave parameters')
        decoded=[]
        for channel in range(channels):
            ci=wi+self.u(wi+self.u(wi+16)+4*channel);data=wave+self.u(wi+20)+self.u(ci)
            if fmt==2:
                ad=wi+self.u(ci+4);co=struct.unpack_from('>16h',self.d,ad);h1,h2=struct.unpack_from('>hh',self.d,ad+0x24);samples=[]
                for off in range(0,((end+13)//14)*8,8):
                    header=self.d[data+off];shift=header&15;predictor=header>>4
                    if predictor>7:raise ValueError('Invalid native DSP predictor')
                    c1,c2=co[2*predictor:2*predictor+2]
                    for n in range(14):
                        byte=self.d[data+off+1+n//2];v=(byte>>(0 if n&1 else 4))&15
                        if v>=8:v-=16
                        v=((v<<shift)*2048+c1*h1+c2*h2+1024)>>11;v=max(-32768,min(32767,v))
                        h2,h1=h1,v;samples.append(v)
                samples=samples[:end]
            elif fmt==1:samples=list(struct.unpack_from('>'+str(end)+'h',self.d,data))
            elif fmt==0:samples=[v*256 for v in struct.unpack_from('>'+str(end)+'b',self.d,data)]
            else:raise ValueError('Unsupported native HOME wave codec')
            decoded.append(samples)
        samples=list(zip(decoded[0],decoded[-1]))
        value=(samples,rate,start,loop,self.d[p+12],self.d[p+13],struct.unpack_from('>f',self.d,p+16)[0])
        self.waves[key]=value;return value
    def score(self,index):
        sound=self.table(0,index);info=self.ref(sound+24);f,_=self.file(self.u(sound+4));bank=self.u(info+4)
        if self.d[f:f+4]!=b'RSEQ':raise ValueError('HOME sound is not the reviewed sequence')
        data=f+self.u(f+16);seq=data+self.u(data+8);at=seq+self.u(info);stack=[];loops=[]
        time=0.;tempo=120;program=0;volume=1.;transpose=0;bend=0;bendrange=2;notewait=True;notes=[]
        def var():
            nonlocal at
            result=0
            for _ in range(5):
                b=self.d[at];at+=1;result=(result<<7)|(b&127)
                if not b&128:return result
            raise ValueError('Native sequence variable length bounds')
        def offset24():
            nonlocal at
            v=int.from_bytes(self.d[at:at+3],'big');at+=3;return seq+v
        for _ in range(4096):
            if time>6:raise ValueError('HOME effect sequence exceeds bounded duration')
            cmd=self.d[at];at+=1
            if cmd<128:
                velocity=self.d[at];at+=1;duration=var();seconds=duration*60/(tempo*48)
                notes.append((time,program,cmd+transpose+bend*bendrange/128,velocity/127,volume,seconds))
                if notewait:time+=seconds
            elif cmd==0x80:time+=var()*60/(tempo*48)
            elif cmd==0x81:program=var()
            elif cmd==0x89:at=offset24()
            elif cmd==0x8a:
                target=offset24();stack.append(at);at=target
            elif cmd==0xfd:
                if not stack:break
                at=stack.pop()
            elif cmd==0xff:break
            elif 0xc0<=cmd<=0xdf:
                v=self.d[at];at+=1
                if cmd in (0xc1,0xc2):volume=v/127
                elif cmd==0xc3:transpose=v if v<128 else v-256
                elif cmd==0xc4:bend=v if v<128 else v-256
                elif cmd==0xc5:bendrange=v
                elif cmd==0xc7:notewait=bool(v)
                elif cmd==0xd4:loops.append([at,v])
            elif cmd==0xfc:
                if not loops:raise ValueError('Unexpected HOME loop')
                loops[-1][1]-=1
                if loops[-1][1]>0:at=loops[-1][0]
                else:loops.pop()
            elif cmd in (0xe0,0xe1,0xe2,0xe3,0xfe):
                v=struct.unpack_from('>H',self.d,at)[0];at+=2
                if cmd==0xe1:tempo=v
            else:raise ValueError(f'Unreviewed HOME sequence command {cmd:#x}')
        else:raise ValueError('HOME sequence execution limit')
        return bank,notes,time,self.d[sound+20]/127
    def render(self,index,rate=32000):
        bank,notes,end,sound_volume=self.score(index);left=[0.]*int(rate*6);right=[0.]*int(rate*6);length=0
        for start,program,note,velocity,volume,duration in notes:
            samples,samplerate,loopstart,loop,key,inst_volume,tune=self.samples(bank,program)
            _,_,instrument=self.instrument(bank,program)
            release=self.d[instrument+7]
            if release>127:raise ValueError('Invalid native HOME release')
            # NW4R EnvGenerator::CalcRelease is in tenths of dB per millisecond.
            slope=65535. if release==127 else 24. if release==126 else (release*2+1)/640. if release<50 else 12./(126-release)
            tail=0. if release==127 else min(2.,72./slope/1000.)
            speed=2**((note-key)/12)*(tune if tune>0 else 1);step=speed*samplerate/rate
            natural=len(samples)/samplerate/speed
            gate=max(duration,end-start) if loop else duration
            seconds=(gate+tail if loop else min(gate+tail,natural) if duration>0 else natural)
            seconds=min(seconds,6-start);count=max(0,int(seconds*rate));offset=int(start*rate)
            gain=velocity*velocity*volume*sound_volume*inst_volume/127
            for i in range(count):
                pos=i*step
                if pos>=len(samples):
                    if not loop:break
                    pos=loopstart+(pos-loopstart)%(len(samples)-loopstart)
                a=int(pos);b=min(a+1,len(samples)-1)
                # Note-off enters the instrument release, rather than truncating the wave.
                elapsed=i/rate
                amp=10**(-slope*(elapsed-gate)*1000/200) if duration>0 and elapsed>gate else 1.
                left[offset+i]+=(samples[a][0]+(samples[b][0]-samples[a][0])*(pos-a))*gain*amp
                right[offset+i]+=(samples[a][1]+(samples[b][1]-samples[a][1])*(pos-a))*gain*amp
                length=max(length,offset+i+1)
        pcm=array.array('h',(max(-32768,min(32767,round(v)))for pair in zip(left[:length],right[:length])for v in pair));pcm.byteswap()
        return pcm.tobytes(),dict(id=index,frames=length,rate=rate,notes=len(notes),native_bank=True)

def home_sound_pack(rsar):
    reader=HomeSounds(rsar);bodies=[];rows=[];offset=16+22*16
    for index in range(22):
        data,record=reader.render(index);bodies.append(data);rows.append(record|dict(offset=offset,bytes=len(data)));offset+=len(data)
    result=b'KWFX'+struct.pack('>III',1,22,32000)+b''.join(struct.pack('>IIII',r['offset'],r['frames'],r['rate'],0)for r in rows)+b''.join(bodies)
    return result,dict(effects=rows,source='local IplSound.brsar native HOME RSEQ/bank0 DSP samples',bytes=len(result),sha256=hashlib.sha256(result).hexdigest())

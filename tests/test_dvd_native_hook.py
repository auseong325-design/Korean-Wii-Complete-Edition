"""Execute compiled menu PPC with synthetic SD responses; no console state."""
import struct
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
runtime=ROOT/'workspace/private/unicorn-2.1.1'
if runtime.exists():sys.path.insert(0,str(runtime))
from kwce.dvd_native_hook import compile_hook,CAVE,BANNER,ORIGINAL


class NativeHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.player=(ROOT/'workspace/channels/dvd-player/build-v31/boot.dol').read_bytes()
        cls.blobs,cls.symbols=compile_hook(cls.player)

    def available(self,kind):
        from unicorn import Uc,UC_ARCH_PPC,UC_MODE_32,UC_MODE_BIG_ENDIAN,UC_HOOK_CODE
        from unicorn.ppc_const import UC_PPC_REG_1,UC_PPC_REG_3,UC_PPC_REG_4,UC_PPC_REG_LR,UC_PPC_REG_PC
        u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN)
        u.mem_map(0x80000000,0x1800000)
        for name,addr in [('native',CAVE),('banner',BANNER),('payload',ORIGINAL+32)]:u.mem_write(addr,self.blobs[name])
        def word(addr,value):u.mem_write(addr,struct.pack('>I',value))
        word(0x81089084,0x80100000);word(0x80100018,0x80200000)
        u.mem_write(0x80201148,b'A')
        u.reg_write(UC_PPC_REG_1,0x807ff000)
        stop=0x80001000
        u.reg_write(UC_PPC_REG_LR,stop)
        opened=[]
        def call(uc,address,size,_):
            ret=None
            if address==stop:uc.emu_stop();return
            if address==0x8135E38C:ret=0
            elif address==0x8135E408:ret=5
            elif address==0x815C0DA4:
                addr=uc.reg_read(UC_PPC_REG_3)
                opened.append(bytes(uc.mem_read(addr,30)).split(b'\0')[0])
                ret=0 if kind=='missing' else 0x80300000
            elif address==0x815C0E00:
                data=bytearray(self.player[:256])
                if kind=='corrupt':data[10]^=1
                uc.mem_write(uc.reg_read(UC_PPC_REG_3),bytes(data))
                ret=100 if kind=='short' else 256
            elif address==0x815C0D4C:ret=0
            if ret is not None:
                uc.reg_write(UC_PPC_REG_3,ret)
                uc.reg_write(UC_PPC_REG_PC,uc.reg_read(UC_PPC_REG_LR))
        u.hook_add(UC_HOOK_CODE,call)
        u.emu_start(self.symbols['kwce_module_available'],stop,count=100000)
        self.assertEqual(opened,[b'A:/kwce/dvd/boot.ash'])
        return u.reg_read(UC_PPC_REG_3)

    def test_pinned_header_accepted(self):self.assertEqual(self.available('good'),1)
    def test_missing_file_rejected(self):self.assertEqual(self.available('missing'),0)
    def test_truncated_read_rejected(self):self.assertEqual(self.available('short'),0)
    def test_corrupt_header_rejected(self):self.assertEqual(self.available('corrupt'),0)

    def test_other_disc_scenes_keep_original_enable_and_launch_calls(self):
        from unicorn import Uc,UC_ARCH_PPC,UC_MODE_32,UC_MODE_BIG_ENDIAN,UC_HOOK_CODE
        from unicorn.ppc_const import UC_PPC_REG_1,UC_PPC_REG_3,UC_PPC_REG_4,UC_PPC_REG_5,UC_PPC_REG_LR,UC_PPC_REG_PC
        # Include state16 with a non-DVD title: state alone must not hijack it.
        for state,kind in ((0,0),(7,1),(16,2),(16,3),(16,14),(16,16)):
            for name,trampoline in [('kwce_enable',ORIGINAL+8),('kwce_reserve',ORIGINAL+16)]:
                with self.subTest(state=state,kind=kind,function=name):
                    u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN);u.mem_map(0x80000000,0x1800000)
                    for section,addr in [('native',CAVE),('banner',BANNER),('payload',ORIGINAL+32)]:u.mem_write(addr,self.blobs[section])
                    scene=0x80200000;u.mem_write(scene+0x74,struct.pack('>I',state));calls=[]
                    def mock(uc,addr,size,_):
                        ret=None
                        if addr==0x813B1564:ret=kind
                        elif addr==trampoline:
                            calls.append(tuple(uc.reg_read(r)for r in (UC_PPC_REG_3,UC_PPC_REG_4,UC_PPC_REG_5)))
                            ret=123
                        elif addr in (0x815C0DA4,0x815D0A08):
                            self.fail('An ordinary disc attempted native DVD file I/O')
                        if ret is not None:
                            uc.reg_write(UC_PPC_REG_3,ret);uc.reg_write(UC_PPC_REG_PC,uc.reg_read(UC_PPC_REG_LR))
                    u.hook_add(UC_HOOK_CODE,mock)
                    for r,v in ((UC_PPC_REG_1,0x807ff000),(UC_PPC_REG_3,scene),(UC_PPC_REG_4,2),(UC_PPC_REG_5,7),(UC_PPC_REG_LR,0x80001000)):u.reg_write(r,v)
                    u.emu_start(self.symbols[name],0x80001000,count=100000)
                    self.assertEqual(len(calls),1);self.assertEqual(calls[0][0],scene)
                    if name=='kwce_enable':self.assertEqual(calls[0],(scene,2,7));self.assertEqual(u.reg_read(UC_PPC_REG_3),123)

    def test_pending_launch_holds_scene_while_sc_is_busy(self):
        from unicorn import Uc,UC_ARCH_PPC,UC_MODE_32,UC_MODE_BIG_ENDIAN,UC_HOOK_CODE
        from unicorn.ppc_const import UC_PPC_REG_1,UC_PPC_REG_3,UC_PPC_REG_LR,UC_PPC_REG_PC
        for pending in (False,True):
            u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN);u.mem_map(0x80000000,0x1800000)
            for name,addr in [('native',CAVE),('banner',BANNER),('payload',ORIGINAL+32)]:u.mem_write(addr,self.blobs[name])
            if pending:u.mem_write(self.symbols['loader_ctx'],struct.pack('>5I',0x91000000,0x80200000,1,0,0))
            u.reg_write(UC_PPC_REG_1,0x807ff000);u.reg_write(UC_PPC_REG_3,0x80200000);u.reg_write(UC_PPC_REG_LR,0x80001000)
            shutdown=[]
            def mock(uc,addr,size,_):
                ret=None
                if addr==ORIGINAL+24:ret=1
                elif addr==0x81552564:ret=0
                elif addr==0x813332D0:ret=1
                elif addr==0x815410FC:ret=1
                elif addr==0x8150B050:shutdown.append(addr);uc.emu_stop()
                if ret is not None:
                    uc.reg_write(UC_PPC_REG_3,ret);uc.reg_write(UC_PPC_REG_PC,uc.reg_read(UC_PPC_REG_LR))
            u.hook_add(UC_HOOK_CODE,mock)
            u.emu_start(self.symbols['kwce_fade'],0x80001000,count=100000)
            self.assertEqual(u.reg_read(UC_PPC_REG_3),0 if pending else 1)
            self.assertEqual(shutdown,[])

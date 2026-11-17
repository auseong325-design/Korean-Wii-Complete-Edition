"""Actual PPC menu callback must not start the stock error during SD setup."""
import struct,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'workspace/private/unicorn-2.1.1'))
from kwce.dvd_native_hook import compile_hook,CAVE,BANNER,ORIGINAL

class NativeWaitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        player=(ROOT/'workspace/channels/dvd-player/build-v43/boot.dol').read_bytes()
        cls.blobs,cls.symbols=compile_hook(player,source=ROOT/'homebrew/kwce-disc-menu/native-v2')

    def execute(self,ready,ticks=0,stage=0,drive=7):
        from unicorn import Uc,UC_ARCH_PPC,UC_MODE_32,UC_MODE_BIG_ENDIAN,UC_HOOK_CODE
        from unicorn.ppc_const import UC_PPC_REG_1,UC_PPC_REG_3,UC_PPC_REG_4,UC_PPC_REG_5,UC_PPC_REG_LR,UC_PPC_REG_PC
        u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN);u.mem_map(0x80000000,0x1800000)
        for name,addr in [('native',CAVE),('banner',BANNER),('payload',ORIGINAL+32)]:u.mem_write(addr,self.blobs[name])
        word=lambda p,v:u.mem_write(p,struct.pack('>I',v))
        scene=0x80200000;word(0x810890b0,0x80300000);word(0x80300004,drive);word(scene+0x74,7)
        u.mem_write(self.symbols['banner_ctx'],struct.pack('>6I',scene,0,1,0,ticks,stage))
        for group,index in ((1,2),(2,2),(1,4),(2,4),(4,7),(4,8)):
            word(scene+0x258+40*group+4*index,0x80400000+0x100*group+0x20*index)
        calls=[]
        def hook(uc,addr,size,_):
            if addr==self.symbols['kwce_module_available']:
                calls.append('available');uc.reg_write(UC_PPC_REG_3,int(ready))
            elif addr==0x813B7A00:calls.append('stock_update')
            elif addr==0x81368FB8:calls.append('play')
            else:return
            uc.reg_write(UC_PPC_REG_PC,uc.reg_read(UC_PPC_REG_LR))
        u.hook_add(UC_HOOK_CODE,hook)
        for r,v in ((UC_PPC_REG_1,0x807ff000),(UC_PPC_REG_3,scene),(UC_PPC_REG_4,0),(UC_PPC_REG_5,0),(UC_PPC_REG_LR,0x80001000)):u.reg_write(r,v)
        u.emu_start(self.symbols['kwce_update'],0x80001000,count=100000)
        state=int.from_bytes(u.mem_read(scene+0x74,4),'big')
        ctx=struct.unpack('>6I',u.mem_read(self.symbols['banner_ctx'],24))
        return state,ctx,calls

    def test_not_ready_holds_spinning_without_stock_error(self):
        state,ctx,calls=self.execute(False)
        self.assertEqual(state,7);self.assertEqual(ctx[5],5)
        self.assertNotIn('stock_update',calls);self.assertNotIn('play',calls)

    def test_ready_starts_dvd_path(self):
        state,ctx,calls=self.execute(True,ticks=20,stage=5)
        self.assertEqual(state,18);self.assertEqual(ctx[5],4)
        self.assertEqual(calls.count('play'),2);self.assertNotIn('stock_update',calls)

    def test_timeout_falls_back_to_stock_error(self):
        state,ctx,calls=self.execute(False,ticks=299,stage=5)
        self.assertEqual(state,7);self.assertEqual(ctx[3],1)
        self.assertIn('stock_update',calls)

    def test_non_error_disc_keeps_stock_path(self):
        state,ctx,calls=self.execute(False,drive=6)
        self.assertIn('stock_update',calls);self.assertNotIn('available',calls)

class NativeV16WaitTests(NativeWaitTests):
    @classmethod
    def setUpClass(cls):
        player=(ROOT/'workspace/channels/dvd-player/build-v43/boot.dol').read_bytes()
        cls.blobs,cls.symbols=compile_hook(player,source=ROOT/'homebrew/kwce-disc-menu/native-v4')

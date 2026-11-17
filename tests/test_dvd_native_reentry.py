"""Execute the native PPC callback for cached re-entry and disc removal."""
import struct, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'workspace/private/unicorn-2.1.1'))
from kwce.dvd_native_hook import compile_hook,CAVE,BANNER,ORIGINAL,BANNER_IO

class NativeReentryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        player=(ROOT/'workspace/channels/dvd-player/build-v43/boot.dol').read_bytes()
        cls.blobs,cls.sym=compile_hook(player,source=ROOT/'homebrew/kwce-disc-menu/native-v5')

    def run_update(self,*,drive,cache,state,ready):
        from unicorn import Uc,UC_ARCH_PPC,UC_MODE_32,UC_MODE_BIG_ENDIAN,UC_HOOK_CODE
        from unicorn.ppc_const import UC_PPC_REG_1,UC_PPC_REG_3,UC_PPC_REG_4,UC_PPC_REG_5,UC_PPC_REG_LR,UC_PPC_REG_PC
        u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN);u.mem_map(0x80000000,0x1800000)
        for n,addr in [('native',CAVE),('banner',BANNER),('bannerio',BANNER_IO),('payload',ORIGINAL+32)]:u.mem_write(addr,self.blobs[n])
        put=lambda a,v:u.mem_write(a,struct.pack('>I',v))
        scene=0x80200000;put(0x810890b0,0x80300000);put(0x80300004,drive);put(scene+0x74,state)
        u.mem_write(self.sym['banner_ctx'],struct.pack('>6I',scene,0,1,0,0,0));put(self.sym['cached_disc'],cache)
        for group in range(1,5):
            for index in range(1,6):put(scene+0x258+40*group+4*index,0x80400000+0x100*group+0x20*index)
        calls=[]
        def hook(uc,addr,size,_):
            if addr==self.sym['kwce_module_available']:
                calls.append('available');uc.reg_write(UC_PPC_REG_3,int(ready))
            elif addr==self.sym['kwce_load_banner']:
                calls.append('load_banner');uc.reg_write(UC_PPC_REG_3,0x80500000)
            elif addr==0x813B57A8:
                calls.append('create');put(scene+0x23c,0x80510000)
            elif addr==0x813B7A00:calls.append('stock')
            elif addr in (0x813699C8,0x813B8ED0,0x81368FB8):calls.append('native_helper')
            else:return
            uc.reg_write(UC_PPC_REG_PC,uc.reg_read(UC_PPC_REG_LR))
        u.hook_add(UC_HOOK_CODE,hook)
        for reg,val in ((UC_PPC_REG_1,0x807ff000),(UC_PPC_REG_3,scene),(UC_PPC_REG_4,0),(UC_PPC_REG_5,0),(UC_PPC_REG_LR,0x80001000)):u.reg_write(reg,val)
        u.emu_start(self.sym['kwce_update'],0x80001000,count=200000)
        read=lambda a:int.from_bytes(u.mem_read(a,4),'big')
        return read(scene+0x74),read(self.sym['cached_disc']),calls

    def test_recognized_disc_reopens_banner(self):
        state,cache,calls=self.run_update(drive=7,cache=1,state=2,ready=True)
        self.assertEqual((state,cache),(16,1));self.assertIn('load_banner',calls);self.assertNotIn('stock',calls)

    def test_removal_invalidates_cache_and_keeps_stock_path(self):
        state,cache,calls=self.run_update(drive=0,cache=1,state=2,ready=True)
        self.assertEqual(cache,0);self.assertIn('stock',calls);self.assertNotIn('load_banner',calls)

    def test_unrecognized_disc_does_not_use_cache(self):
        state,cache,calls=self.run_update(drive=7,cache=0,state=2,ready=True)
        self.assertIn('stock',calls);self.assertNotIn('load_banner',calls)

    def test_missing_module_does_not_open_cached_banner(self):
        state,cache,calls=self.run_update(drive=7,cache=1,state=2,ready=False)
        self.assertIn('stock',calls);self.assertNotIn('load_banner',calls)

class NativeV22ReentryTests(NativeReentryTests):
    @classmethod
    def setUpClass(cls):
        player=(ROOT/'workspace/channels/dvd-player/build-v43/boot.dol').read_bytes()
        cls.blobs,cls.sym=compile_hook(player,source=ROOT/'homebrew/kwce-disc-menu/native-v9')

    def test_cached_banner_can_open_at_scene_start(self):
        state,cache,calls=self.run_update(drive=7,cache=1,state=0,ready=True)
        self.assertEqual((state,cache),(16,1));self.assertIn('load_banner',calls)

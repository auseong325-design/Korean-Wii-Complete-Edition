"""Compiled PPC banner: ordinary-disc forwarding and DVD ejection ownership."""
import struct
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'workspace/private/unicorn-2.1.1'))
from kwce.dvd_native_hook import compile_hook, CAVE, BANNER, ORIGINAL


class NativeBannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blobs, cls.symbols = compile_hook((ROOT/'workspace/channels/dvd-player/build-v43/boot.dol').read_bytes())

    def run_update(self, drive, eject=False):
        from unicorn import Uc,UC_ARCH_PPC,UC_MODE_32,UC_MODE_BIG_ENDIAN,UC_HOOK_CODE
        from unicorn.ppc_const import UC_PPC_REG_1,UC_PPC_REG_3,UC_PPC_REG_4,UC_PPC_REG_5,UC_PPC_REG_LR,UC_PPC_REG_PC
        u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN);u.mem_map(0x80000000,0x1800000)
        for name,addr in [('native',CAVE),('banner',BANNER),('payload',ORIGINAL+32)]:u.mem_write(addr,self.blobs[name])
        def word(a,v):u.mem_write(a,struct.pack('>I',v))
        def get(a):return int.from_bytes(u.mem_read(a,4),'big')
        scene,file,layout,original,sound=0x80200000,0x80400000,0x80500000,0x80510000,0x80600000
        word(0x810890b0,0x80300000);word(0x80300004,drive)
        word(scene+0x74,16 if eject else 6)
        u.mem_write(self.symbols['banner_ctx'],struct.pack('>6I',scene,file if eject else 0,1,0,0,2 if eject else 0))
        if eject:
            for at,v in ((0x21c,file),(0x23c,layout),(0x22c,sound),(0x250,original),(0x254,original)):
                word(scene+at,v)
        calls=[]
        def mock(uc,addr,size,_):
            ret=None
            if addr==0x813B7A00:
                calls.append(('update',tuple(uc.reg_read(r)for r in (UC_PPC_REG_3,UC_PPC_REG_4,UC_PPC_REG_5))));ret=0
            elif addr==0x8133BA54:ret=1
            elif addr in (0x8136A194,0x8133BB18,0x8133A94C):
                calls.append(('delete',uc.reg_read(UC_PPC_REG_3)));ret=0
            elif addr in (0x813B55BC,0x813B8ED0):ret=0
            elif addr==0x815C0DA4:self.fail('An ordinary/ejected disc opened the DVD module')
            if ret is not None:
                uc.reg_write(UC_PPC_REG_3,ret);uc.reg_write(UC_PPC_REG_PC,uc.reg_read(UC_PPC_REG_LR))
        u.hook_add(UC_HOOK_CODE,mock)
        for r,v in ((UC_PPC_REG_1,0x807ff000),(UC_PPC_REG_3,scene),(UC_PPC_REG_4,2),(UC_PPC_REG_5,7),(UC_PPC_REG_LR,0x80001000)):u.reg_write(r,v)
        u.emu_start(self.symbols['kwce_update'],0x80001000,count=100000)
        self.assertEqual([c for c in calls if c[0]=='update'],[('update',(scene,2,7))])
        if eject:
            self.assertCountEqual([c[1]for c in calls if c[0]=='delete'],[layout,file,sound])
            self.assertEqual(get(self.symbols['banner_ctx']+4),0)
            self.assertEqual(get(scene+0x21c),original)
            self.assertEqual(get(scene+0x23c),0)
            self.assertEqual(get(scene+0x74),0)
        else:self.assertEqual(len(calls),1)

    def test_other_disc_states_use_original_sdk_update(self):
        for state in (0,1,2,3,4,5,6,8):
            with self.subTest(drive=state):self.run_update(state)

    def test_dvd_ejection_frees_each_owned_object_once(self):self.run_update(0,eject=True)

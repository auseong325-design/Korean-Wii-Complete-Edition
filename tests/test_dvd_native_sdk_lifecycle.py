"""Run the original SDK layout/heap ownership code without a renderer or threads.

Fonts, pane matrices, language selection, sound and OS mutexes are stubbed.
Real SDK archive parsing, layout allocations, heap lists and destructors run.
This is an ownership regression test, not a reproduction of the hardware hang.
"""
from pathlib import Path
import struct
import unittest

from kwce.ppc_patch import sections

ROOT=Path(__file__).resolve().parents[1]


class SDKMachine:
    def __init__(self):
        from unicorn import Uc,UC_ARCH_PPC,UC_MODE_32,UC_MODE_BIG_ENDIAN,UC_HOOK_CODE
        from unicorn import ppc_const as R
        self.R=R;self.u=u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN)
        u.mem_map(0x80000000,0x1800000);u.mem_map(0x90000000,0x4000000)
        dol=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
        for _,o,a,s in sections(dol):u.mem_write(a,dol[o:o+s])
        u.reg_write(R.UC_PPC_REG_MSR,0x2000)
        def hook(uc,addr,size,_):
            # Matrix arithmetic uses Gekko paired-single instructions unavailable
            # in Unicorn. It has no part in these heap ownership assertions.
            if addr==0x81519BE8: # PSMTXIdentity, pinned 43K symbol map
                uc.mem_write(uc.reg_read(R.UC_PPC_REG_3),struct.pack('>12f',1,0,0,0,0,1,0,0,0,0,1,0))
            elif addr in (0x8150A988,0x8150A9C0,0x8150AA9C,0x8150963C,0x81509664,
                          0x81369F5C,0x813B1800,0x813B1408,0x814F7FC8):
                uc.reg_write(R.UC_PPC_REG_3,int(addr==0x8150963C))
            elif addr in (0x81334E84,0x81334F24,0x813B1504):
                uc.reg_write(R.UC_PPC_REG_3,{0x81334E84:9,0x81334F24:4,0x813B1504:1}[addr])
            elif addr in (0x815066C0,0x815066EC,0x8150671C,0x815067A4,0x81507458):pass
            elif addr==0x815074E8:raise AssertionError('SDK panic during synthetic layout lifecycle')
            else:return
            uc.reg_write(R.UC_PPC_REG_PC,uc.reg_read(R.UC_PPC_REG_LR))
        u.hook_add(UC_HOOK_CODE,hook)
        self.run(0x813300A8);self.run(0x815D08B0)
        self.root=self.run(0x815D01C8,0x91000000,0x400000,9)
        assert self.root;self.put(0x8166DDE0,self.root)
        self.disk=self.run(0x815D0260,0x19100,self.root,9);assert self.disk
        self.obj=0x80300000;self.put(self.obj+0x14,self.disk)
        icon=(ROOT/'workspace/experiments/dvd-native-icon-v1/icon.arc').read_bytes()
        self.u.mem_write(0x90400000,icon)

    def put(self,a,v):self.u.mem_write(a,struct.pack('>I',v))
    def get(self,a):return int.from_bytes(self.u.mem_read(a,4),'big')

    def run(self,address,*args):
        R=self.R;u=self.u
        u.reg_write(R.UC_PPC_REG_1,0x817e0000);u.reg_write(R.UC_PPC_REG_LR,0x80001000)
        for i,v in enumerate(args):u.reg_write(getattr(R,'UC_PPC_REG_'+str(i+3)),v)
        u.emu_start(address,0x80001000,count=3000000)
        assert u.reg_read(R.UC_PPC_REG_PC)==0x80001000,'SDK instruction budget exceeded'
        return u.reg_read(R.UC_PPC_REG_3)

    def free_size(self):return self.run(0x815D03BC,self.disk,4)
    def create(self):
        self.run(0x813B12D8,self.obj,0x90400000)
        layout=self.get(self.obj+0x40);assert layout;return layout


class SDKLifecycleTests(unittest.TestCase):
    def test_real_sdk_create_and_destroy_restore_heap(self):
        m=SDKMachine();before=m.free_size();m.create();self.assertLess(m.free_size(),before)
        m.run(0x813B13B8,m.obj);self.assertEqual(m.get(m.obj+0x40),0)
        self.assertEqual(m.free_size(),before);m.run(0x815D0334,m.disk)

    def test_repeated_layout_creation_reuses_archive_without_leak(self):
        m=SDKMachine();before=m.free_size()
        for _ in range(16):
            m.create();m.run(0x813B13B8,m.obj);self.assertEqual(m.free_size(),before)

    def test_channel_object_destructor_releases_aliased_disk_layout(self):
        m=SDKMachine();before=m.free_size();layout=m.create()
        # calcNormal points the thumbnail at the active disk layout.
        m.put(m.obj+0x30,layout)
        m.run(0x813B0A30,m.obj,0)
        self.assertEqual(m.get(m.obj+0x40),0);self.assertEqual(m.free_size(),before)
        m.run(0x815D0334,m.disk)


if __name__=='__main__':unittest.main()

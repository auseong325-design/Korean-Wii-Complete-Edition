"""PPC read/graphics separation, one positive cue, and frozen SD scope."""
from pathlib import Path
import json
import struct
import tempfile
import unittest

from kwce.dvd_native_hook import compile_hook,CAVE,END,BANNER,BANNER_END,BANNER_IO,ORIGINAL,SITES
from kwce.ppc_patch import to_file
from kwce.priiloader_legacy import parse
from kwce import dvd_read_control_sd as control

ROOT=Path(__file__).resolve().parents[1]


class ReadControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        player=(ROOT/'workspace/channels/dvd-player/build-v51/boot.dol').read_bytes()
        module=(ROOT/'workspace/experiments/dvd-native-module-v10/player.ash').read_bytes()
        cls.blobs,cls.sym=compile_hook(player,module,source=ROOT/'homebrew/kwce-disc-menu/native-v32')
        cls.package=ROOT/'workspace/hardware/kwce-dvd-read-control-v1'

    def machine(self,ready):
        from unicorn import Uc,UC_ARCH_PPC,UC_MODE_32,UC_MODE_BIG_ENDIAN,UC_HOOK_CODE
        from unicorn import ppc_const as R
        u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN);u.mem_map(0x80000000,0x1800000)
        for n,a in [('native',CAVE),('banner',BANNER),('bannerio',BANNER_IO),('payload',ORIGINAL+32)]:
            u.mem_write(a,self.blobs[n])
        calls=[]
        def put(a,v):u.mem_write(a,struct.pack('>I',v))
        put(0x810890b0,0x80300000)
        def hook(uc,addr,size,_):
            if addr==self.sym['kwce_load_icon']:
                calls.append('read');uc.reg_write(R.UC_PPC_REG_3,0x80500000 if ready[0] else 0)
            elif addr==0x8136A800:
                self.assertEqual(uc.reg_read(R.UC_PPC_REG_3),0x8108992C)
                name=bytes(uc.mem_read(uc.reg_read(R.UC_PPC_REG_4),15)).split(b'\0')[0]
                self.assertEqual(name,b'WIPL_SE_DECIDE');calls.append('sound')
                uc.reg_write(R.UC_PPC_REG_3,1)
            elif addr==0x813AC288:calls.append('stock')
            elif addr in (0x813B12D8,0x813B13B8,0x813AC620,0x813AC680,self.sym['kwce_module_available']):
                self.fail('Read control called a layout/animation/player preparation path')
            else:return
            uc.reg_write(R.UC_PPC_REG_PC,uc.reg_read(R.UC_PPC_REG_LR))
        u.hook_add(UC_HOOK_CODE,hook)
        def run(drive=7,owner=0x80200000):
            put(0x80300004,drive)
            for reg,v in [(R.UC_PPC_REG_1,0x807ff000),(R.UC_PPC_REG_3,owner),(R.UC_PPC_REG_LR,0x80001000)]:u.reg_write(reg,v)
            u.emu_start(self.sym['kwce_select_update'],0x80001000,count=100000)
            self.assertEqual(u.reg_read(R.UC_PPC_REG_PC),0x80001000)
            self.assertEqual(u.reg_read(R.UC_PPC_REG_1),0x807ff000)
        return run,calls

    def test_success_has_one_notice_and_stock_update_every_frame(self):
        run,calls=self.machine([True])
        for _ in range(20):run()
        self.assertEqual(calls[:3],['read','sound','stock'])
        self.assertEqual(calls.count('read'),1);self.assertEqual(calls.count('sound'),1)
        self.assertEqual(calls.count('stock'),20)

    def test_readiness_failure_eject_and_scene_change(self):
        ready=[False];run,calls=self.machine(ready)
        run();run();self.assertEqual(calls,['read','stock','read','stock'])
        ready[0]=True;run();run();self.assertEqual(calls.count('sound'),1)
        run(1);run(5);run(6);self.assertEqual(calls.count('read'),3)
        run();self.assertEqual(calls.count('sound'),2)
        run(owner=0x80201000);self.assertEqual(calls.count('sound'),3)

    def test_frozen_menu_changes_only_reviewed_code_regions(self):
        old=(ROOT/'workspace/experiments/dvd-native-hook-v60/menu.dol').read_bytes()
        new=(ROOT/'workspace/experiments/dvd-native-hook-v61/menu.dol').read_bytes()
        allowed=set()
        for a,z in [(ORIGINAL+32,ORIGINAL+0x740),(BANNER,BANNER_END),(CAVE,END),(0x813A9FBC,0x813A9FC0)]:
            at=to_file(old,a,z-a);allowed.update(range(at,at+z-a))
        self.assertEqual(len(old),len(new))
        self.assertTrue(any(a!=b for a,b in zip(old,new)))
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(old,new)) if a!=b))
        for address in [*SITES,0x8135E820]:
            at=to_file(old,address);self.assertEqual(old[at:at+4],new[at:at+4])

    def test_sd_scope_and_wrong_input_are_rejected(self):
        meta,files=control.sd_files(self.package);self.assertEqual(len(files),5)
        self.assertFalse(meta['custom_icon_layout'])
        for rel in control.TARGETS:
            old=(self.package/'expected'/rel).read_bytes();new=(self.package/rel).read_bytes()
            a,b=parse(old),parse(new)
            self.assertEqual([r['name']for r in a],[r['name']for r in b])
            self.assertEqual([r for r in a if not r['name'].startswith('KWCE DVD:')],
                             [r for r in b if not r['name'].startswith('KWCE DVD:')])
            with self.assertRaises(ValueError):control.upgrade_definition(new)
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);raw=(self.package/'package-manifest.json').read_bytes()
            (p/'package-manifest.json').write_bytes(raw+b' ')
            (p/'package-manifest.sha256').write_bytes((self.package/'package-manifest.sha256').read_bytes())
            with self.assertRaises(ValueError):control.sd_files(p)


if __name__=='__main__':unittest.main()

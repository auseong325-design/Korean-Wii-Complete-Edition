"""Actual PPC call-site control and legacy SD scope for native59."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from kwce import dvd_thumbnail_trial_sd as trial
from kwce.ppc_patch import to_file
from kwce.priiloader_legacy import parse

ROOT=Path(__file__).resolve().parents[1]
SITE=0x813A9FBC


class StockThumbnailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
        cls.before=(ROOT/'workspace/experiments/dvd-native-hook-v58/menu.dol').read_bytes()
        cls.after=(ROOT/'workspace/experiments/dvd-native-hook-v59/menu.dol').read_bytes()
        cls.package=ROOT/'workspace/hardware/kwce-dvd-stock-thumbnail-v1'
        cls.offset=to_file(cls.original,SITE)

    def test_only_one_instruction_is_restored_to_stock(self):
        at=self.offset
        self.assertEqual(self.before[:at],self.after[:at])
        self.assertEqual(self.before[at+4:],self.after[at+4:])
        self.assertEqual(self.after[at:at+4],self.original[at:at+4])
        self.assertNotEqual(self.before[at:at+4],self.after[at:at+4])

    def test_ppc_call_reaches_original_sdk_instead_of_custom_interceptor(self):
        from unicorn import Uc,UC_ARCH_PPC,UC_MODE_32,UC_MODE_BIG_ENDIAN,UC_HOOK_CODE
        from unicorn.ppc_const import UC_PPC_REG_1,UC_PPC_REG_3,UC_PPC_REG_LR,UC_PPC_REG_PC
        meta=json.loads((ROOT/'workspace/experiments/dvd-native-hook-v58/manifest.json').read_text())
        targets={meta['symbols']['kwce_select_update']:'custom',0x813AC288:'stock'}
        for data,expected in [(self.before,'custom'),(self.after,'stock')]:
            u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN);u.mem_map(0x80000000,0x1800000)
            u.mem_write(SITE,data[self.offset:self.offset+4]);calls=[]
            def hook(uc,address,size,_):
                if address in targets:
                    calls.append(targets[address]);uc.reg_write(UC_PPC_REG_PC,uc.reg_read(UC_PPC_REG_LR))
            u.hook_add(UC_HOOK_CODE,hook)
            u.reg_write(UC_PPC_REG_1,0x81700000);u.reg_write(UC_PPC_REG_3,0x80200000)
            u.emu_start(SITE,SITE+4,count=100)
            self.assertEqual(calls,[expected]);self.assertEqual(u.reg_read(UC_PPC_REG_1),0x81700000)

    def test_three_definitions_preserve_gc_and_other_blocks(self):
        _,files=trial.sd_files(self.package);self.assertEqual(len(files),5)
        for rel in trial.TARGETS:
            before=(self.package/'expected'/rel).read_bytes();after=(self.package/rel).read_bytes()
            self.assertEqual([e['name']for e in parse(before)],[e['name']for e in parse(after)])
            for a,b in zip(before.split(b'['),after.split(b'[')):
                if not a.startswith(b'KWCE DVD: disc channel DVD player]'):self.assertEqual(a,b)
            self.assertEqual(len(next(e for e in parse(after)if 'Japanese memory card encoding'in e['name'])['pairs']),3)

    def test_wrong_input_and_extra_gc_mutation_are_refused(self):
        old=(ROOT/'workspace/hardware/kwce-gc-card-encoding-v1/apps/Priiloader/hacks_hash.ini').read_bytes()
        with self.assertRaisesRegex(ValueError,'native58'):trial.upgrade_definition(old)
        with tempfile.TemporaryDirectory(dir=ROOT/'workspace/private')as folder:
            package=Path(folder)/'package';shutil.copytree(self.package,package)
            rel='apps/Priiloader/hacks_hash.ini';p=package/rel
            data=p.read_bytes().replace(b'[KWCE GC: Wii/GC save menu]',b'[Unexpected GC mutation]');p.write_bytes(data)
            meta=json.loads((package/'package-manifest.json').read_text());meta['files'][rel]=hashlib.sha256(data).hexdigest()
            raw=json.dumps(meta).encode();(package/'package-manifest.json').write_bytes(raw)
            (package/'package-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest())
            with self.assertRaisesRegex(ValueError,'changes more'):trial.sd_files(package)


if __name__=='__main__':unittest.main()

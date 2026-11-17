"""Local-only Priiloader definition preservation and deployment failure gates."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kwce import gc_card_encoding_sd as sd
from kwce.priiloader_hacks import hacks, gc_layout_entry
from kwce.priiloader_legacy import checked_ini, parse

ROOT = Path(__file__).resolve().parents[1]
MENU = ROOT/'workspace/console-baseline/menu-original-43K.dol'


@unittest.skipUnless(MENU.is_file(), 'pinned local 43K original required')
class EncodingSDTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.menu = MENU.read_bytes()
        cls.raw = checked_ini(cls.menu, hacks(cls.menu)+[gc_layout_entry(cls.menu, ordered=True)], packed=True)
        cls.updated = sd.upgrade_definition(cls.raw, cls.menu)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);self.card=self.root/'card';self.package=self.root/'package'
        self.card.mkdir();self.package.mkdir()
        reference=self.root/'workspace/console-baseline/menu-original-43K.dol'
        reference.parent.mkdir(parents=True);reference.write_bytes(self.menu)
        for rel in sd.DEFINITIONS:
            old=self.card/rel;old.parent.mkdir(parents=True, exist_ok=True);old.write_bytes(self.raw)
            new=self.package/rel;new.parent.mkdir(parents=True, exist_ok=True);new.write_bytes(self.updated)
        (self.card/'preserve.txt').write_text('synthetic unrelated file')
        (self.package/sd.README).write_text('synthetic instructions')
        self.manifest()
        for ctx in (patch.object(sd,'ROOT',self.root),patch.object(sd,'wii_mount')):
            ctx.start();self.addCleanup(ctx.stop)

    def manifest(self):
        meta=dict(kind='gc-per-card-priiloader-v1',files={r:sd.sha(self.package/r) for r in sd.PATHS},
                  expected_inputs={r:sd.sha(self.card/r) for r in sd.DEFINITIONS})
        (self.package/'package-manifest.json').write_text(json.dumps(meta))

    def test_names_order_and_all_other_blocks_byte_identical(self):
        old=parse(self.raw);new=parse(self.updated)
        self.assertEqual([x['name'] for x in old],[x['name'] for x in new])
        for a,b in zip(old,new):
            if a['name'] != sd.NAME:self.assertEqual(a,b)
        self.assertEqual(len(next(x for x in new if x['name']==sd.NAME)['pairs']),3)
        old_blocks=self.raw.split(b'[');new_blocks=self.updated.split(b'[')
        for a,b in zip(old_blocks,new_blocks):
            if not a.startswith(sd.NAME.encode()+b']'):self.assertEqual(a,b)

    def test_second_upgrade_or_altered_encoding_group_refused(self):
        with self.assertRaisesRegex(ValueError,'differs'):
            sd.upgrade_definition(self.updated,self.menu)
        changed=self.raw.replace(b'0x38600001',b'0x38600002')
        with self.assertRaisesRegex(ValueError,'differs'):
            sd.upgrade_definition(changed,self.menu)

    def test_full_target_backup_and_only_five_updates_one_addition(self):
        before=sd.metadata_inventory(self.card)
        sd.deploy(self.package,self.card)
        after=sd.metadata_inventory(self.card)
        self.assertEqual(set(after)-set(before),{sd.README})
        self.assertEqual(after['preserve.txt'],before['preserve.txt'])
        backup=self.root/'workspace/private/gc-card-investigation/encoding-sd-1/original-definitions'
        for rel in sd.DEFINITIONS:
            self.assertEqual((backup/rel).read_bytes(),self.raw)
            self.assertEqual((self.card/rel).read_bytes(),self.updated)

    def test_changed_card_and_tampered_package_prevent_writes(self):
        (self.card/'apps/Priiloader/hacks_hash.ini').write_bytes(self.raw+b'changed')
        before=sd.metadata_inventory(self.card)
        with self.assertRaisesRegex(ValueError,'changed since review'):
            sd.deploy(self.package,self.card)
        self.assertEqual(sd.metadata_inventory(self.card),before)
        (self.card/'apps/Priiloader/hacks_hash.ini').write_bytes(self.raw)
        (self.package/sd.README).write_text('tampered')
        with self.assertRaisesRegex(ValueError,'hash'):
            sd.deploy(self.package,self.card)

    def test_other_section_change_detected_even_if_manifest_hash_updated(self):
        rel='kwce-rc/priiloader/gc-only.ini'
        p=self.package/rel;p.write_bytes(p.read_bytes().replace(b'[KWCE GC: Wii/GC save menu]',b'[Other section]'))
        self.manifest()
        with self.assertRaisesRegex(ValueError,'changes more'):
            sd.deploy(self.package,self.card)

    def test_dry_run_never_writes_or_creates_backup(self):
        before=sd.metadata_inventory(self.card);sd.deploy(self.package,self.card,True)
        self.assertEqual(sd.metadata_inventory(self.card),before)
        self.assertFalse((self.root/'workspace/private').exists())

    def test_preexisting_stage_and_project_original_sd_refused(self):
        p=self.card/'apps/Priiloader/hacks_hash.ini.kwce-new';p.write_text('preserve interrupted stage')
        with self.assertRaisesRegex(ValueError,'staging'):
            sd.deploy(self.package,self.card)
        with self.assertRaisesRegex(ValueError,'Original project SD'):
            sd.deploy(self.package,self.root/'sd')


if __name__=='__main__':unittest.main()

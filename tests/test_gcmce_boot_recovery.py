"""Synthetic-only checks for the narrowly guarded default-card update."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_gcmce_recovery as fixtures
from kwce import gcmce_boot_recovery as b
from kwce import gcmce_recovery as r
from kwce.gc_fixture import raw_card


class BootRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RecoveryDeploymentTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.card = self.fixture.root, self.fixture.card
        self.package = self.root/'boot-package';self.package.mkdir()
        source = self.card/b.RAW;source.parent.mkdir(parents=True);source.write_bytes(raw_card(False, 0, 64))
        (self.card/b.SETTINGS).write_bytes(b'[General]\nShowInfo=OFF\n[GC]\nCardRestore=ON\nGameID=ON\nEncoding=JAP\nCardSize=64\n')
        for rel in b.PATHS:
            (self.package/rel).parent.mkdir(parents=True, exist_ok=True)
        (self.package/b.RAW).write_bytes((self.fixture.package/r.RAW).read_bytes())
        (self.package/b.SETTINGS).write_bytes(b.disable_restore((self.card/b.SETTINGS).read_bytes()))
        (self.package/b.INI).write_text(b.CONFIG)
        (self.package/b.README).write_text('Synthetic instructions')
        self.manifest()
        for ctx in (patch.object(b, 'ROOT', self.root), patch.object(b, 'removable_mount')):
            ctx.start();self.addCleanup(ctx.stop)

    def manifest(self):
        meta = dict(kind='gcmce-empty-card1-recovery-v1',
                    files={p:b.sha(self.package/p) for p in b.PATHS},
                    expected_inputs={p:b.sha(self.card/p) for p in (b.RAW, b.SETTINGS)})
        (self.package/'package-manifest.json').write_text(json.dumps(meta))

    def test_complete_backup_and_only_reviewed_changes(self):
        before = b.inventory(self.card)
        original_settings = (self.card/b.SETTINGS).read_bytes()
        b.deploy(self.package, self.card)
        after = b.inventory(self.card)
        self.assertEqual(set(after)-set(before), {b.INI, b.README})
        self.assertEqual({k:after[k] for k in before if k not in {b.RAW,b.SETTINGS}},
                         {k:v for k,v in before.items() if k not in {b.RAW,b.SETTINGS}})
        backup = self.root/'workspace/private/gc-card-investigation/sd-fixed-start-1/original-files'
        self.assertEqual(b.inventory(backup), before)
        self.assertEqual((self.card/b.SETTINGS).read_bytes(), b.disable_restore(original_settings))

    def test_nonempty_card_refused_even_if_hash_was_reviewed(self):
        (self.card/b.RAW).write_bytes((self.package/b.RAW).read_bytes());self.manifest()
        before = b.inventory(self.card)
        with self.assertRaisesRegex(ValueError, 'empty'):
            b.deploy(self.package, self.card)
        self.assertEqual(b.inventory(self.card), before)

    def test_deleted_but_retained_data_preserved(self):
        p = self.card/b.RAW;data = bytearray(p.read_bytes());data[5*8192:5*8192+16] = b'SYNTHETIC-DATA!!'
        p.write_bytes(data);self.manifest();before = b.inventory(self.card)
        with self.assertRaisesRegex(ValueError, 'retained data'):
            b.deploy(self.package, self.card)
        self.assertEqual(b.inventory(self.card), before)

    def test_other_setting_change_refused(self):
        p = self.package/b.SETTINGS;p.write_bytes(p.read_bytes().replace(b'GameID=ON',b'GameID=OFF'));self.manifest()
        with self.assertRaisesRegex(ValueError, 'limited to CardRestore'):
            b.deploy(self.package, self.card)

    def test_changed_source_prevents_writes(self):
        p = self.card/b.SETTINGS;p.write_bytes(p.read_bytes()+b'# changed since review\n')
        before = b.inventory(self.card)
        with self.assertRaisesRegex(ValueError, 'changed since review'):
            b.deploy(self.package, self.card)
        self.assertEqual(b.inventory(self.card), before)

    def test_dry_run_and_existing_added_file_never_write(self):
        before = b.inventory(self.card);b.deploy(self.package, self.card, True)
        self.assertEqual(b.inventory(self.card), before)
        (self.card/b.INI).write_text('preserve this config')
        before = b.inventory(self.card)
        with self.assertRaisesRegex(ValueError, 'Existing added target'):
            b.deploy(self.package, self.card)
        self.assertEqual(b.inventory(self.card), before)

    def test_restore_must_be_in_gc_section(self):
        with self.assertRaises(ValueError):
            b.disable_restore(b'[General]\nCardRestore=ON\n[GC]\nGameID=ON\n')


if __name__ == '__main__':
    unittest.main()

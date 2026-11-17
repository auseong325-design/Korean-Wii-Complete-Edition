"""Synthetic-only tests for add-only recovered-card deployment."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from kwce import gcmce_recovery as r
from kwce.gc_fixture import raw_card, checksum


class RecoveryDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root/'package'
        self.card = self.root/'card'
        self.package.mkdir(); self.card.mkdir()
        (self.card/'.flippermce').mkdir()
        (self.card/'.flippermce/settings.ini').write_text('[GC]\nEncoding=JAP\n')
        (self.card/'MemoryCards/GC/Original').mkdir(parents=True)
        (self.card/'MemoryCards/GC/Original/old.raw').write_bytes(b'synthetic old VMC')
        b = bytearray(raw_card(True, 1, 64))
        for index in (1, 2):
            at = index*8192
            struct.pack_into('>H', b, at+0x38, 11)
            struct.pack_into('>HH', b, at+0x1ffc, *checksum(b[at:at+0x1ffc]))
        for index in (3, 4):
            bat = bytearray(8192)
            struct.pack_into('>HHH', bat, 4, 1, 1008, 15)
            for block in range(5, 16):
                struct.pack_into('>H', bat, 0xa+2*(block-5), block+1 if block<15 else 65535)
            struct.pack_into('>HH', bat, 0, *checksum(bat[4:]))
            b[index*8192:(index+1)*8192] = bat
        p = self.package/r.RAW;p.parent.mkdir(parents=True);p.write_bytes(b)
        (self.package/r.INI).write_text(r.CONFIG)
        (self.package/r.README).write_text('Synthetic test instructions')
        self.write_manifest()
        for context in (patch.object(r, 'ROOT', self.root), patch.object(r, 'removable_mount')):
            context.start();self.addCleanup(context.stop)

    def write_manifest(self):
        files = {x:r.sha(self.package/x) for x in r.PATHS}
        (self.package/'package-manifest.json').write_text(json.dumps(
            {'kind':'gcmce-add-recovered-card-v1','files':files}))

    def test_additions_preserve_all_originals_and_backup_before_writing(self):
        before = r.inventory(self.card)
        r.deploy(self.package, self.card)
        after = r.inventory(self.card)
        self.assertEqual({k:after[k] for k in before}, before)
        self.assertEqual(set(after)-set(before), r.PATHS)
        backup = self.root/'workspace/private/gc-card-investigation/sd-addition-1/original-files'
        self.assertEqual(r.inventory(backup), before)

    def test_existing_recovery_target_refused_without_changes(self):
        p = self.card/r.RAW;p.parent.mkdir(parents=True);p.write_bytes(b'preserve existing target')
        before = r.inventory(self.card)
        with self.assertRaisesRegex(ValueError, 'Existing recovery target'):
            r.deploy(self.package, self.card)
        self.assertEqual(r.inventory(self.card), before)
        self.assertFalse((self.root/'workspace').exists())

    def test_hash_failure_and_path_injection_prevent_writes(self):
        before = r.inventory(self.card)
        (self.package/r.README).write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'hash'):
            r.deploy(self.package, self.card)
        self.write_manifest()
        meta = json.loads((self.package/'package-manifest.json').read_text())
        meta['files']['../escape'] = '0'*64
        (self.package/'package-manifest.json').write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, 'paths'):
            r.deploy(self.package, self.card)
        self.assertEqual(r.inventory(self.card), before)

    def test_dry_run_does_not_create_backup_or_targets(self):
        before = r.inventory(self.card)
        r.deploy(self.package, self.card, True)
        self.assertEqual(r.inventory(self.card), before)
        self.assertFalse((self.root/'workspace').exists())

    def test_symlink_source_refused(self):
        p = self.package/r.README;p.unlink();p.symlink_to(self.card/'.flippermce/settings.ini')
        with self.assertRaisesRegex(ValueError, 'escaped|Indirect'):
            r.package_files(self.package)


if __name__ == '__main__':
    unittest.main()

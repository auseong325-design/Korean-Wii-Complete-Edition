"""Candidate scope, input pinning and backup preservation on synthetic SD directories."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from kwce import dvd_prefetch_sd as sd
from kwce.priiloader_legacy import parse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import deploy_channel_package as copier


class PrefetchSDTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'workspace/private');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.pkg=self.root/'package';self.card=self.root/'card';self.card.mkdir()
        shutil.copytree(ROOT/'workspace/hardware/kwce-dvd-deferred-prefetch-v1',self.pkg)
        self.meta=json.loads((self.pkg/'package-manifest.json').read_text())
        for rel in self.meta['expected_inputs']:
            p=self.card/rel;p.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/'workspace/hardware/kwce-gc-card-encoding-v1'/rel,p)
        for rel in self.meta['runtime_inputs']:
            p=self.card/rel;p.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/'workspace/hardware/kwce-rc-sd-v38'/rel,p)
        (self.card/'keep.txt').write_text('synthetic unrelated file')
        for ctx in [patch.object(sd,'wii_mount'),patch.object(copier,'PRIVATE',self.root/'private')]:
            ctx.start();self.addCleanup(ctx.stop)

    def test_only_dvd_block_changes_gc_and_other_sections_stay_byte_identical(self):
        for rel in sd.TARGETS:
            old=(self.pkg/'expected'/rel).read_bytes();new=(self.pkg/rel).read_bytes()
            before,after=parse(old),parse(new)
            self.assertEqual([r['name']for r in before],[r['name']for r in after])
            for a,b in zip(old.split(b'['),new.split(b'[')):
                if not a.startswith(sd.DVD_GROUP.encode()+b']'):self.assertEqual(a,b)
            self.assertEqual(len(next(r for r in after if 'Japanese memory card encoding'in r['name'])['pairs']),3)
        sd.verify_card(self.pkg,self.card)

    def test_backup_three_updates_and_preserve_runtime_and_gc_only(self):
        before=copier.inventory(self.card)[0]
        sd.verify_card(self.pkg,self.card)
        copier.deploy(self.pkg,self.card,verifier=sd.sd_files)
        after=copier.inventory(self.card)[0]
        for rel in before:
            if rel not in sd.TARGETS:self.assertEqual(after[rel],before[rel])
        backups=list((self.card/'kwce-deploy-backups').glob('*'))
        self.assertEqual(len(backups),1)
        for rel in sd.TARGETS:
            self.assertEqual((backups[0]/rel).read_bytes(),(self.pkg/'expected'/rel).read_bytes())
            self.assertEqual((self.card/rel).read_bytes(),(self.pkg/rel).read_bytes())

    def test_changed_card_refused_before_any_writes(self):
        p=self.card/'kwce-rc/priiloader/gc-only.ini';p.write_bytes(p.read_bytes()+b'; changed\r\n')
        before=copier.inventory(self.card)[0]
        with self.assertRaisesRegex(ValueError,'changed since'):
            sd.verify_card(self.pkg,self.card)
        self.assertEqual(copier.inventory(self.card)[0],before)
        self.assertFalse((self.card/'kwce-deploy-backups').exists())

    def test_other_hack_change_refused_even_if_payload_hash_updated(self):
        rel='apps/Priiloader/hacks_hash.ini';p=self.pkg/rel
        data=p.read_bytes().replace(b'[KWCE GC: Wii/GC save menu]',b'[Changed section]')
        p.write_bytes(data);self.meta['files'][rel]=hashlib.sha256(data).hexdigest()
        raw=json.dumps(self.meta).encode();(self.pkg/'package-manifest.json').write_bytes(raw)
        (self.pkg/'package-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest())
        with self.assertRaisesRegex(ValueError,'changes more'):
            sd.sd_files(self.pkg)

    def test_dry_run_and_old_dvd_section_input_gate(self):
        before=copier.inventory(self.card)[0]
        sd.verify_card(self.pkg,self.card)
        copier.deploy(self.pkg,self.card,True,verifier=sd.sd_files)
        self.assertEqual(copier.inventory(self.card)[0],before)
        self.assertFalse((self.card/'kwce-deploy-backups').exists())
        with self.assertRaisesRegex(ValueError,'differs from frozen'):
            sd.upgrade_definition((self.pkg/'apps/Priiloader/hacks_hash.ini').read_bytes())


if __name__=='__main__':unittest.main()

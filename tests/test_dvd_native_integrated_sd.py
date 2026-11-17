"""Deployment boundary for the qualified integrated RAM service."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from kwce.dvd_integrated_sd import definition, upgrade, qualified, REQUIRED, ROOT
from kwce.priiloader_legacy import parse, apply_streaming
from kwce.priiloader_hacks import DVD_GROUP


class IntegratedSDTests(unittest.TestCase):
    def test_legacy_sequential_definition_matches_frozen_candidate(self):
        from kwce.gc_native import patch_gc_native
        menu=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
        base=patch_gc_native(menu,japanese_cards=True,japanese_comments=True)[0]
        self.assertEqual(apply_streaming(base,parse(definition())),
                         (ROOT/'workspace/experiments/dvd-native-hook-v66/menu.dol').read_bytes())

    def test_upgrade_preserves_all_other_sections_and_gc_encoding(self):
        for rel in ('kwce-rc/priiloader/gc-dvd.ini','kwce-rc/priiloader/fragment-gc-dvd.ini'):
            old=(ROOT/'workspace/hardware/kwce-dvd-read-control-v1'/rel).read_bytes()
            a,b=parse(old),parse(upgrade(old))
            self.assertEqual([r for r in a if r['name']!=DVD_GROUP],[r for r in b if r['name']!=DVD_GROUP])
            self.assertEqual([r['name']for r in a],[r['name']for r in b])

    def test_wrong_previous_definition_refused(self):
        for name in ('kwce-dvd-icon-cache-v1','kwce-dvd-stock-thumbnail-v1'):
            raw=(ROOT/'workspace/hardware'/name/'kwce-rc/priiloader/gc-dvd.ini').read_bytes()
            with self.assertRaises(ValueError):upgrade(raw)

    def test_incomplete_or_mismatched_qualification_refused(self):
        folder=ROOT/'workspace/experiments/dvd-native-hook-v66'
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        good=dict(revision=66,source_revision=37,sha256=sha(folder/'menu.dol'),
                  card_encoding_sha256=sha(folder/'menu-with-card-encoding.dol'),
                  physical_dvd_verified=False,checks={k:True for k in REQUIRED},
                  evidence={'workspace/experiments/dvd-native-hook-v66/manifest.json':sha(folder/'manifest.json')})
        with tempfile.TemporaryDirectory()as d:
            p=Path(d)/'qualification.json';p.write_text(json.dumps(good));qualified(p)
            for key in REQUIRED:
                bad={**good,'checks':{**good['checks'],key:False}};p.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):qualified(p)
            for field,value in [('sha256','bad'),('revision',64),('source_revision',35),
                                ('physical_dvd_verified',True),('evidence',{})]:
                p.write_text(json.dumps({**good,field:value}))
                with self.assertRaises(ValueError):qualified(p)

    def test_old_generic_export_cannot_bypass_integrated_gate(self):
        from kwce.dvd_native_hardware import entry
        menu=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
        with self.assertRaisesRegex(ValueError,'qualification'):
            entry(menu,{'hook':'dvd-native-hook-v66'})


if __name__=='__main__':unittest.main()

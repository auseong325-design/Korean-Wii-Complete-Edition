"""Trace update must retain all non-DVD definitions and require qualification."""
import json
import tempfile
import unittest
from pathlib import Path
from kwce.dvd_player_trace_sd import ROOT, TARGETS, upgrade, qualified, sha
from kwce.dvd_integrated_sd import REQUIRED
from kwce.priiloader_legacy import parse
from kwce.priiloader_hacks import DVD_GROUP


class TraceSDTests(unittest.TestCase):
    def test_disable_polarity_upgrade_preserves_other_hacks(self):
        for rel in TARGETS:
            raw=(ROOT/'workspace/hardware/kwce-dvd-player-trace-v5'/rel).read_bytes()
            before,after=parse(raw),parse(upgrade(raw,71,72))
            self.assertEqual([x['name']for x in before],[x['name']for x in after])
            self.assertEqual([x for x in before if x['name']!=DVD_GROUP],
                             [x for x in after if x['name']!=DVD_GROUP])
        with self.assertRaises(ValueError):upgrade(raw,70,72)

    def test_first_read_upgrade_preserves_other_hacks(self):
        for rel in TARGETS:
            raw=(ROOT/'workspace/hardware/kwce-dvd-player-trace-v4'/rel).read_bytes()
            before,after=parse(raw),parse(upgrade(raw,70,71))
            self.assertEqual([x['name']for x in before],[x['name']for x in after])
            self.assertEqual([x for x in before if x['name']!=DVD_GROUP],
                             [x for x in after if x['name']!=DVD_GROUP])
        with self.assertRaises(ValueError):upgrade(raw,69,71)

    def test_exact_read_upgrade_preserves_other_hacks(self):
        for rel in TARGETS:
            raw=(ROOT/'workspace/hardware/kwce-dvd-player-trace-v3'/rel).read_bytes()
            before,after=parse(raw),parse(upgrade(raw,69,70))
            self.assertEqual([x['name']for x in before],[x['name']for x in after])
            self.assertEqual([x for x in before if x['name']!=DVD_GROUP],
                             [x for x in after if x['name']!=DVD_GROUP])
        with self.assertRaises(ValueError):upgrade(raw,68,70)

    def test_dvd_permission_upgrade_preserves_other_hacks(self):
        for rel in TARGETS:
            raw=(ROOT/'workspace/hardware/kwce-dvd-player-trace-v2'/rel).read_bytes()
            before,after=parse(raw),parse(upgrade(raw,68,69))
            self.assertEqual([x['name']for x in before],[x['name']for x in after])
            self.assertEqual([x for x in before if x['name']!=DVD_GROUP],
                             [x for x in after if x['name']!=DVD_GROUP])
        with self.assertRaises(ValueError):upgrade(raw,67,69)

    def test_failure_return_upgrade_preserves_other_hacks(self):
        for rel in TARGETS:
            raw=(ROOT/'workspace/hardware/kwce-dvd-player-trace-v1'/rel).read_bytes()
            before,after=parse(raw),parse(upgrade(raw,67,68))
            self.assertEqual([x['name']for x in before],[x['name']for x in after])
            self.assertEqual([x for x in before if x['name']!=DVD_GROUP],
                             [x for x in after if x['name']!=DVD_GROUP])
        with self.assertRaises(ValueError):upgrade(raw,66,68)
    def test_all_three_definitions_preserve_gc_and_other_hacks(self):
        for rel in TARGETS:
            raw=(ROOT/'workspace/hardware/kwce-dvd-integrated-v1'/rel).read_bytes()
            before,after=parse(raw),parse(upgrade(raw))
            self.assertEqual([x['name'] for x in before],[x['name'] for x in after])
            self.assertEqual([x for x in before if x['name']!=DVD_GROUP],
                             [x for x in after if x['name']!=DVD_GROUP])

    def test_stale_or_already_updated_inputs_rejected(self):
        raw=(ROOT/'workspace/hardware/kwce-dvd-integrated-v1/kwce-rc/priiloader/gc-dvd.ini').read_bytes()
        with self.assertRaises(ValueError):upgrade(upgrade(raw))
        old=(ROOT/'workspace/hardware/kwce-dvd-read-control-v1/kwce-rc/priiloader/gc-dvd.ini').read_bytes()
        with self.assertRaises(ValueError):upgrade(old)

    def test_candidate_qualification_bound_to_revision_and_evidence(self):
        folder=ROOT/'workspace/experiments/dvd-native-hook-v67'
        proof=dict(revision=67,source_revision=37,physical_dvd_verified=False,
                   sha256=sha(folder/'menu.dol'),card_encoding_sha256=sha(folder/'menu-with-card-encoding.dol'),
                   checks={k:True for k in REQUIRED},
                   evidence={'workspace/experiments/dvd-native-hook-v67/manifest.json':sha(folder/'manifest.json')})
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'qualification.json';p.write_text(json.dumps(proof));qualified(p,67)
            with self.assertRaises(ValueError):qualified(p,66)
            for key in REQUIRED:
                p.write_text(json.dumps({**proof,'checks':{**proof['checks'],key:False}}))
                with self.assertRaises(ValueError):qualified(p,67)


if __name__=='__main__':unittest.main()

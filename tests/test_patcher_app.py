"""Windows patcher wizard v6+ (kwce/patcher_app.py) and the version-neutral Priiloader profiles."""
import hashlib
import io
import json
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path

from kwce import patcher_app as pa
from kwce import priiloader_profile as pr

ROOT = Path(__file__).resolve().parents[1]
FRAG_DVD = b'[KWCE DVD: disc channel DVD player]\r\nmaxversion=518\r\nminversion=518\r\namount=1\r\n' \
           b'hash=0x38000000\r\npatch=0x47000000,0x00474300,0x2e617263\r\n'
FRAG_GC = b'[KWCE GC: Wii/GC save menu]\r\nmaxversion=518\r\nminversion=518\r\namount=1\r\n' \
          b'hash=0x38000000\r\npatch=0x38000001\r\n'
DATA = {
    'KWCE-RC-README-ko.txt': b'readme',
    'apps/kwce-installer-rc/boot.dol': b'installer',
    'kwce/dvd/player.dol': b'player',
    'kwce-rc/priiloader/fragment-gc-dvd.ini': FRAG_DVD,
    'kwce-rc/priiloader/fragment-gc-only.ini': FRAG_GC,
    'kwce-rc/packages.txt': b'# header\nforecast|0001000248414645|Forecast Channel|0|0\n'
                            b'dvd-player|000100014b445644|DVD Player (legacy)|0|0|1\n',
    'kwce-rc/forecast/korean.wad': b'wad',
}


def manifest():
    m = {'files': {k: {'sha256': hashlib.sha256(v).hexdigest(), 'size': len(v), 'mode': 'verbatim'} for k, v in DATA.items()}}
    m['_packages'] = DATA['kwce-rc/packages.txt'].decode()
    return m


def fake_apply(bundle, work, cache, plan, log):
    for i, rel in enumerate(sorted(plan.files), 1):
        p = Path(work) / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(DATA[rel])
        log(f'  [{i}/{len(plan.files)}] {rel}')
    for rel, data in plan.extras.items():
        p = Path(work) / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)


def quiet(fn, *a, **k):
    with redirect_stdout(io.StringIO()) as s:
        r = fn(*a, **k)
    return r, s.getvalue()


class ProfileTest(unittest.TestCase):
    def test_neutral_tokens_same_bytes_in_both_parsers(self):
        text = pr.neutral_fragment(FRAG_DVD.decode())
        line = [l for l in text.split('\n') if l.startswith('patch=')][0][6:].split(',')
        legacy = b''.join(pr.legacy_bytes(t) for t in line)
        self.assertEqual(legacy, b''.join(pr.modern_bytes(t) for t in line))
        self.assertEqual(legacy, bytes.fromhex('47000000') + bytes.fromhex('474300') + bytes.fromhex('2e617263'))
        self.assertFalse(any(t[2:4] == '00' for t in line))

    def test_card_hacks_kept_and_old_kwce_replaced(self):
        card = b'# comment\r\n[Block Disc Updates]\r\nmaxversion=518\r\nminversion=512\r\namount=1\r\n' \
               b'hash=0x2c030000\r\npatch=0x60000000\r\n[KWCE GC: old]\r\nmaxversion=518\r\nminversion=518\r\n'
        out = pr.build_profile(card, FRAG_GC)
        self.assertTrue(out.startswith(b'[Block Disc Updates]\r\n'))
        self.assertNotIn(b'KWCE GC: old', out)
        self.assertIn(b'[KWCE GC: Wii/GC save menu]', out)
        self.assertEqual(pr.build_profile(None, FRAG_GC).split(b'\r\n')[0], b'[KWCE GC: Wii/GC save menu]')

    @unittest.skipUnless((ROOT / 'workspace/hardware/kwce-rc-sd-v53').is_dir(), 'package not present')
    def test_real_fragments_match_tested_legacy_bytes(self):
        from kwce.priiloader_legacy import parse
        from kwce.rc_hardware import merge_disc_profile
        for mode in ('gc-only', 'gc-dvd'):
            frag = (ROOT / f'workspace/hardware/kwce-rc-sd-v53/kwce-rc/priiloader/fragment-{mode}.ini').read_bytes()
            self.assertEqual(parse(merge_disc_profile(b'', frag)), parse(pr.build_profile(None, frag)))


class WizardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name); self.m = manifest()

    def tearDown(self):
        self.tmp.cleanup()

    def run_plan(self, mode, sd):
        plan = pa.Plan(self.m, mode); out = self.d / pa.OUT_NAMES[mode]
        quiet(pa.build, self.d, out, self.d / 'c', plan, True, apply=fake_apply)
        r, text = quiet(pa.copy_to, out, sd, plan, True)
        return plan, out, text

    def test_gc_plan_has_no_channels(self):
        plan = pa.Plan(self.m, 'gc')
        self.assertNotIn('kwce-rc/forecast/korean.wad', plan.files)
        self.assertIn('kwce/dvd/player.dol', plan.files)
        self.assertEqual(plan.extras['kwce-rc/packages.txt'],
                         b'# header\ndvd-player|000100014b445644|DVD Player (legacy)|0|0|1\n')

    def test_gc_copy_writes_profiles_and_keeps_card_hacks(self):
        sd = self.d / 'sd'; (sd / 'apps/priiloader').mkdir(parents=True)
        card = b'[My Hack]\r\nmaxversion=518\r\nminversion=512\r\namount=1\r\nhash=0x1\r\npatch=0x2\r\n'
        (sd / 'apps/priiloader/hacks_hash.ini').write_bytes(card)
        plan, out, text = self.run_plan('gc', sd)
        prof = (sd / 'kwce-rc/priiloader/gc-dvd.ini').read_bytes()
        self.assertTrue(prof.startswith(card))
        self.assertEqual((sd / 'apps/priiloader/hacks_hash.ini').read_bytes(), card)   # card file untouched
        self.assertTrue((sd / 'kwce-rc/wiilink-skip.txt').is_file())
        self.assertFalse((sd / 'kwce-rc/forecast').exists())
        self.assertIn('Priiloader 핵 1개는 그대로', text)

    def test_gc_on_full_card_keeps_channel_list(self):
        sd = self.d / 'sd'; sd.mkdir()
        self.run_plan('full', sd)
        self.run_plan('gc', sd)
        self.assertIn(b'forecast|', (sd / 'kwce-rc/packages.txt').read_bytes())

    def test_full_copy_without_card_file(self):
        sd = self.d / 'sd'; sd.mkdir(); (sd / 'notes.txt').write_text('mine')
        plan, out, text = self.run_plan('full', sd)
        self.assertEqual((sd / 'notes.txt').read_text(), 'mine')
        self.assertTrue((sd / 'kwce-rc/priiloader/gc-only.ini').read_bytes().startswith(b'[KWCE GC:'))
        self.assertTrue((sd / 'apps/priiloader').is_dir())
        self.assertFalse((sd / 'kwce-rc/wiilink-skip.txt').exists())
        self.assertIn('KWCE 항목만', text)

    def test_reuse_and_network_failure(self):
        plan = pa.Plan(self.m, 'full'); out = self.d / pa.OUT_NAMES['full']
        quiet(pa.build, self.d, out, self.d / 'c', plan, True, apply=fake_apply)
        _, text = quiet(pa.build, self.d, out, self.d / 'c', plan, True, apply=lambda *a: self.fail('reuse'))
        self.assertIn('다시 만들지 않습니다', text)
        def bad(bundle, work, cache, plan, log):
            Path(work).mkdir(parents=True); raise urllib.error.URLError('offline')
        with self.assertRaises(pa.Quit) as e:
            quiet(pa.build, self.d, self.d / 'other', self.d / 'c', plan, True, apply=bad)
        self.assertIn('인터넷 연결', str(e.exception))
        self.assertFalse((self.d / 'other').exists() or (self.d / pa.WORK_NAME).exists())


if __name__ == '__main__':
    unittest.main()

"""Windows patcher entries: v1 (kwce/patcher_entry_v1.py, packages v1-v4) and the v5 wizard (kwce/patcher_entry.py)."""
import hashlib
import io
import json
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path

from kwce import patcher_entry as pe
from kwce import patcher_entry_v1 as pe1

DATA = {'a.txt': b'alpha', 'kwce-rc/forecast/korean.wad': b'wad-bytes'}


def make_bundle(root):
    b = Path(root) / 'bundle'; b.mkdir()
    files = {k: {'sha256': hashlib.sha256(v).hexdigest(), 'size': len(v)} for k, v in DATA.items()}
    (b / 'manifest.json').write_text(json.dumps({'source_package': 'kwce-rc-sd-v0', 'files': files}))
    return b, {'files': files}


def good_apply(bundle, work, cache, log):
    for i, (rel, data) in enumerate(DATA.items(), 1):
        p = Path(work) / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
        log(f'  [{i}/{len(DATA)}] {rel}')
    return {'files': DATA}


class V1EntryTest(unittest.TestCase):
    def test_failure_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as d:
            b, _ = make_bundle(d); out = Path(d) / pe1.OUT_NAME; lines = []

            def bad(bundle, work, cache, log):
                work.mkdir(parents=True); (work / 'half').write_text('x'); raise ValueError('hash differs')
            self.assertEqual(pe1.run(b, out, Path(d) / 'c', apply=bad, log=lines.append), 1)
            self.assertFalse(out.exists() or (Path(d) / pe1.WORK_NAME).exists())

    def test_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as d:
            b, _ = make_bundle(d); out = Path(d) / pe1.OUT_NAME; out.mkdir(); (out / 'old').write_text('keep')
            self.assertEqual(pe1.run(b, out, Path(d) / 'c', apply=lambda *a: self.fail(), log=lambda s: None), 1)


class WizardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name)
        self.bundle, self.m = make_bundle(self.d); self.out = self.d / pe.OUT_NAME

    def tearDown(self):
        self.tmp.cleanup()

    def quiet(self, fn, *a, **k):
        with redirect_stdout(io.StringIO()) as s:
            r = fn(*a, **k)
        return r, s.getvalue()

    def test_build_then_reuse(self):
        self.quiet(pe.build, self.bundle, self.out, self.d / 'c', self.m, True, apply=good_apply)
        self.assertTrue(pe.output_ok(self.out, self.m))
        _, text = self.quiet(pe.build, self.bundle, self.out, self.d / 'c', self.m, True,
                             apply=lambda *a: self.fail('must reuse'))
        self.assertIn('다시 만들지 않습니다', text)

    def test_failed_build_leaves_nothing(self):
        def bad(bundle, work, cache, log):
            Path(work).mkdir(parents=True); raise urllib.error.URLError('offline')
        with self.assertRaises(pe.Quit) as e:
            self.quiet(pe.build, self.bundle, self.out, self.d / 'c', self.m, True, apply=bad)
        self.assertIn('인터넷 연결', str(e.exception))
        self.assertFalse(self.out.exists() or (self.d / pe.WORK_NAME).exists())

    def test_copy_adds_and_replaces_never_deletes(self):
        self.quiet(pe.build, self.bundle, self.out, self.d / 'c', self.m, True, apply=good_apply)
        sd = self.d / 'sd'; (sd / 'kwce-rc/forecast').mkdir(parents=True)
        (sd / 'kwce-rc/forecast/korean.wad').write_bytes(b'old')          # older KWCE file -> replaced
        (sd / 'kwce-rc/log.txt').write_text('user log')                     # not ours -> kept
        (sd / 'a.txt').write_bytes(b'alpha')                                # already same -> untouched
        ok, text = self.quiet(pe.copy_to, self.out, sd, self.m, True)
        self.assertTrue(ok)
        self.assertEqual((sd / 'kwce-rc/forecast/korean.wad').read_bytes(), b'wad-bytes')
        self.assertEqual((sd / 'kwce-rc/log.txt').read_text(), 'user log')
        self.assertIn('이미 같은 파일 1개', text)

    def test_progress_names_channels(self):
        _, text = self.quiet(pe.Progress(2), '  [1/2] kwce-rc/forecast/korean.wad')
        self.assertIn('날씨 채널 패치 중', text)

    def test_choose_target_none(self):
        self.assertIsNone(pe.choose_target([], 'none', True))
        r, _ = self.quiet(pe.choose_target, [{'path': 'E:\\', 'label': 'WII', 'fs': 'FAT32', 'free': 8e9,
                                              'removable': True, 'has_apps': True}], None, True)
        self.assertEqual(r, 'E:\\')


if __name__ == '__main__':
    unittest.main()

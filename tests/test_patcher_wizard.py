"""Windows patcher wizard v7+ (kwce/patcher_wizard.py): other-PC robustness and the revert guide."""
import io
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from kwce import patcher_wizard as pw
from tests.test_patcher_app import DATA, fake_apply, manifest


def quiet(fn, *a, **k):
    with redirect_stdout(io.StringIO()) as s:
        r = fn(*a, **k)
    return r, s.getvalue()


class WizardV7Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name); self.m = manifest()

    def tearDown(self):
        self.tmp.cleanup()

    def test_retries_network_errors_only(self):
        calls = []

        def flaky(*a):
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionResetError('dropped')
            return 'ok'
        r, text = quiet(pw.with_retries(flaky, wait=0))
        self.assertEqual((r, len(calls)), ('ok', 3))
        self.assertIn('다시 시도합니다', text)
        with self.assertRaises(ValueError):
            pw.with_retries(mock.Mock(side_effect=ValueError('bad hash')), wait=0)()

    def test_permission_error_explained(self):
        plan = pw.Plan(self.m, 'full')

        def denied(*a):
            raise PermissionError('blocked')
        with self.assertRaises(pw.Quit) as e:
            quiet(pw.build, self.d, self.d / 'out', self.d / 'c', plan, True, apply=denied)
        self.assertIn('랜섬웨어 방지', str(e.exception))

    def test_low_disk_space_stops_before_work(self):
        plan = pw.Plan(self.m, 'full')
        with mock.patch('shutil.disk_usage', return_value=mock.Mock(free=10)):
            with self.assertRaises(pw.Quit) as e:
                quiet(pw.build, self.d, self.d / 'out', self.d / 'c', plan, True, apply=fake_apply)
        self.assertIn('저장 공간이 부족', str(e.exception))
        self.assertFalse((self.d / 'out').exists())

    def test_sd_write_protect_explained(self):
        plan = pw.Plan(self.m, 'gc'); out = self.d / pw.OUT_NAMES['gc']
        quiet(pw.build, self.d, out, self.d / 'c', plan, True, apply=fake_apply)
        sd = self.d / 'sd'; sd.mkdir()
        with mock.patch('shutil.copyfile', side_effect=PermissionError('locked')):
            with self.assertRaises(pw.Quit) as e:
                quiet(pw.copy_to, out, sd, plan, True)
        self.assertIn('잠금 스위치', str(e.exception))

    def test_non_root_target_skips_fs_check(self):
        self.assertEqual(pw.volume_fs(self.d), '')

    def test_revert_guide_checks_card(self):
        sd = self.d / 'sd'; (sd / 'kwce-rc/state').mkdir(parents=True)
        (sd / 'kwce-rc/state/forecast.txt').write_text('before=0 version=-1\n')
        (sd / 'kwce-rc/state/wiispeak.txt').write_text('before=1 version=512\n')
        _, text = quiet(pw.revert_guide, sd)
        self.assertIn('복원 기록: 채널 2개', text)
        self.assertIn('설치 도구: 없음', text)
        self.assertIn('1번(빠른 설정)', text)            # installer and the Wii Speak original are missing
        self.assertIn('+(START) → 2(전체 복원)', text)
        self.assertEqual(pw.sd_records(sd), {'forecast': 'removed', 'wiispeak': 'original'})
        self.assertEqual(sorted(p.name for p in sd.rglob('*')), ['forecast.txt', 'kwce-rc', 'state', 'wiispeak.txt'])

    def test_revert_mode_writes_nothing(self):
        sd = self.d / 'sd'; sd.mkdir()
        bundle = self.d / 'bundle'; (bundle / 'files/kwce-rc').mkdir(parents=True)
        (bundle / 'manifest.json').write_text('{"files": {}}')
        r, text = quiet(pw.main, ['--bundle', str(bundle), '--mode', 'revert', '--sd', str(sd), '--yes'])
        self.assertEqual(r, 0)
        self.assertEqual(list(sd.iterdir()), [])
        self.assertIn('되돌리기', text)


class ScreenTest(unittest.TestCase):
    def test_progress_line_leaves_no_old_characters(self):
        p = pw.Progress(2)
        _, text = quiet(lambda: (p('  [1/2] kwce-rc/personal-data/korean.wad'), p('  받는 중: Forecast Channel (USA)')))
        bar, dl = text.split('\r')[1], text.split('\r')[2].rstrip('\n')
        self.assertGreaterEqual(pw.width(dl), pw.width(bar))      # the shorter line is padded over the old one
        self.assertEqual(pw.width('주소'), 4)

    def test_scripted_answers_look_typed(self):
        pw.ANSWERS[:] = ['2', 'x']
        try:
            r1, t1 = quiet(pw.ask, '  번호:', ['1', '2'], '1', True)
            r2, _ = quiet(pw.ask, '  번호:', ['1', '2'], '1', True)
        finally:
            pw.ANSWERS[:] = []
        self.assertEqual((r1, r2), ('2', '1'))                    # an invalid scripted answer falls back to the default
        self.assertEqual(t1.strip(), '번호: [기본 1] 2')
        self.assertEqual(pw.gb(200_000), '1MB 미만')


class UsageAndSntpTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_readme_numbers_match_measurement(self):
        import json, re
        u = json.loads((self.ROOT / 'configs/nand-usage-v1.json').read_text(encoding='utf-8'))
        readme = (self.ROOT / 'docs/release/patcher-win-README-v8-ko.txt').read_text(encoding='utf-8')
        names = {'forecast': '날씨', 'news': '뉴스', 'votes': '모두의 투표', 'mii-contest': 'Mii 콘테스트',
                 'wiiroom': 'Wii의 방', 'nintendo': '닌텐도', 'personal-data': '주소 설정', 'internet': '인터넷',
                 'kirbytv': '커비 TV', 'photoprints': '사진 프린트', 'food': '음식 배달', 'wiispeak': 'Wii 스피크',
                 'tvguide': 'TV 가이드'}
        for c in u['channels']:
            self.assertRegex(readme, re.escape(names[c['id']]) + r' ' + str(c['content_blocks'] + c['data_blocks']) + r'\b')
        self.assertIn(f"{round(u['total']['blocks'], -1):,}블록", readme)
        self.assertIn(pw.usage_line(u).split('(')[0].strip(), '빠른 설정 ' + pw.usage_line(u))

    def test_finish_recommends_sntp_for_full_only(self):
        with tempfile.TemporaryDirectory() as d:
            m = manifest()
            _, full = quiet(pw.finish, Path(d), None, False, pw.Plan(m, 'full'), True)
            _, gc = quiet(pw.finish, Path(d), None, False, pw.Plan(m, 'gc'), True)
        self.assertIn('sntp', full)
        self.assertIn('UTC+9', full)
        self.assertNotIn('sntp', gc)


if __name__ == '__main__':
    unittest.main()

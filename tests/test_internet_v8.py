"""Internet Channel revision 8: error messages broken for the error dialog text column.

Synthetic tests always run. Tests marked 'local data' use the project's own ignored
originals/builds and are skipped when those files are absent.
"""
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import internet_error_dialog as ed  # noqa: E402

BASE = ROOT / 'workspace/channels/internet'
ORIGINAL = BASE / 'originals/internet-usa-v1024.wad'
LOCAL, HARDWARE = 'internet-ko-local-test.wad', 'internet-ko-hardware-candidate.wad'
B = ed.BREAK


class CharMetrics:
    """1 em per character ('%s' counts as the placeholder)."""

    def em(self, text):
        return float(len(text.replace('%s', ed.PLACEHOLDER)))

    def limit(self):
        return 100.0


class DialogModel(unittest.TestCase):
    def test_column_and_limit(self):
        self.assertAlmostEqual(ed.column_em(ed.LAYOUTS['16:9']), 307 / 22)
        self.assertAlmostEqual(ed.column_em(ed.LAYOUTS['4:3']), 409 / 30)
        self.assertAlmostEqual(ed.limit(), 409 / 30 * ed.SAFETY / ed.BOLD_FACTOR)
        # the observed v7 fit (13.31 em in the 13.95 em 16:9 column) bounds the bold factor
        self.assertLessEqual(13.3057 * ed.BOLD_FACTOR, 307 / 22 + 0.02)

    def test_penalties(self):
        for a, b in (('찾을', '수'), ('수', '없습니다.'), ('지원하지', '않는'), ('보내지', '못했습니다.'),
                     ('더', '이상'), ('불러와', '주세요.'), ('들어', '있는'), ('이동하려고', '합니다.')):
            self.assertEqual(ed.penalty(a, b, None), ed.HARD, (a, b))
        self.assertEqual(ed.penalty('이', '주소는', None), ed.DETERMINER)
        self.assertEqual(ed.penalty('HTTP', '요청', None), ed.STRONG)
        self.assertEqual(ed.penalty('인터넷', '채널에서는', None), ed.STRONG)
        self.assertEqual(ed.penalty('다시', '불러와', None), ed.ADVERB)
        self.assertEqual(ed.penalty('주소', '형식입니다.', None), ed.NOUN)
        self.assertEqual(ed.penalty('240019:', '알', '240019:'), ed.CODE_ALONE)
        self.assertEqual(ed.penalty('없거나', '지원하지', None), 0)
        self.assertEqual(ed.penalty('부족해', 'Flash', None), 0)

    def test_spaces_to_breaks(self):
        self.assertEqual(ed.spaces_to_breaks('가 나 다', f'가{B}나 다'), 1)
        self.assertEqual(ed.spaces_to_breaks(f'가 나{B}다 라', f'가{B}나{B}다{B}라'), 2)
        self.assertEqual(ed.spaces_to_breaks('a: %s ', 'a: %s '), 0)
        for old, new in (('가 나', '가나'), ('가  나', f'가 {B}나'), ('가 나', f'가{B}{B}나'), ('가 나', f'{B}가 나'),
                         ('가 나', '가 너'), (f'가{B}나', '가 나')):
            with self.assertRaises(ValueError, msg=(old, new)):
                ed.spaces_to_breaks(old, new)

    def test_split_prefers_phrase_boundaries(self):
        m = CharMetrics()
        # 8-char lines: '할 수 없습니다' must not split; the break goes before it
        lines, cost = ed.split_segment('이 파일에 접근할 수 없습니다.', m, 11, None)
        self.assertEqual(lines, ['이 파일에', '접근할 수 없습니다.'])
        self.assertEqual(cost, 0)
        with self.assertRaises(ValueError):
            ed.split_segment('가나다라마바사아자차카', m, 5, None)

    def test_plan_sets_code_apart_when_the_sentence_fits(self):
        m = CharMetrics()
        width = ed.limit()
        text = '240023: ' + '가' * int(width)  # sentence fits one line, code + sentence does not
        rows = ed.plan({'0': text, '1': '그냥 문장'}, m)
        self.assertEqual(rows['0']['ko'], '240023:' + B + '가' * int(width))
        self.assertNotIn('1', rows)
        report = ed.check(rows, {'0': text, '1': '그냥 문장'}, m)
        self.assertEqual((report['coded_messages'], report['changed'], report['max_lines']), (1, 1, 2))

    def test_check_refuses_too_wide_or_reworded(self):
        m = CharMetrics()
        text = '240019: ' + '가' * 20
        with self.assertRaises(ValueError):
            ed.check({}, {'0': text}, m)  # coded message left wider than the column
        with self.assertRaises(ValueError):
            ed.check({'0': dict(v1=text, ko='240019:' + B + '나' * 20)}, {'0': text}, m)

    def test_layouts_refuse_other_geometry(self):
        class Archive:
            def __init__(self, files):
                self.files = files

            def get(self, name):
                return self.files[name].encode('utf-8')

        def css(font, msg, margin, icon):
            return (f'.dialog {{\n  font-weight:bold;\n  font-size:{font}px;\n}}\n#notificationImg {{\n  float: left;\n'
                    f'  margin-left: {icon[0]}px;\n  width: {icon[1]}px;\n  margin-right:{icon[2]}px;\n}}\n'
                    f'p {{\n  margin:{margin}px;\n}}\n#message \n{{\n    width: {msg}px;\n}}\n')
        font = "html, body {\n  font-family: 'Wii NTLG PGothic Regular', sans-serif;\n}\n"
        js = ('text.split("\\n") loadCSS("styles/dialog16x9") loadCSS("styles/dialog") '
              'loadCSS("styles/stylesWideScreen/wii") loadCSS("styles/wii")')
        files = {'dialog.js': js, 'styles/wii.css': font, 'styles/stylesWideScreen/wii.css': font,
                 'styles/dialog16x9.css': css(22, 425, 2, (30, 64, 22)), 'styles/dialog.css': css(30, 567, 3, (40, 85, 30))}
        found = ed.layouts(Archive(files))
        self.assertEqual((found['16:9']['column_px'], found['4:3']['column_px']), (307, 409))
        files['styles/dialog.css'] = css(30, 600, 3, (40, 85, 30))
        with self.assertRaises(ValueError):
            ed.layouts(Archive(files))


def _wads(kind, revision):
    return BASE / f'{kind}-v{revision}' / (LOCAL if kind == 'build' else HARDWARE)


@unittest.skipUnless(ORIGINAL.exists() and all(_wads(k, r).exists() for k in ('build', 'hardware') for r in (6, 7, 8)),
                     'local data')
class Revision8(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kwce.channels import load_library
        cls.lib = load_library()
        cls.cfg = json.loads((ROOT / 'configs/internet-v8-ko.json').read_text(encoding='utf-8'))
        cls.lng = json.loads((ROOT / 'configs/internet-lng-v1-ko.json').read_text(encoding='utf-8'))['translations']

    def load(self, path):
        t = self.lib.title.Title()
        t.load_wad(path.read_bytes())
        return t

    def test_older_revisions_unchanged(self):
        for kind in ('build', 'hardware'):
            for revision in (6, 7):
                stored = json.loads((_wads(kind, revision).with_name('build-manifest.json')).read_text(encoding='utf-8'))
                self.assertEqual(hashlib.sha256(_wads(kind, revision).read_bytes()).hexdigest(), stored['wad_sha256'])

    def test_v8_changes_only_the_language_files(self):
        from kwce.channels import ChannelArchive
        from kwce import internet_error_headings as eh
        rows = self.cfg['error_breaks']
        self.assertEqual(len(rows), 35)
        for kind in ('build', 'hardware'):
            v6, v7, v8 = (self.load(_wads(kind, r)) for r in (6, 7, 8))
            changed = [i for i in range(v7.tmd.num_contents) if v7.get_content_by_index(i) != v8.get_content_by_index(i)]
            self.assertEqual(changed, [2, 6])  # content 1 (executable) identical to v7
            c2_7, c2_8 = ChannelArchive(v7.get_content_by_index(2)), ChannelArchive(v8.get_content_by_index(2))
            self.assertEqual(sorted(f for f in c2_8.files if c2_8.get(f) != c2_7.get(f)), ['english.lng'])
            text = ChannelArchive(v8.get_content_by_index(6)).get('english.lng').decode('utf-8')
            self.assertEqual(c2_8.get('english.lng').decode('utf-8'), text)
            restored = text
            counts = {}
            for row in rows.values():
                counts[row['ko']] = counts.get(row['ko'], 0) + 1  # 240023 is used by three entries
            for row in rows.values():
                self.assertEqual(text.count(f'="{row["ko"]}"'), counts[row['ko']])
                restored = restored.replace(f'="{row["ko"]}"', f'="{row["v1"]}"')
            # without the breaks the file is the v6 (v1 translation) language file
            self.assertEqual(restored, ChannelArchive(v6.get_content_by_index(6)).get('english.lng').decode('utf-8'))
            self.assertIn('white-space: pre-line;', c2_8.get('styles/error.css').decode('utf-8'))
            metrics = eh.Metrics(eh.opera_face(v8.get_content_by_index(4)))
            report = ed.check(rows, self.lng, metrics, c2_8)
            self.assertEqual((report['coded_messages'], report['changed']), (35, 35))
            self.assertLessEqual(report['widest_em'], report['limit_em'])
            self.assertEqual(report['layouts']['16:9']['column_px'], 307)
            self.assertEqual(v8.tmd.region, 4)
        # the lines the lead saw wrap inside a word
        self.assertEqual(rows['24']['ko'], f'240019: 알 수 없거나{B}지원하지 않는{B}주소 형식입니다.')
        self.assertEqual(rows['377']['ko'], f'240016: %s{B}프로토콜은{B}지원하지 않습니다.')

    def test_hardware_v8(self):
        from kwce.hardware import local_reference_counts
        hw = self.load(_wads('hardware', 8))
        self.assertEqual(local_reference_counts(hw), local_reference_counts(self.load(ORIGINAL)))
        self.assertTrue(hw.get_is_fakesigned())
        self.assertEqual(hw.tmd.region, 4)
        stored = json.loads(_wads('hardware', 8).with_name('build-manifest.json').read_text(encoding='utf-8'))
        self.assertFalse(stored['hardware_success_verified'] or stored['local_only'] or stored['installed_anywhere'])
        self.assertEqual(stored['tmd_region'], 4)

    def test_local_v8_reproduces(self):
        from kwce.internet_build import build
        wad, manifest = build(local=True, revision=8)
        stored = json.loads(_wads('build', 8).with_name('build-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(hashlib.sha256(wad).hexdigest(), stored['wad_sha256'])
        self.assertEqual(manifest['error_message_breaks']['changed'], 35)
        self.assertTrue(stored['local_only'])


if __name__ == '__main__':
    unittest.main()

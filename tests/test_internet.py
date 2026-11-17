"""Internet Channel Korean localization tests.

Synthetic tests always run. Tests marked 'local data' use the project's own
ignored originals/builds and are skipped when those files are absent.
"""
import hashlib
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import internet_manual as im  # noqa: E402
from kwce import internet_exe as ex  # noqa: E402
from kwce import internet_resources as res  # noqa: E402

ORIGINAL = ROOT / 'workspace/channels/internet/originals/internet-usa-v1024.wad'
BUILD = ROOT / 'workspace/channels/internet/build-v1'
HARDWARE = ROOT / 'workspace/channels/internet/hardware-v1'
FEED = ROOT / 'workspace/channels/internet/local-feed-v1'


def config(name):
    return json.loads((ROOT / f'configs/internet-{name}-v1-ko.json').read_text(encoding='utf-8'))


class ManualRuns(unittest.TestCase):
    HTML = ('<! DOCTYPE html ><html><head><title>PAGE 1</title><script>var a="Point";</script></head><body>'
            '<p>Point at <img src="a.png"> and press <img src="b.png">.<br>Next line</p></body></html>')

    def test_round_trip_and_templates(self):
        self.assertEqual(''.join(t[1] for t in im.tokens(self.HTML)), self.HTML)
        templates = [t for _, _, t, _ in im.runs(self.HTML)]
        self.assertEqual(templates, ['PAGE 1', 'Point at {0} and press {1}.', 'Next line'])

    def test_reorder_and_structure(self):
        mapping = {'Point at {0} and press {1}.': '포인터를 {0}에 맞추고 {1} 버튼을 누르세요.', 'PAGE 1': '1쪽'}
        used = set()
        out = im.localize_html(self.HTML, mapping, used)
        self.assertIn('포인터를 <img src="a.png">에 맞추고 <img src="b.png"> 버튼을 누르세요.<br>Next line', out)
        self.assertIn('var a="Point";', out)
        self.assertEqual(used, set(mapping))
        self.assertEqual(im.untranslated(self.HTML, mapping), ['Next line'])

    def test_placeholder_rules(self):
        with self.assertRaises(ValueError):
            im.fill('a {0} b {1}', ['<b>', '</b>'], '{1} x {0}')
        with self.assertRaises(ValueError):
            im.fill('a {0}', ['<img src="x">'], 'no placeholder')
        with self.assertRaises(ValueError):
            im.fill('{0}open', ['<span>'], 'x <i>{0}</i>')
        self.assertEqual(im.fill('{0}A{1}', ['<strong>', '</strong>'], '{0}가{1}'), '<strong>가</strong>')


class LanguageFile(unittest.TestCase):
    SRC = b'; c\n[Info]\nLanguage="en"\nLanguageName="English"\n[Translation]\n1="Hello %s"\n-2="Line\\nTwo"\n'

    def cfg(self, **tr):
        return dict(source_sha256=hashlib.sha256(self.SRC).hexdigest(), source_entries=2, info=dict(Language='ko', LanguageName='한국어'),
                    translations=tr or {'0': '안녕 %s', '1': '줄\\n둘'})

    def test_korean_lng(self):
        data, record = res.korean_lng(self.SRC, self.cfg())
        text = data.decode('utf-8')
        self.assertIn('Language="ko"', text)
        self.assertIn('1="안녕 %s"', text)
        self.assertIn('-2="줄\\n둘"', text)
        self.assertEqual(record['translated'], 2)

    def test_tokens_must_match(self):
        with self.assertRaises(ValueError):
            res.korean_lng(self.SRC, self.cfg(**{'0': '안녕', '1': '줄\\n둘'}))


class Executable(unittest.TestCase):
    def test_area_table(self):
        raw = b'\x01' * 16 + ex.AREA_TABLE + b'\x02' * 16
        out, record = ex.patch_area(raw)
        at = 16 + ex.KOR_ENTRY
        self.assertEqual(out[at:at + 5], b'\x01KOR\x00')
        self.assertEqual(len(out), len(raw))
        self.assertEqual(sum(a != b for a, b in zip(raw, out)), 1)
        with self.assertRaises(ValueError):
            ex.patch_area(raw + ex.AREA_TABLE)

    def test_local_urls(self):
        url = 'http://xml.opera.com/update/wii'
        raw = b'xx' + url.encode('utf-16-be') + b'\0\0' + b'http://searcher.wii.com/s?k=%s\0'
        rows = [dict(url=url, encoding='utf-16-be', count=1), dict(url='http://searcher.wii.com/s?k=%s', encoding='ascii', count=1)]
        out, records = ex.patch_local_urls(raw, rows)
        self.assertEqual(len(out), len(raw))
        self.assertIn('http://127.0.0.2/update/wii'.encode('utf-16-be') + b'\0\0', out)
        self.assertIn(b'http://127.0.0.2/s?k=%s\0', out)
        with self.assertRaises(ValueError):
            ex.patch_local_urls(raw, [dict(url=url, encoding='utf-16-be', count=2)])


class Resources(unittest.TestCase):
    def test_adr_round_trip(self):
        entries = res.adr_entries([('가', 'http://127.0.0.2/'), ('나', 'http://127.0.0.2/a')])
        data = res.write_adr(entries)
        self.assertTrue(data.startswith('가\nhttp://127.0.0.2/\n\n1.000000\n2.000000\n2.000000\n'.encode('utf-8')))
        self.assertEqual(res.parse_adr(data), entries)

    def test_csv_columns(self):
        rows = ['\t'.join(f'"{c}"' for c in ['jp', 'en', 'de', 'fr', 'es', 'it', 'nl', 'zh', 'en', f'한국어{r}']) for r in range(2)]
        data = b'\xfe\xff' + '\r\n'.join(rows).encode('utf-16-be')
        out, targets = res.korean_csv(data, 10, 9)
        self.assertEqual(targets, ['한국어0', '한국어1'])
        self.assertEqual(out[2:].decode('utf-16-be').count('한국어0'), 10)

    def test_textbox_buffer_kept(self):
        text = 'others'
        section = bytearray(116)
        section[:4] = b'txt1'
        section[12:18] = b'T_test'
        payload = (text + '\0').encode('utf-16-be')
        struct.pack_into('>HH', section, 76, len(payload), len(payload))
        struct.pack_into('>I', section, 88, 116)
        section += payload + bytes(-len(payload) % 4)
        struct.pack_into('>I', section, 4, len(section))
        new = res.set_textbox(bytes(section), '기호')
        from kwce.channels import textbox
        self.assertEqual(textbox(new), ('T_test', '기호'))
        self.assertEqual(struct.unpack_from('>H', new, 76)[0], len(payload))


class Configs(unittest.TestCase):
    def test_lng_table_complete(self):
        cfg = config('lng')
        self.assertEqual(sorted(map(int, cfg['translations'])), list(range(cfg['source_entries'])))

    def test_manual_kept_lists(self):
        cfg = config('manual')
        self.assertFalse(set(cfg['kept_english']) & set(cfg['translations']))
        self.assertEqual(len(cfg['kept_english']), 4)

    def test_hardware_keeps_urls(self):
        exe = config('exe')
        self.assertTrue(all(r['url'].startswith('http://') for r in exe['local_urls']))
        ui = config('ui')
        self.assertTrue(all(url.startswith('http://127.0.0.2/') for _, url in ui['favorites']['local_test']))


@unittest.skipUnless(ORIGINAL.exists() and (BUILD / 'internet-ko-local-test.wad').exists(), 'local data')
class Builds(unittest.TestCase):
    def test_local_build_reproduces(self):
        from kwce.internet_build import build
        for revision in (1, 2, 3, 4, 5, 6, 7):
            folder = ROOT / f'workspace/channels/internet/build-v{revision}'
            if not folder.exists():
                continue
            wad, manifest = build(local=True, revision=revision)
            stored = json.loads((folder / 'build-manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(hashlib.sha256(wad).hexdigest(), stored['wad_sha256'])
            self.assertEqual(manifest['changed_contents'], [0, 1, 2, 3, 4, 5, 6, 8])
            self.assertFalse(stored['full_localization_complete'] or stored['hardware_success_verified'])
            self.assertTrue(stored['local_only'])

    @unittest.skipUnless((HARDWARE / 'internet-ko-hardware-candidate.wad').exists(), 'local data')
    def test_hardware_candidate_has_no_loopback(self):
        from kwce.channels import load_library
        from kwce.hardware import local_reference_counts
        lib = load_library()
        orig = lib.title.Title()
        orig.load_wad(ORIGINAL.read_bytes())
        expected = local_reference_counts(orig)
        for revision in (1, 2, 3, 4, 5, 6, 7):
            folder = ROOT / f'workspace/channels/internet/hardware-v{revision}'
            if not folder.exists():
                continue
            hw = lib.title.Title()
            hw.load_wad((folder / 'internet-ko-hardware-candidate.wad').read_bytes())
            self.assertEqual(local_reference_counts(hw), expected)
            self.assertTrue(hw.get_is_fakesigned())
            stored = json.loads((folder / 'build-manifest.json').read_text(encoding='utf-8'))
            self.assertFalse(stored['hardware_success_verified'] or stored['local_only'])

    def test_undeclared_pages_are_ascii_in_v2(self):
        folder = ROOT / 'workspace/channels/internet/build-v2'
        if not folder.exists():
            self.skipTest('local data')
        from kwce.channels import load_library, ChannelArchive
        lib = load_library()
        t = lib.title.Title()
        t.load_wad((folder / 'internet-ko-local-test.wad').read_bytes())
        c2 = ChannelArchive(t.get_content_by_index(2))
        for name in ('about.html', 'authdialog.html', 'startpage/startpage.html'):
            data = c2.get(name)
            self.assertTrue(all(b < 128 for b in data), name)
            self.assertIn(b'&#', data)

    def test_v3_review_fixes(self):
        folder = ROOT / 'workspace/channels/internet/build-v3'
        if not folder.exists():
            self.skipTest('local data')
        from kwce.channels import load_library, ChannelArchive
        import io
        from fontTools.ttLib import TTCollection
        lib = load_library()
        t = lib.title.Title()
        t.load_wad((folder / 'internet-ko-local-test.wad').read_bytes())
        # (2/3) per-face TTC names restored so web content resolves the font
        col = TTCollection(io.BytesIO(ChannelArchive(t.get_content_by_index(4)).get('WiiNTLG-Regular.ttc')))
        full = [str(r) for f in col.fonts for r in f['name'].names if r.nameID == 4 and r.platformID == 3]
        self.assertIn('Wii NTLG PGothic Regular', full)
        self.assertIn('Wii NTLG Gothic Regular', full)
        # (1) first-run favorites import kept intact (4-line files.dat, test adr)
        c2 = ChannelArchive(t.get_content_by_index(2))
        self.assertEqual(len(c2.get('default_bookmarks/us_sp/files.dat').decode('utf-8').strip().split('\n')), 4)
        self.assertIn('127.0.0.2', c2.get('default_bookmarks/us_sp/append1.adr').decode('utf-8'))
        # (4) keyboard labels reverted to English (no Korean in the exe keyboard strings)
        from kwce.wiiroom_formats import decompress_lz11
        raw = decompress_lz11(t.get_content_by_index(1))
        self.assertNotIn('스페이스'.encode('utf-16-be'), raw)
        stored = json.loads((folder / 'build-manifest.json').read_text(encoding='utf-8'))
        self.assertFalse(stored['executable']['keyboard_translated'])

    def test_v4_review_fixes(self):
        local = ROOT / 'workspace/channels/internet/build-v4/internet-ko-local-test.wad'
        hardware = ROOT / 'workspace/channels/internet/hardware-v4/internet-ko-hardware-candidate.wad'
        if not (local.exists() and hardware.exists()):
            self.skipTest('local data')
        from kwce.channels import load_library, ChannelArchive
        lib = load_library()
        hints = json.loads((ROOT / 'configs/internet-v4-ko.json').read_text(encoding='utf-8'))['lng_keep_english']
        orig = lib.title.Title()
        orig.load_wad(ORIGINAL.read_bytes())
        o2 = ChannelArchive(orig.get_content_by_index(2))
        for wad, is_local in ((local, True), (hardware, False)):
            t = lib.title.Title()
            t.load_wad(wad.read_bytes())
            text = ChannelArchive(t.get_content_by_index(6)).get('english.lng').decode('utf-8')
            for english in hints.values():
                self.assertIn(f'="{english}"', text)  # keyboard input hints stay English
            self.assertIn('Language="ko"', text)
            c2 = ChannelArchive(t.get_content_by_index(2))
            self.assertEqual(c2.get('english.lng').decode('utf-8'), text)
            changed = c2.get('default_bookmarks/yahoo.bmp') != o2.get('default_bookmarks/yahoo.bmp')
            self.assertEqual(changed, is_local)  # test thumbnails in the local build only

    def test_v5_review_fixes(self):
        local = ROOT / 'workspace/channels/internet/build-v5/internet-ko-local-test.wad'
        hardware = ROOT / 'workspace/channels/internet/hardware-v5/internet-ko-hardware-candidate.wad'
        if not (local.exists() and hardware.exists()):
            self.skipTest('local data')
        from kwce.channels import load_library, ChannelArchive
        from kwce.wiiroom_formats import decompress_lz11
        lib = load_library()
        redirect = b'apps.digitalhomeservices.yahoo.com/gc/wii/v10/redirect.php?app=fav1&ctry=%s&lgge=%s\0'
        for wad, is_local in ((local, True), (hardware, False)):
            t = lib.title.Title()
            t.load_wad(wad.read_bytes())
            raw = decompress_lz11(t.get_content_by_index(1))
            self.assertEqual(redirect in raw, not is_local)  # hardware keeps the Yahoo! template
            self.assertNotIn(b'/gc/wii/v10/redirect.php', raw if is_local else b'')
            for index, names in ((2, ['operarc', 'operarc.nand']), (3, ['operarc.nand']), (6, ['operarc'])):
                arc = ChannelArchive(t.get_content_by_index(index))
                for name in names:
                    text = arc.get(name).decode('utf-8')
                    self.assertIn('[User Prefs]\nFallback HTML Encoding=euc-kr\n', text, f'{index}/{name}')
                    self.assertEqual(text.count('Fallback HTML Encoding'), 1)

    def test_v6_review_fixes(self):
        local = ROOT / 'workspace/channels/internet/build-v6/internet-ko-local-test.wad'
        hardware = ROOT / 'workspace/channels/internet/hardware-v6/internet-ko-hardware-candidate.wad'
        hw5 = ROOT / 'workspace/channels/internet/hardware-v5/internet-ko-hardware-candidate.wad'
        if not (local.exists() and hardware.exists() and hw5.exists()):
            self.skipTest('local data')
        import io
        import re
        from kwce.channels import load_library, ChannelArchive
        from kwce.wiiroom_formats import decompress_lz11
        from kwce import internet_keyboard_font as kf
        from PIL import Image
        lib = load_library()
        v6 = json.loads((ROOT / 'configs/internet-v6-ko.json').read_text(encoding='utf-8'))
        pictures = json.loads((ROOT / 'configs/internet-manual-images-v6-ko.json').read_text(encoding='utf-8'))
        lng = config('lng')['translations']
        orig = lib.title.Title()
        orig.load_wad(ORIGINAL.read_bytes())
        o2 = ChannelArchive(orig.get_content_by_index(2))

        def load(path):
            t = lib.title.Title()
            t.load_wad(path.read_bytes())
            return t

        def urls(raw):
            ascii_urls = re.findall(rb'https?://[\x21-\x7e]+', raw)
            wide = [m.decode('utf-16-be') for m in re.findall(rb'\x00h\x00t\x00t\x00p(?:\x00s)?\x00:\x00/\x00/(?:\x00[\x21-\x7e])+', raw)]
            return sorted(u.decode('ascii') for u in ascii_urls), sorted(wide)

        t5 = load(hw5)
        for wad, is_local in ((local, True), (hardware, False)):
            t = load(wad)
            self.assertEqual(t.tmd.region, 4)  # Korean system menu accepts region 3 or 4 only
            # keyboard font: 'wii_name' also loads the KS X 1001 Hangul sheets; nothing else changed
            fonts, fonts5 = ChannelArchive(t.get_content_by_index(8)), ChannelArchive(t5.get_content_by_index(8))
            wbf1, wbf1_5 = fonts.get('wbf1.brfna'), fonts5.get('wbf1.brfna')
            self.assertEqual(kf.group_sheets(wbf1, 'wii_name'), list(range(38, 56)))
            self.assertEqual(kf.group_sheets(wbf1_5, 'wii_name'), [38] + list(range(49, 56)))
            self.assertEqual(sum(a != b for a, b in zip(wbf1, wbf1_5)), 3)
            self.assertEqual(fonts.get('wbf2.brfna'), fonts5.get('wbf2.brfna'))
            raw = decompress_lz11(t.get_content_by_index(1))
            labels = [r['ko'] for r in v6['keyboard_labels']] + [lng[k] for k in v6['lng_hints']]
            labels += [r['ko'] for r in config('exe')['keyboard'] if r['en'] not in v6['keyboard_rows_keep_english']]
            self.assertEqual(kf.missing_in_group(wbf1, 'wii_name', labels), [])
            self.assertTrue(kf.missing_in_group(wbf1_5, 'wii_name', labels))
            for word in ('확인', '취소', '예측 사전 언어', '기호', '영어', '프랑스', '스페인'):
                self.assertIn(word.encode('utf-16-be') + b'\0\0', raw)
            self.assertNotIn('스페이스'.encode('utf-16-be'), raw)  # key caps stay English
            text = ChannelArchive(t.get_content_by_index(6)).get('english.lng').decode('utf-8')
            for k in v6['lng_hints']:
                self.assertIn(f'="{lng[k]}"', text)  # Korean input hints
            c2 = ChannelArchive(t.get_content_by_index(2))
            for name in pictures['images']:
                new, old = Image.open(io.BytesIO(c2.get(name))), Image.open(io.BytesIO(o2.get(name)))
                self.assertNotEqual(c2.get(name), o2.get(name), name)
                self.assertEqual((new.size, new.mode, new.getpalette()), (old.size, old.mode, old.getpalette()), name)
            for name in pictures['kept']:
                self.assertEqual(c2.get(name), o2.get(name), name)
            self.assertIn('font-size: 110%;', c2.get('styles/error.css').decode('utf-8'))
            if not is_local:
                # hardware candidate: the same service addresses as hardware-v5
                self.assertEqual(urls(raw), urls(decompress_lz11(t5.get_content_by_index(1))))
                self.assertTrue(t.get_is_fakesigned())

    def test_v7_error_headings(self):
        base = ROOT / 'workspace/channels/internet'
        pairs = [(base / f'{kind}-v6' / name, base / f'{kind}-v7' / name)
                 for kind, name in (('build', 'internet-ko-local-test.wad'), ('hardware', 'internet-ko-hardware-candidate.wad'))]
        if not all(p.exists() for pair in pairs for p in pair):
            self.skipTest('local data')
        from kwce.channels import load_library, ChannelArchive
        from kwce import internet_error_headings as eh
        lib = load_library()
        v7 = json.loads((ROOT / 'configs/internet-v7-ko.json').read_text(encoding='utf-8'))
        rows = v7['error_heading_breaks']
        lng = config('lng')['translations']

        def load(path):
            t = lib.title.Title()
            t.load_wad(path.read_bytes())
            return t

        for old_path, new_path in pairs:
            old, new = load(old_path), load(new_path)
            changed = [i for i in range(old.tmd.num_contents) if old.get_content_by_index(i) != new.get_content_by_index(i)]
            self.assertEqual(changed, [2, 6])  # language files and the error stylesheet only
            o2, n2 = ChannelArchive(old.get_content_by_index(2)), ChannelArchive(new.get_content_by_index(2))
            self.assertEqual(sorted(f for f in n2.files if n2.get(f) != o2.get(f)), ['english.lng', 'styles/error.css'])
            text = ChannelArchive(new.get_content_by_index(6)).get('english.lng').decode('utf-8')
            self.assertEqual(n2.get('english.lng').decode('utf-8'), text)
            restored = text
            for row in rows.values():
                self.assertEqual(text.count(f'="{row["ko"]}"'), 1)
                restored = restored.replace(f'="{row["ko"]}"', f'="{row["v6"]}"')
            self.assertEqual(restored, ChannelArchive(old.get_content_by_index(6)).get('english.lng').decode('utf-8'))
            css = n2.get('styles/error.css').decode('utf-8')
            h1 = css[css.index('\nh1 {'):css.index('}', css.index('\nh1 {'))]
            self.assertIn('white-space: pre-line;', h1)
            self.assertIn('font-size: 110%;', h1)
            self.assertEqual(css.count('pre-line'), 1)
            # every forced line fits the width measured on screen, in the font the build ships
            report = eh.check(rows, lng, eh.Metrics(eh.opera_face(new.get_content_by_index(4))))
            self.assertEqual((report['headings'], report['max_lines']), (23, 2))
            self.assertEqual(new.tmd.region, 4)
        self.assertEqual(sorted(v7['kept_two_sentence']), [126, 514])
        self.assertTrue(all(eh.single_sentence(row['v6']) for row in rows.values()))


class ErrorHeadings(unittest.TestCase):
    """kwce.internet_error_headings with a synthetic width (1 em per character)."""

    class Metrics:
        from kwce import internet_error_headings as _eh

        def em(self, text):
            return float(len(text.replace('%s', self._eh.PLACEHOLDER)))

        bounds = _eh.Metrics.bounds
        limit = _eh.Metrics.limit

    def setUp(self):
        from kwce import internet_error_headings as eh
        self.eh = eh
        self.m = self.Metrics()

    def test_limit_from_observation(self):
        lower, upper = self.m.bounds()
        self.assertEqual((lower, upper), (1.3 * len(self.eh.OBSERVED_FITS), 1.3 * len(self.eh.OBSERVED_WRAPS)))
        self.assertAlmostEqual(self.m.limit(), self.eh.SAFETY * lower / 1.1)

    def test_plan_breaks_at_spaces_only(self):
        tr = {'0': '240001: ' + ' '.join(['가나다라'] * 8) + '.', '1': '240002: 짧습니다.', '2': '일반 문장 ' * 9,
              '3': '240003: 첫 문장입니다. ' + '두 번째 문장입니다 ' * 3 + '끝.'}
        rows = self.eh.plan(tr, self.m)
        self.assertEqual(sorted(rows), ['0'])  # short, non-heading and two-sentence entries untouched
        lines = rows['0']['ko'].split(self.eh.BREAK)
        self.assertEqual(' '.join(lines), tr['0'])
        self.assertTrue(all(self.m.em(ln) <= self.m.limit() for ln in lines))
        self.eh.check(rows, tr, self.m)

    def test_check_rejects(self):
        tr = {'0': '240001: ' + ' '.join(['가나다라'] * 8) + '.'}
        rows = self.eh.plan(tr, self.m)
        bad_words = {'0': dict(v6=tr['0'], ko=rows['0']['ko'].replace('가나', '나가', 1))}
        with self.assertRaises(ValueError):
            self.eh.check(bad_words, tr, self.m)
        too_wide = {'0': dict(v6=tr['0'], ko=tr['0'].replace(' ', self.eh.BREAK, 1))}
        with self.assertRaises(ValueError):
            self.eh.check(too_wide, tr, self.m)
        with self.assertRaises(ValueError):
            self.eh.check({'0': dict(v6='240001: 다른 문장.', ko='240001:\\n다른 문장.')}, tr, self.m)

    def test_apply_breaks(self):
        lng = '[Translation]\n1="a"\n-2="240001: 가 나"\n3="b"'.encode('utf-8')
        out, rec = self.eh.apply_breaks(lng, {'1': dict(v6='240001: 가 나', ko='240001: 가\\n나')})
        self.assertEqual(out.decode('utf-8'), '[Translation]\n1="a"\n-2="240001: 가\\n나"\n3="b"')
        self.assertEqual(rec['entries'], 1)
        with self.assertRaises(ValueError):
            self.eh.apply_breaks(lng, {'0': dict(v6='240001: 가 나', ko='240001: 가\\n나')})


class KeyboardFont(unittest.TestCase):
    @staticmethod
    def font(bits):
        """Minimal RFNA: GLGR (groups 'all', 'wii_name'; 3 sheets of 2 glyphs), FINF, one direct CMAP A-F."""
        names = b'all\0wii_name\0\0\0\0'
        glgr = struct.pack('>IHHHHH', 64, 2, 2, 3, 1, 1) + struct.pack('>HH', 88, 92) + bytes(2)
        glgr += struct.pack('>5I', 1, 1, 1, 1, 1)
        glgr += struct.pack('>2I', 0xe0000000, bits) + struct.pack('>2I', 1 << 31, 1 << 31) * 2 + names
        glgr = b'GLGR' + struct.pack('>I', 8 + len(glgr)) + glgr
        cmap_at = 16 + len(glgr) + 32
        finf = b'FINF' + struct.pack('>I', 32) + bytes(16) + struct.pack('>I', cmap_at + 8) + bytes(4)
        cmap = b'CMAP' + struct.pack('>I', 24) + struct.pack('>HHHHIH', 0x41, 0x46, 0, 0, 0, 0) + bytes(2)
        body = glgr + finf + cmap
        return b'RFNA\xfe\xff\x01\x04' + struct.pack('>IHH', 16 + len(body), 16, 3) + body

    def test_group_bits_and_lookup(self):
        from kwce import internet_keyboard_font as kf
        f = self.font(0x80000000)  # 'wii_name' loads sheet 0 only (glyphs 0-1 = 'A', 'B')
        self.assertEqual(kf.glyph_groups(f)['names'], ['all', 'wii_name'])
        self.assertEqual(kf.group_sheets(f, 'all'), [0, 1, 2])
        self.assertEqual(kf.group_sheets(f, 'wii_name'), [0])
        self.assertEqual([kf.find_glyph(f, ord(c)) for c in 'AFG'], [0, 5, kf.NOT_FOUND])
        self.assertEqual(kf.missing_in_group(f, 'wii_name', ['ABC', 'G']), ['C', 'G'])
        g, (lo, hi) = kf.with_group_sheets(f, 'wii_name', [0, 1])
        self.assertEqual(len(g), len(f))
        self.assertEqual([i for i in range(len(f)) if f[i] != g[i]], [lo])
        self.assertEqual(kf.group_sheets(g, 'wii_name'), [0, 1])
        self.assertEqual(kf.group_sheets(g, 'all'), [0, 1, 2])
        self.assertEqual(kf.missing_in_group(g, 'wii_name', ['ABCD']), [])
        with self.assertRaises(ValueError):
            kf.with_group_sheets(f, 'wii_name', [3])


class ManualPictures(unittest.TestCase):
    def test_fill_and_palette(self):
        from kwce.channels import load_library
        from kwce import internet_manual_images as mi
        load_library()
        from PIL import Image
        image = Image.new('RGB', (12, 6))
        for x in range(12):
            for y in range(6):
                image.putpixel((x, y), (20 * x, 10, 10))
        image.putpixel((5, 3), (255, 255, 255))  # a 'label' pixel
        mi.fill_box(image, [4, 2, 8, 5], 'interp')
        self.assertEqual(image.getpixel((5, 3)), (100, 10, 10))  # gradient restored
        mi.fill_box(image, [4, 2, 8, 5], 'row')
        self.assertEqual(image.getpixel((7, 2)), (60, 10, 10))
        with self.assertRaises(ValueError):
            mi.fill_box(image, [0, 0, 3, 3], 'interp')  # no border ring
        source = Image.new('P', (4, 2))
        source.putpalette([0, 0, 0, 255, 255, 255, 250, 250, 250])
        source.putdata([0, 1, 2, 1, 1, 1, 0, 0])
        edited = source.convert('RGB')
        edited.putpixel((0, 0), (240, 240, 240))  # inside the label box -> nearest used colour (index 2)
        edited.putpixel((3, 1), (255, 255, 255))  # outside the label box -> original index kept
        out = mi._same_palette(source, edited, [(0, 0, 2, 1)])
        self.assertEqual(list(out.getdata()), [2, 1, 2, 1, 1, 1, 0, 0])
        self.assertEqual(out.getpalette(), source.getpalette())


class Prefs(unittest.TestCase):
    def test_set_pref(self):
        src = b'Opera Preferences version 2.1\n\n[User Prefs]\nHome URL=/x\n\n[RM2]\nfxf=36\n'
        out = res.set_pref(src, 'User Prefs', 'Fallback HTML Encoding', 'euc-kr').decode('utf-8')
        self.assertIn('[User Prefs]\nFallback HTML Encoding=euc-kr\nHome URL=/x\n', out)
        with self.assertRaises(ValueError):
            res.set_pref(out.encode('utf-8'), 'User Prefs', 'Fallback HTML Encoding', 'euc-kr')
        with self.assertRaises(ValueError):
            res.set_pref(src, 'Missing', 'A', 'b')

    def test_exact_local_target(self):
        url = 'http://apps.example.com/r.php?a=%s&b=%s'
        raw = b'zz' + url.encode() + b'\0'
        out, rec = ex.patch_local_urls(raw, [dict(url=url, encoding='ascii', count=1)], {url: 'http://127.0.0.2/'})
        self.assertIn(b'http://127.0.0.2/\0', out)
        self.assertNotIn(b'%s', out)
        self.assertEqual(len(out), len(raw))
        with self.assertRaises(ValueError):
            ex.patch_local_urls(raw, [dict(url=url, encoding='ascii', count=1)], {url: 'http://127.0.0.2/?q=%s'})


class Server(unittest.TestCase):
    def test_server_source(self):
        from kwce.internet_server import server_source
        src = server_source()
        self.assertTrue(all(ord(c) < 128 for c in src))
        self.assertIn('Connection: keep-alive', src)
        # the send side is only shut down after waiting for the client (never right after a response)
        body = src.split('static string WaitClientClose', 1)
        self.assertNotIn('Shutdown(', body[0])
        self.assertEqual(src.count('Shutdown('), 1)
        # header names are logged, values never
        self.assertIn('names.Add(Regex.Replace(name', src)
        self.assertNotIn('Log(value', src)
        self.assertIn('status = 405', src)


@unittest.skipUnless(FEED.exists(), 'local data')
class Feed(unittest.TestCase):
    def test_fixture(self):
        manifest = json.loads((FEED / 'fixture-manifest.json').read_text(encoding='utf-8'))
        self.assertTrue(manifest['local_only'] and manifest['synthetic'] and manifest['fictional'])
        self.assertFalse(manifest['accepts_orders_uploads_or_posts'])
        routes = (FEED / 'routes.tsv').read_text(encoding='ascii').splitlines()
        self.assertTrue(all(len(r.split('\t')) == 3 for r in routes))
        for row in manifest['files']:
            data = (FEED / row['path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
            text = data.decode('euc_kr' if 'euckr' in row['path'] else 'utf-8')
            self.assertNotIn('<form', text.lower())
            self.assertIn('한글' if row['path'] != 'search.html' else '검색', text)
        self.assertIn('charset=euc-kr', (FEED / 'euckr.html').read_bytes().decode('euc_kr'))
        self.assertNotIn('charset', (FEED / 'euckr-nometa.html').read_bytes().decode('euc_kr'))


if __name__ == '__main__':
    unittest.main()

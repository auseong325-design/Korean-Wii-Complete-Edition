"""Wave-2 Food tests: Korean Wii Menu art, text fit, v6 tables, build-v6 / hardware-v5. No Dolphin.

Run: .venv\\Scripts\\python.exe -m unittest tests.test_food_wave2
"""
import hashlib, json, struct, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
from kwce.channels import load_library, ChannelArchive, layout_sections, textbox, sha256
from kwce import food_textfit as tf

FOOD = ROOT / 'workspace/channels/food'
WAD = FOOD / 'originals/food-japan-v512.wad'
BUILD6 = FOOD / 'build-v6/food-ko-local-test.wad'
HW5 = FOOD / 'hardware-v5/food-ko-hardware-test.wad'
_CACHE = {}


def _original():
    if 'orig' not in _CACHE:
        lib = load_library(); t = lib.title.Title(); t.load_wad(WAD.read_bytes())
        _CACHE['orig'] = (t, [t.get_content_by_index(i) for i in range(t.tmd.num_contents)])
    return _CACHE['orig']


def _metrics():
    if 'm' not in _CACHE:
        t, c = _original()
        _CACHE['m'] = (tf.korean_metrics(), tf.stock_metrics(c[3]))
    return _CACHE['m']


def _menu_archives(content0):
    load_library(); from libWiiPy.archive import decompress_lz77
    outer = ChannelArchive(content0[0x640:]); out = {}
    for member in ('meta/banner.bin', 'meta/icon.bin'):
        wrapped = outer.get(member)
        assert wrapped[:4] == b'IMD5' and hashlib.md5(wrapped[32:]).digest() == wrapped[16:32], member
        out[member] = ChannelArchive(decompress_lz77(wrapped[32:]))
    return out


def _pane(layout, name):
    for s in layout_sections(layout):
        if s[:4] in (b'pic1', b'txt1') and s[12:28].split(b'\0')[0].decode('ascii') == name:
            return s
    raise AssertionError(name)


class MenuArt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kwce.food_menu_art import korean_menu_art
        from kwce.food_banner import korean_banner
        t, c = _original()
        cls.art, cls.records = korean_menu_art(c[0])
        cls.final, _ = korean_banner(cls.art)
        cls.before, cls.after = _menu_archives(c[0]), _menu_archives(cls.final)

    def test_imet_integrity_and_names(self):
        from kwce.food_banner import _imet_md5, MD5_AT
        self.assertEqual(_imet_md5(self.final), self.final[MD5_AT:MD5_AT + 16])
        self.assertEqual(self.final[0x9c:0x9c + 16].decode('utf-16-be'), '음식 배달 채널')
        icon, banner = struct.unpack_from('>II', self.final, 0x8c)
        self.assertEqual((icon, banner), (len(self.after['meta/icon.bin'].data), len(self.after['meta/banner.bin'].data)))

    def test_only_wordmark_resources_change(self):
        from kwce.food_menu_art import BANNER, ICON, ORDER_TEXTURE
        allowed = {'meta/banner.bin': {BANNER['layout']} | {'arc/timg/%s.tpl' % n for n in BANNER['textures']},
                   'meta/icon.bin': {ICON['layout'], ORDER_TEXTURE} | {'arc/timg/%s.tpl' % n for n in ICON['textures']}}
        for member, archive in self.after.items():
            before = self.before[member]
            self.assertEqual(set(archive.files), set(before.files))
            changed = {p for p in before.files if archive.get(p) != before.get(p)}
            self.assertEqual(changed, allowed[member], member)
            for p in before.files:
                if p.endswith('.brlan'):
                    self.assertEqual(archive.get(p), before.get(p), p)        # animations untouched

    def test_tiles_keep_palette_and_size(self):
        from kwce.food_menu_art import BANNER, ICON, decode_ci
        from kwce.channel_texture import texture_records
        for member, spec in (('meta/banner.bin', BANNER), ('meta/icon.bin', ICON)):
            for i, name in enumerate(spec['textures']):
                path = 'arc/timg/%s.tpl' % name
                old, new = self.before[member].get(path), self.after[member].get(path)
                r = texture_records(old)[0]
                self.assertEqual(len(old), len(new)); self.assertEqual(texture_records(new), texture_records(old))
                self.assertEqual(new[:r['offset']], old[:r['offset']], path)      # header + palette bytes unchanged
                alpha = [p[3] for p in decode_ci(new).getdata()]
                if i == 3:
                    self.assertEqual(max(alpha), 0, 'small ャ tile must be blank')
                else:
                    self.assertGreater(sum(a > 200 for a in alpha), 20, path)

    def test_pane_positions_and_operator_line(self):
        lay = self.after['meta/banner.bin'].get('arc/blyt/banner.brlyt')
        xs = {n: round(struct.unpack_from('>f', _pane(lay, n), 0x24)[0]) for n in ('Ban_logo_00', 'Ban_logo_01', 'Ban_logo_02', 'Ban_logo_04', 'Ban_logo_05', 'Ban_logo_06')}
        self.assertEqual(xs, {'Ban_logo_00': -33, 'Ban_logo_01': 34, 'Ban_logo_02': -33, 'Ban_logo_04': 33, 'Ban_logo_05': -33, 'Ban_logo_06': 33})
        icon = self.after['meta/icon.bin'].get('arc/blyt/icon.brlyt')
        self.assertEqual([round(struct.unpack_from('>f', _pane(icon, 'Ico_logo_%02d' % i), 0x24)[0]) for i in (0, 1, 2, 4, 5, 6)],
                         [-46, -30, -8, 8, 30, 46])
        yume = textbox(_pane(lay, 'T_yume'))[1]
        self.assertEqual(yume, '이 서비스는 유메노마치소조위원회(주)가 운영합니다.')
        m, mj = _metrics(); box = tf.Box('banner', 'T_yume', _pane(lay, 'T_yume'))
        ja = textbox(_pane(self.before['meta/banner.bin'].get('arc/blyt/banner.brlyt'), 'T_yume'))[1]
        self.assertTrue(tf.fit(m, mj, box, ja, yume)['ok'])


class TextFit(unittest.TestCase):
    def _check(self, config):
        t, c = _original(); m, mj = _metrics(); outer = ChannelArchive(c[2]); reports = []
        for arc, lays in json.loads((ROOT / config).read_text(encoding='utf-8'))['layouts'].items():
            inner = ChannelArchive(outer.get('Dtest/' + arc))
            for lay, panes in lays.items():
                boxes = tf.boxes(inner.get(lay))
                for p in panes:
                    box, text, _ = boxes[p['pane']]
                    self.assertEqual(text, p['ja'], p['pane'])
                    reports.append((p['pane'], tf.fit(m, mj, box, p['ja'], p['ko'])))
        return dict(reports)

    def test_every_v6_layout_string_fits(self):
        reports = self._check('configs/food-layout-v6-ko.json')
        self.assertGreaterEqual(len(reports), 35)
        self.assertEqual([p for p, r in reports.items() if not r['ok']], [])
        self.assertEqual(reports['weT_05_txt_00']['lines'], 1)                 # welcome title: one line

    def test_v4_title_defect_is_detected(self):
        reports = self._check('configs/food-layout-v4-ko.json')               # real-Wii video 14:54
        self.assertFalse(reports['weT_05_txt_00']['ok']); self.assertFalse(reports['weT_05_txt_02']['ok'])

    def test_every_v6_dialog_string_fits(self):
        import make_food_translations_v6 as gen6
        t, c = _original(); m, mj = _metrics(); panes = tf.dialog_boxes(c[2])
        for ja, ko in gen6.NEW.items():
            self.assertEqual(tf.dialog_fit(m, mj, panes, ja, ko), [], ko[:12])


class ExecutableV6(unittest.TestCase):
    def test_table_matches_generator(self):
        import make_food_translations_v6 as gen6
        cfg = json.loads((ROOT / 'configs/food-executable-v6-ko.json').read_text(encoding='utf-8'))
        self.assertEqual(cfg, gen6.build())
        v4 = json.loads((ROOT / 'configs/food-executable-v4-ko.json').read_text(encoding='utf-8'))['utf16']
        self.assertTrue(set(v4) < set(cfg['utf16'])); self.assertEqual(len(cfg['utf16']), len(v4) + len(gen6.NEW))
        guide = [k for k in cfg['utf16'] if k.startswith('Wii本体に自宅住所情報が')]
        self.assertEqual(len(guide), 2)                                          # the guide seen before address setting


class TexturesV6(unittest.TestCase):
    def test_restyle_keeps_format_and_fixes_v4_mapping(self):
        from kwce.food_texture_v6 import restyle
        from kwce.channel_texture import texture_records
        t, c = _original(); outer = ChannelArchive(c[2])
        cfg = json.loads((ROOT / 'configs/food-textures-v6-ko.json').read_text(encoding='utf-8'))['textures']
        self.assertEqual(cfg['DtestOrder.arc']['Order/timg/02a_obi.tpl']['ja'], 'お店のリクエストができます')
        v1 = json.loads((ROOT / 'configs/food-textures-v1-ko.json').read_text(encoding='utf-8'))['labels']
        for arc, specs in cfg.items():
            self.assertFalse(set(specs) & set(v1.get(arc, {})), arc)            # never redraws a v1 label twice
            inner = ChannelArchive(outer.get('Dtest/' + arc))
            for path, spec in specs.items():
                if spec['mode'] not in ('text', 'button'):
                    continue
                raw = inner.get(path); new, meta = restyle(raw, spec)
                self.assertEqual(len(new), len(raw)); self.assertEqual(texture_records(new), texture_records(raw))
                self.assertNotEqual(new, raw, path); self.assertGreaterEqual(meta['size'], 12, path)


@unittest.skipUnless(BUILD6.exists() and HW5.exists(), 'build-v6 / hardware-v5 not built')
class Builds(unittest.TestCase):
    PAIRS = [(6, BUILD6, HW5), (7, FOOD / 'build-v7/food-ko-local-test.wad', FOOD / 'hardware-v6/food-ko-hardware-test.wad')]

    def _title(self, path):
        lib = load_library(); t = lib.title.Title(); t.load_wad(path.read_bytes()); return t

    def _pairs(self):
        return [(r, a, b) for r, a, b in self.PAIRS if a.exists() and b.exists()]

    def test_region_4_identity_and_endpoints(self):
        from kwce.wiiroom_formats import decompress_lz11
        t0, orig = _original()
        for _, local_wad, hw_wad in self._pairs():
            for path, local in ((local_wad, True), (hw_wad, False)):
                t = self._title(path)
                self.assertEqual(t.tmd.region, 4, path.parent.name)             # Korean Wii Menu accepts 3 or 4 only
                self.assertEqual((t.tmd.title_id, t.tmd.boot_index), ('000100014843484a', 9))
                meta = json.loads(path.with_name('build-manifest.json').read_text(encoding='utf-8'))
                self.assertEqual(meta['wad_sha256'], sha256(path.read_bytes()))
                self.assertEqual(meta['tmd_region'], 4)
                changed = [i for i in range(t.tmd.num_contents) if t.get_content_by_index(i) != orig[i]]
                self.assertEqual(changed, [0, 1, 2, 3, 4])
                dol = decompress_lz11(t.get_content_by_index(1))
                if local:
                    self.assertEqual(dol.count(b'127.0.0.2'), 4); self.assertNotIn(b'wiilink24', dol)
                else:
                    self.assertIn(b'food.wiilink24.com', dol); self.assertNotIn(b'127.0.0', dol)

    def test_byte_identical_regeneration_of_changed_contents(self):
        from kwce.food_menu_art import korean_menu_art, YUME_KO, YUME_KO_V7
        from kwce.food_banner import korean_banner
        from kwce.food_resources import korean_content2
        t0, orig = _original()
        for rev, local_wad, hw_wad in self._pairs():
            content0 = korean_banner(korean_menu_art(orig[0], YUME_KO_V7 if rev >= 7 else YUME_KO)[0])[0]
            content2 = korean_content2(orig[2], revision=rev)[0]
            for path in (local_wad, hw_wad):
                t = self._title(path)
                self.assertEqual(t.get_content_by_index(0), content0, path.parent.name)
                self.assertEqual(t.get_content_by_index(2), content2, path.parent.name)
            a, b = self._title(local_wad), self._title(hw_wad)
            for i in (2, 3, 4):
                self.assertEqual(a.get_content_by_index(i), b.get_content_by_index(i), (rev, i))


class LeadReviewV7(unittest.TestCase):
    """Lead Dolphin review of build-v4 (2026-10-28) folded into revision 7."""

    def test_v7_layout_fits_and_wording(self):
        reports = TextFit._check(TextFit(), 'configs/food-layout-v7-ko.json')
        self.assertEqual([p for p, r in reports.items() if not r['ok']], [])
        lay = json.loads((ROOT / 'configs/food-layout-v7-ko.json').read_text(encoding='utf-8'))['layouts']
        welcome = {p['pane']: p['ko'] for p in lay['DtestWelcome.arc']['Welcome/blyt/welcome_layout.brlyt']}
        self.assertIn('100만 엔', welcome['weT_06_txt_02']); self.assertNotIn('원 이상', welcome['weT_06_txt_02'])
        self.assertIn('유메노마치소조이인카이(주)', welcome['weT_07_txt_00'])

    def test_v7_table_and_operator_name_form(self):
        import make_food_translations_v7 as gen7
        from kwce.food_menu_art import YUME_KO_V7
        cfg = json.loads((ROOT / 'configs/food-executable-v7-ko.json').read_text(encoding='utf-8'))
        self.assertEqual(cfg, gen7.build())
        texts = list(cfg['utf16'].values()) + [YUME_KO_V7]
        self.assertFalse([t for t in texts if '위원회' in t])                     # one form only
        self.assertIn(gen7.COMPANY, YUME_KO_V7)

    def test_spd_identical_personal_data(self):
        from kwce import food_personal_data as fpd, personal_data_format as fmt
        plain = fpd.variant('korean-spd'); f = fmt.fields(plain)
        self.assertEqual(plain, fpd.korean_sample())                              # nothing a real SPD could not write
        for name, kana in (('last_name', 'kana_last_name'), ('first_name', 'kana_first_name')):
            self.assertTrue(f[name]); self.assertEqual(f[kana], f[name])
        self.assertEqual(fmt.fields(fpd.variant('korean'))['last_name'], '')    # old variant kept unchanged

    def test_feed_v7_terms_wrap_at_words(self):
        import tempfile
        from kwce.food_fixtures import EULA, EULA_V7, write_feed
        t, c = _original(); m, mj = _metrics()
        lay = ChannelArchive(ChannelArchive(c[2]).get('Dtest/DtestTitle.arc')).get('Title/blyt/00-2_m_layout.brlyt')
        box = tf.boxes(lay)['00-2T_regulat1'][0]
        self.assertIn('No r', [l[-4:] for l in tf.wrapped(m, box, EULA)])         # reproduces the lead's "No r / eal"
        self.assertEqual(tf.wrapped(m, box, EULA_V7), EULA_V7.split('\n'))        # no writer wrap any more
        self.assertEqual(EULA_V7.replace('\n', ' '), EULA)
        ref = FOOD / 'local-feed-v7'
        if ref.exists():
            with tempfile.TemporaryDirectory() as tmp:
                manifest = write_feed(Path(tmp), 7)
                for name in manifest['files'] + ['fixture-manifest.json']:
                    self.assertEqual(sha256((Path(tmp) / name).read_bytes()), sha256((ref / name).read_bytes()), name)


if __name__ == '__main__':
    unittest.main()

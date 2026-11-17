"""rc7b Y-Food tests (revision 12 / hardware-v11): every stock baked-Japanese texture the earlier waves
left, the order-record / order-list static labels, the recipient card of the confirm screens and the
order-record strings in content 1 (kwce.food_confirm_card), and rev <= 11 immutability. No Dolphin.

Run: .venv\\Scripts\\python.exe -m unittest tests.test_food_rc7b
"""
import json, struct, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
from kwce.channels import load_library, ChannelArchive, layout_sections, textbox, sha256
from kwce.channel_texture import texture_records
from kwce.food_menu_art import decode_any
from kwce.wiiroom_formats import decompress_lz11
from kwce import food_textfit as tf
from kwce import food_confirm_card as cc
from kwce.food_address_card import _offset, _sections

FOOD = ROOT / 'workspace/channels/food'
STOCK = FOOD / 'originals/food-japan-v512.wad'
BUILD11 = FOOD / 'build-v11/food-ko-local-test.wad'
BUILD12 = FOOD / 'build-v12/food-ko-local-test.wad'
HW10 = FOOD / 'hardware-v10/food-ko-hardware-test.wad'
HW11 = FOOD / 'hardware-v11/food-ko-hardware-test.wad'
TEX = json.loads((ROOT / 'configs/food-textures-v12-ko.json').read_text(encoding='utf-8'))['textures']
LAY_CFG = json.loads((ROOT / 'configs/food-layout-v12-ko.json').read_text(encoding='utf-8'))
LAY, HIDDEN = LAY_CFG['layouts'], LAY_CFG['hidden']
FROZEN = {'build-v12/food-ko-local-test.wad': 'b104d47a9915ebfa29a7586100ef0e37ae5799292fb7bcabced717d9a416efb7',
          'hardware-v11/food-ko-hardware-test.wad': 'b99cde1be6e4da3bc2af56411e5c1475b0789efba645b0752ef897530e11ce76',
          'build-v11/food-ko-local-test.wad': 'a70a24d49bd7496ffb927f32c6212ef3f20be53ce4a9ffa602e6a9788966b456',
          'hardware-v10/food-ko-hardware-test.wad': 'e204f1e95b14d67abde7f6aafd753008278c8d3f970e636f08ebf748dfe400bf',
          'build-v10/food-ko-local-test.wad': '8a361e27c15b51c5db162d52a787263ee0a34f95363ffb47ccfbd6111b22877a',
          'hardware-v9/food-ko-hardware-test.wad': '3190415bc12e1055cd34be729f0dffc4323a256b8491b5b130540f6b21940306'}
# panes the DOL writes at run time (UTF-16 or Shift-JIS literals): rev 12 leaves their layout text alone
RUNTIME = (('DtestTitle.arc', 'Title/blyt/L2_m_layout.brlyt', 'L2_T_reorder1'),
           ('DtestTitle.arc', 'Title/blyt/L2_m_layout.brlyt', 'L2_T_objnm_t00'),
           ('DtestTitle.arc', 'Title/blyt/L2_m_layout.brlyt', 'L2_T_d-time_v'),
           ('DtestTitle.arc', 'Title/blyt/A1_m_layout.brlyt', 'A1_T_obj_Cname'),
           ('DtestOrder.arc', 'Order/blyt/10_m_layout.brlyt', '10_T_btn_noOK'),
           ('DtestOrder.arc', 'Order/blyt/12_m_layout.brlyt', '12_T_d-time_v'),
           ('DtestOrder.arc', 'Order/blyt/12_m_layout.brlyt', '12_T_user-name'),
           ('DtestOrder.arc', 'Order/blyt/12_m_layout.brlyt', '12_T_ad-code'),
           ('DtestOrder.arc', 'Order/blyt/14_m_layout.brlyt', '14_T_uppertext'),
           ('DtestOrder.arc', 'Order/blyt/14_m_layout.brlyt', '14_T_endtext'),
           ('DtestOrder.arc', 'Order/blyt/04abc_m_layout.brlyt', '04c_T_time'))
_CACHE = {}


def _contents(path):
    if path not in _CACHE:
        lib = load_library(); t = lib.title.Title(); t.load_wad(Path(path).read_bytes())
        _CACHE[path] = [t.get_content_by_index(i) for i in range(t.tmd.num_contents)]
    return _CACHE[path]


def _dol(path):
    key = ('dol', path)
    if key not in _CACHE:
        raw = _contents(path)[1]
        _CACHE[key] = raw if raw[:4] == b'\x00\x00\x01\x00' else decompress_lz11(raw)
    return _CACHE[key]


def _inner(path, arc):
    return ChannelArchive(ChannelArchive(_contents(path)[2]).get('Dtest/' + arc))


def _sections_of(path, arc, layout):
    return layout_sections(_inner(path, arc).get(layout))


def _pane(path, arc, layout, name):
    for s in _sections_of(path, arc, layout):
        if s[:4] in (b'txt1', b'pic1', b'pan1') and s[12:28].split(b'\0')[0].decode('ascii') == name:
            return s
    raise KeyError(name)


class Contents(unittest.TestCase):
    def test_rev12_changes_contents_1_and_2_only(self):
        for a, b in ((BUILD11, BUILD12), (HW10, HW11)):
            ca, cb = _contents(a), _contents(b)
            self.assertEqual([i for i in range(len(ca)) if ca[i] != cb[i]], [1, 2], b.parent.name)

    def test_frozen_hashes(self):
        for rel, digest in FROZEN.items():
            self.assertEqual(sha256((FOOD / rel).read_bytes()), digest, rel)


class Executable(unittest.TestCase):
    def test_only_card_words_and_string_literals_changed(self):
        for old, new in ((BUILD11, BUILD12), (HW10, HW11)):
            a, b = _dol(old), _dol(new)
            self.assertEqual(len(a), len(b)); self.assertEqual(_sections(a), _sections(b))   # no new section
            words = {_offset(a, va) for va, *_ in cc.CARD_EDITS}
            spans = [(_offset(a, va), 2 * len(ja)) for va, ja, _, _ in cc.string_plan(a)]
            for i in range(0, len(a), 2):
                if a[i:i + 2] != b[i:i + 2]:
                    self.assertTrue(i - i % 4 in words or any(s <= i < s + n for s, n in spans), '%x' % i)
            for va, old_w, new_w, _ in cc.CARD_EDITS:
                at = _offset(a, va)
                self.assertEqual(struct.unpack_from('>I', a, at)[0], old_w)
                self.assertEqual(struct.unpack_from('>I', b, at)[0], new_w)

    def test_simulated_recipient_card(self):
        self.assertEqual(cc.simulate(_dol(HW10)), cc.stock_expectation())      # 'given family', 〒, parts run together
        self.assertEqual(cc.simulate(_dol(HW11)), cc.korean_expectation())     # 'familygiven', no 〒, spaced parts
        for path in (BUILD12, HW11):
            sim = cc.simulate(_dol(path), parts=('서울특별시', '', '세종대로 1', ''))
            self.assertTrue(all(fits for _, fits in sim.values()))               # buffer holds the extra spaces

    def test_order_strings_korean_in_place(self):
        m = tf.korean_metrics()
        for path in (BUILD12, HW11):
            dol = _dol(path)
            self.assertEqual(cc._read_wide(dol, 0x804706f8), '가'); self.assertEqual(cc._read_wide(dol, 0x804706fc), '불가')
            tagged = cc._read_wide(dol, 0x804708c6); plain = cc._read_wide(dol, 0x80470972)
            self.assertIn('예약 주문', tagged); self.assertEqual(tagged.count(cc.REORDER_TAG), 2)
            self.assertEqual(plain, cc.REORDER_KO_PLAIN)
            for text in (tagged, plain):
                self.assertFalse(m.missing(cc.visible_text(text)))
                lines = cc.visible_text(text).split('\n')
                box = tf.boxes(_inner(path, 'DtestTitle.arc').get('Title/blyt/L2_m_layout.brlyt'))['L2_T_reorder1'][0]
                self.assertLessEqual(max(tf.width(m, box, line) for line in lines), box.w - tf.MARGIN)
                self.assertLessEqual(len(lines), 4)
        # the stock literals are still where the code points (pool 0x804708c4 + 2 / + 0xae), only shorter
        self.assertEqual(len(cc._read_wide(_dol(HW10), 0x804708c6)), 85)


class Textures(unittest.TestCase):
    def test_v12_textures_redrawn_same_gx_layout(self):
        stock = ChannelArchive(_contents(STOCK)[2]); n = 0
        for arc, specs in TEX.items():
            s_in, a, b = ChannelArchive(stock.get('Dtest/' + arc)), _inner(HW10, arc), _inner(HW11, arc)
            for tpl in specs:
                old, new = a.get(tpl), b.get(tpl)
                self.assertEqual(old, s_in.get(tpl), tpl)                 # still stock in rev 11 (Japanese)
                self.assertNotEqual(new, old, tpl)                       # redrawn in rev 12
                self.assertEqual(len(new), len(old), tpl)
                ra, rb = texture_records(old), texture_records(new)
                self.assertEqual([(r['format'], r['width'], r['height'], r['offset']) for r in ra],
                                 [(r['format'], r['width'], r['height'], r['offset']) for r in rb], tpl)
                self.assertEqual(new[:ra[0]['offset']], old[:ra[0]['offset']], tpl)   # header (+ CI palette) unchanged
                if ra[0]['format'] in (8, 9):
                    self.assertTrue(ra[0]['palette'])
                decode_any(new, 0); n += 1
        self.assertEqual(n, sum(len(v) for v in TEX.values()))
        self.assertGreaterEqual(n, 80)

    def test_shop_info_band_titles(self):
        # IMG_5695 band titles are 04_panel_f_* (04_m_layout pic1 04_P_win_g*), not the 04abc detail obis
        specs = TEX['DtestOrder.arc']
        self.assertEqual([specs['Order/timg/04_panel_f_%02d.tpl' % i]['ko'] for i in range(3)], ['한마디 PR', '배달 혜택', '가게 확인'])
        lay = _inner(HW11, 'DtestOrder.arc').get('Order/blyt/04_m_layout.brlyt')
        self.assertIn(b'04_panel_f_00.tpl', lay)

    def test_glyphs_in_shared_font(self):
        from kwce.food_resources import _wbf1_glyphs
        glyphs = _wbf1_glyphs()
        for specs in TEX.values():
            for tpl, spec in specs.items():
                for part in spec.get('parts') or [spec]:
                    self.assertFalse([c for c in part['ko'] if c != '\n' and ord(c) not in glyphs], tpl)


class Layouts(unittest.TestCase):
    def test_static_labels_korean_and_fit(self):
        m, mj = tf.korean_metrics(), tf.stock_metrics(_contents(HW11)[3]); n = 0
        for arc, layouts in LAY.items():
            for layout, panes in layouts.items():
                before = {tb[0]: tb[1] for s in _sections_of(HW10, arc, layout) for tb in [textbox(s)] if tb}
                boxes = tf.boxes(_inner(HW11, arc).get(layout))
                for p in panes:
                    self.assertEqual(before[p['pane']].rstrip('\0'), p['ja'], p['pane'])
                    box, after, _ = boxes[p['pane']]
                    self.assertEqual(after.rstrip('\0'), p['ko'], p['pane'])
                    rep = tf.fit(m, mj, box, p['ja'], p['ko'])
                    self.assertTrue(rep['ok'], (p['pane'], rep))
                    n += 1
        self.assertGreaterEqual(n, 35)

    def test_icon_gaps_stay_under_their_icons(self):
        m, mj = tf.korean_metrics(), tf.stock_metrics(_contents(HW11)[3])
        panes = {p['pane']: p for p in LAY['DtestTitle.arc']['Title/blyt/L2_m_layout.brlyt']}
        box = tf.boxes(_inner(HW11, 'DtestTitle.arc').get('Title/blyt/L2_m_layout.brlyt'))['L2_T_warnin00'][0]
        gap = '\u3000'

        def starts(metrics, text):
            out = []
            for line in text.split('\n'):
                lw = tf.width(metrics, box, line); i = 0
                while gap in line[i:]:
                    j = line.index(gap, i)
                    out.append(round(-lw / 2 + tf.width(metrics, box, line[:j]) + (box.cs if j else 0), 1))
                    i = line.index(next((c for c in line[j:] if c != gap), gap), j) if line[j:].strip(gap) else len(line)
            return out
        ja, ko = starts(mj, panes['L2_T_warnin00']['ja']), starts(m, panes['L2_T_warnin00']['ko'])
        self.assertEqual(len(ja), len(ko))
        for a, b in zip(ja, ko):
            self.assertLessEqual(abs(a - b), 4.0, (ja, ko))

    def test_runtime_panes_untouched(self):
        for arc, layout, pane in RUNTIME:
            a = textbox(_pane(HW10, arc, layout, pane))[1]; b = textbox(_pane(HW11, arc, layout, pane))[1]
            self.assertEqual(a, b, pane)

    def test_text_buffers_never_below_stock(self):
        stock = ChannelArchive(_contents(STOCK)[2]); checked = 0
        for arc in ('DtestOrder.arc', 'DtestTitle.arc', 'DtestDialog.arc', 'DtestWelcome.arc', 'DtestCommon.arc'):
            s_in, n_in = ChannelArchive(stock.get('Dtest/' + arc)), _inner(HW11, arc)
            for f in s_in.files:
                if not f.endswith('.brlyt') or s_in.get(f)[:4] != b'RLYT':
                    continue
                old = {s[12:28]: struct.unpack_from('>H', s, 76)[0] for s in layout_sections(s_in.get(f)) if s[:4] == b'txt1'}
                for s in layout_sections(n_in.get(f)):
                    if s[:4] == b'txt1':
                        self.assertGreaterEqual(struct.unpack_from('>H', s, 76)[0], old[s[12:28]], f); checked += 1
        self.assertGreater(checked, 300)

    def test_reading_lines_hidden(self):
        for layout, names in HIDDEN['DtestOrder.arc'].items():
            for name in names:
                self.assertTrue(_pane(HW10, 'DtestOrder.arc', layout, name)[8] & 1)
                self.assertFalse(_pane(HW11, 'DtestOrder.arc', layout, name)[8] & 1)


if __name__ == '__main__':
    unittest.main()

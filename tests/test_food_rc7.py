"""rc7 X-Food tests: order-flow BRLYT static labels (DtestOrder + product-help dialog),
the buttons the earlier waves missed (くわしく->자세히, 注文する->주문하기 glyph tiles,
へんこう/えらぶ/とりけし), the category-screen refit (one max font size, 케이터링, blanked
NOdata placeholder, asu contrast), content-2-only change (boot-safe), and rev 10 / earlier
immutability. No Dolphin.

Run: .venv\\Scripts\\python.exe -m unittest tests.test_food_rc7
"""
import json, struct, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
from kwce.channels import load_library, ChannelArchive, layout_sections, textbox, sha256
from kwce.tpl import decode, texture_records
from kwce import food_resources as fr
from kwce import food_textfit as tf

FOOD = ROOT / 'workspace/channels/food'
BUILD10 = FOOD / 'build-v10/food-ko-local-test.wad'
BUILD11 = FOOD / 'build-v11/food-ko-local-test.wad'
HW9 = FOOD / 'hardware-v9/food-ko-hardware-test.wad'
HW10 = FOOD / 'hardware-v10/food-ko-hardware-test.wad'
LAY_V11 = json.loads((ROOT / 'configs/food-layout-v11-ko.json').read_text(encoding='utf-8'))['layouts']
TEX_V11 = json.loads((ROOT / 'configs/food-textures-v11-ko.json').read_text(encoding='utf-8'))['textures']
FROZEN = {'build-v11/food-ko-local-test.wad': 'a70a24d49bd7496ffb927f32c6212ef3f20be53ce4a9ffa602e6a9788966b456',
          'hardware-v10/food-ko-hardware-test.wad': 'e204f1e95b14d67abde7f6aafd753008278c8d3f970e636f08ebf748dfe400bf',
          'build-v10/food-ko-local-test.wad': '8a361e27c15b51c5db162d52a787263ee0a34f95363ffb47ccfbd6111b22877a',
          'hardware-v9/food-ko-hardware-test.wad': '3190415bc12e1055cd34be729f0dffc4323a256b8491b5b130540f6b21940306'}
_CACHE = {}


def _contents(path):
    if path not in _CACHE:
        lib = load_library(); t = lib.title.Title(); t.load_wad(Path(path).read_bytes())
        _CACHE[path] = [t.get_content_by_index(i) for i in range(t.tmd.num_contents)]
    return _CACHE[path]


def _textboxes(content2, arc, layout):
    inner = ChannelArchive(ChannelArchive(content2).get('Dtest/' + arc))
    return {tb[0]: tb[1] for s in layout_sections(inner.get(layout)) for tb in [textbox(s)] if tb}


def _tpl(content2, arc, name):
    return ChannelArchive(ChannelArchive(content2).get('Dtest/' + arc)).get(name)


class BootSafety(unittest.TestCase):
    def test_v11_changes_only_content_2_vs_rev10(self):
        # content 0 (logo) / 1 (phone+address) / 3 (fonts) / 4 (home) stay exactly rev 10 -> boot-safe
        for a, b in ((BUILD10, BUILD11), (HW9, HW10)):
            ca, cb = _contents(a), _contents(b)
            self.assertEqual([i for i in range(len(ca)) if ca[i] != cb[i]], [2], b.parent.name)


class LayoutLabels(unittest.TestCase):
    def test_new_labels_japanese_before_korean_after_and_fit(self):
        m = tf.korean_metrics(); mj = tf.stock_metrics(_contents(BUILD11)[3])
        checked = 0
        for arc, layouts in LAY_V11.items():
            for layout, panes in layouts.items():
                before = _textboxes(_contents(BUILD10)[2], arc, layout)
                after = _textboxes(_contents(BUILD11)[2], arc, layout)
                boxes = tf.boxes(ChannelArchive(ChannelArchive(_contents(BUILD11)[2]).get('Dtest/' + arc)).get(layout))
                for p in panes:
                    pane = p['pane']
                    self.assertEqual(before[pane].rstrip('\0'), p['ja'], arc + '/' + pane)   # rev10 still Japanese
                    self.assertEqual(after[pane].rstrip('\0'), p['ko'], arc + '/' + pane)     # rev11 Korean
                    box = boxes[pane][0]; fw = box.fw * p.get('fw_scale', 1.0)
                    rep = tf.fit(m, mj, box, p['ja'], p['ko'], fw=fw)
                    self.assertFalse(rep['missing'], arc + '/' + pane + ' glyphs')
                    self.assertLessEqual(rep['widest'], box.w - tf.MARGIN + 0.1, arc + '/' + pane + ' width')
                    self.assertLessEqual(rep['lines'], rep['budget'], arc + '/' + pane + ' lines')
                    checked += 1
        self.assertGreater(checked, 80)

    def test_server_and_placeholder_panes_untouched(self):
        # prices, personal-data placeholders and server 'ああ' names are identical rev10 -> rev11
        c10, c11 = _contents(BUILD10)[2], _contents(BUILD11)[2]
        arc = 'DtestOrder.arc'
        for layout, pane in (('Order/blyt/12_m_layout.brlyt', '12_T_price_v00'),
                             ('Order/blyt/12_m_layout.brlyt', '12_T_user-name'),
                             ('Order/blyt/12_m_layout.brlyt', '12_T_ad-code'),
                             ('Order/blyt/10_m_layout.brlyt', '10_T_men_Mname'),
                             ('Order/blyt/08_m_layout.brlyt', '08_T_btn_money_S')):
            self.assertEqual(_textboxes(c10, arc, layout)[pane], _textboxes(c11, arc, layout)[pane], pane)


class Textures(unittest.TestCase):
    def test_new_buttons_and_tiles_differ_same_gx_size(self):
        c10, c11 = _contents(BUILD10)[2], _contents(BUILD11)[2]
        for arc, specs in TEX_V11.items():
            for tpl in specs:
                a, b = _tpl(c10, arc, tpl), _tpl(c11, arc, tpl)
                self.assertNotEqual(a, b, arc + '/' + tpl)          # redrawn
                self.assertEqual(len(a), len(b), arc + '/' + tpl)   # same GX format/size/offset

    def test_nodata_placeholder_blanked(self):
        img = decode(_tpl(_contents(BUILD11)[2], 'DtestOrder.arc', 'Order/timg/02_btn_menu_NOdata.tpl'), 0).convert('RGBA')
        self.assertEqual(img.getextrema()[3], (0, 0))   # fully transparent (no floating '음식 배달 채널')

    def test_order_button_is_jumunhagi(self):
        self.assertEqual([TEX_V11['DtestOrder.arc']['Order/timg/12_btn_f_%s.tpl' % k]['ko'] for k in ('chu', 'mon', 'su', 'ru')],
                         ['주', '문', '하', '기'])


class MergeHelpers(unittest.TestCase):
    def test_merge_cfg_override_and_overlap(self):
        base = {'a': {'x': 1}}; delta = {'a': {'x': 2}}
        with self.assertRaises(ValueError):
            fr._merge_cfg(base, delta)
        self.assertEqual(fr._merge_cfg(base, delta, override=True)['a']['x'], 2)

    def test_merge_layouts_appends_and_refuses_duplicate_pane(self):
        base = {'A': {'b.brlyt': [{'pane': 'p1'}]}}
        merged = fr._merge_layouts(base, {'A': {'b.brlyt': [{'pane': 'p2'}]}})
        self.assertEqual([p['pane'] for p in merged['A']['b.brlyt']], ['p1', 'p2'])
        with self.assertRaises(ValueError):
            fr._merge_layouts(base, {'A': {'b.brlyt': [{'pane': 'p1'}]}})


class Frozen(unittest.TestCase):
    def test_hashes(self):
        for rel, digest in FROZEN.items():
            self.assertEqual(sha256((FOOD / rel).read_bytes()), digest, rel)


if __name__ == '__main__':
    unittest.main()

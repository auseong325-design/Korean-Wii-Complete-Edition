"""Food hardware-v14: overlay panes follow the blank runs of the Korean sentences.

Real-console photos (2026-11-16) showed the A button drawn over the next letter and the
waiting minutes over the unit. The stock panes sit at the centre of the Japanese blank run;
the test pins that model on the stock layout and the Korean positions derived from it.
"""
import json
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOOD = ROOT / 'workspace/channels/food'
WADS = [FOOD / 'originals/food-japan-v512.wad', FOOD / 'hardware-v12/food-ko-hardware-test.wad',
        FOOD / 'hardware-v14/food-ko-hardware-test.wad']


def content(path, index):
    from kwce.channels import load_library
    title = load_library().title.Title(); title.load_wad(path.read_bytes())
    return title.get_content_by_index(index)


@unittest.skipUnless(all(p.is_file() for p in WADS), 'Food stock/v12/v14 builds not present')
class FoodOverlayAlignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kwce import food_overlay_align as fo, food_textfit as ft
        cls.fo = fo
        cls.stock2, cls.v12, cls.v14 = content(WADS[0], 2), content(WADS[1], 2), content(WADS[2], 2)
        cls.new, cls.record = fo.align(cls.v12, cls.stock2, ft.stock_metrics(content(WADS[0], 3)), ft.korean_metrics())

    def test_stock_panes_sit_on_the_stock_blank_runs(self):
        # align() refuses any pane further than MODEL_TOLERANCE from its stock run.
        self.assertEqual(len(self.record), 10)
        offsets = {'11_T_Iname_00': 0.0, '08h_T_OKtxt': 192.0}
        for row in self.record:
            self.assertLessEqual(abs(row['x'][0] - offsets.get(row['pane'], 0.0) - row['stock_run']), self.fo.MODEL_TOLERANCE, row['pane'])

    def test_panes_move_by_the_distance_the_run_moved(self):
        moved = {r['pane']: r for r in self.record}
        for pane, row in moved.items():
            self.assertAlmostEqual(row['x'][1] - row['x'][0], row['korean_run'] - row['stock_run'], delta=0.11, msg=pane)
        # The cases visible in the photos: A button, second A button, last heart, waiting minutes.
        self.assertEqual(moved['dic_P_iconH00_00']['x'], [25.0, 9.2])
        self.assertEqual(moved['dic_P_iconH00_02']['x'], [-44.0, -63.1])
        self.assertEqual(moved['dic_P_iconH00_03']['x'], [-60.0, -47.5])
        self.assertEqual(moved['11_T_Iname_00']['x'], [107.0, 83.3])

    def test_v14_is_v12_with_only_the_three_layouts_changed(self):
        from kwce.channels import ChannelArchive
        self.assertEqual(self.new, self.v14)
        a, b = ChannelArchive(self.v12), ChannelArchive(self.v14)
        changed = {}
        for name in a.files:
            if a.get(name) != b.get(name):
                x, y = ChannelArchive(a.get(name)), ChannelArchive(b.get(name))
                changed[name] = sorted(f for f in x.files if x.get(f) != y.get(f))
        self.assertEqual(changed, {'Dtest/DtestDialog.arc': ['Dialog/blyt/dialogue_layout.brlyt'],
                                   'Dtest/DtestOrder.arc': ['Order/blyt/08_m_layout.brlyt', 'Order/blyt/11_m_layout.brlyt']})
        for index in (0, 1, 3, 4):
            self.assertEqual(content(WADS[1], index), content(WADS[2], index))
        manifest = json.loads((WADS[2].parent / 'build-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual((manifest['parent_revision'], manifest['changed_from_parent']), (12, [2]))

    def test_text_is_untouched(self):
        from kwce.channels import ChannelArchive, layout_sections, textbox
        for arc, layout in (('Dtest/DtestDialog.arc', 'Dialog/blyt/dialogue_layout.brlyt'), ('Dtest/DtestOrder.arc', 'Order/blyt/11_m_layout.brlyt')):
            old = layout_sections(ChannelArchive(ChannelArchive(self.v12).get(arc)).get(layout))
            new = layout_sections(ChannelArchive(ChannelArchive(self.v14).get(arc)).get(layout))
            self.assertEqual([textbox(s) for s in old], [textbox(s) for s in new])
            for s, n in zip(old, new):       # only the x translate (0x24) of a moved pane differs
                if s != n:
                    self.assertEqual(s[:0x24] + s[0x28:], n[:0x24] + n[0x28:])
                    self.assertNotEqual(struct.unpack_from('>f', s, 0x24), struct.unpack_from('>f', n, 0x24))


if __name__ == '__main__':
    unittest.main()

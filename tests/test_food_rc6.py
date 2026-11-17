"""rc6 W-Food tests: phone-check patch (9-11 digits, in place), order-flow texture/label
translation, the bolder Wii-Menu wordmark, build-v10 / hardware-v9 parity, and rev 9 /
earlier immutability. No Dolphin.

Run: .venv\\Scripts\\python.exe -m unittest tests.test_food_rc6
"""
import json, struct, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
from kwce.channels import load_library, ChannelArchive, layout_sections, textbox, sha256
from kwce.wiiroom_formats import decompress_lz11
from kwce import bspatch
from kwce import food_phone as ph
from kwce import food_address_card as card
from kwce import food_textfit as tf

FOOD = ROOT / 'workspace/channels/food'
WIILINK_PATCH = FOOD / 'references/wiilink-patcher/bsdiff__demae__Demae_1_Japan.bsdiff'
BUILD9 = FOOD / 'build-v9/food-ko-local-test.wad'
BUILD10 = FOOD / 'build-v10/food-ko-local-test.wad'
HW8 = FOOD / 'hardware-v8/food-ko-hardware-test.wad'
HW9 = FOOD / 'hardware-v9/food-ko-hardware-test.wad'
TEX_V10 = json.loads((ROOT / 'configs/food-textures-v10-ko.json').read_text(encoding='utf-8'))['textures']
LAY_V10 = json.loads((ROOT / 'configs/food-layout-v10-ko.json').read_text(encoding='utf-8'))['layouts']
FROZEN = {'build-v9/food-ko-local-test.wad': 'f1a254c515a1a605b006976ffcf09445664e12f6a8b152d78b511e4e4211eaf4',
          'hardware-v8/food-ko-hardware-test.wad': 'd50267ca11d1122cecf503ff5b655ee9ccf11be57656677b9e242e812a8ad54e',
          'build-v10/food-ko-local-test.wad': '8a361e27c15b51c5db162d52a787263ee0a34f95363ffb47ccfbd6111b22877a',
          'hardware-v9/food-ko-hardware-test.wad': '3190415bc12e1055cd34be729f0dffc4323a256b8491b5b130540f6b21940306'}
_CACHE = {}


def _contents(path):
    if path not in _CACHE:
        lib = load_library(); t = lib.title.Title(); t.load_wad(Path(path).read_bytes())
        _CACHE[path] = [t.get_content_by_index(i) for i in range(t.tmd.num_contents)]
    return _CACHE[path]


def _wiilink_dol():
    if 'wl' not in _CACHE:
        _CACHE['wl'] = bspatch.apply(_contents(FOOD / 'originals/food-japan-v512.wad')[1], WIILINK_PATCH.read_bytes())
    return _CACHE['wl']


def _textboxes(content2, arc, layout):
    inner = ChannelArchive(ChannelArchive(content2).get('Dtest/' + arc))
    return {tb[0]: tb[1] for s in layout_sections(inner.get(layout)) for tb in [textbox(s)] if tb}


class PhoneCheck(unittest.TestCase):
    def test_five_words_in_place_only(self):
        dol = _wiilink_dol(); new, rec = ph.patch_phone_check(dol)
        self.assertEqual(len(new), len(dol)); self.assertEqual(new[:0x100], dol[:0x100])   # DOL header/section table
        diff = [i for i in range(0, len(dol), 4) if dol[i:i + 4] != new[i:i + 4]]
        self.assertEqual(len(diff), len(ph.DOL_EDITS)); self.assertEqual(rec['edited_words'], 5)
        self.assertEqual(rec['new_sections'], 0); self.assertTrue(rec['dol_size_unchanged'])

    def test_simulation_matches_the_L4_table(self):
        dol = _wiilink_dol(); new, _ = ph.patch_phone_check(dol)
        for number, case, stock, patched in ph.CASES:
            self.assertEqual(ph.check_phone(dol, number), stock, 'stock: ' + case)
            self.assertEqual(ph.check_phone(new, number), patched, 'patched: ' + case)
        # the fix is exactly "accept 9-11 digits": 010/02/031 Korean numbers pass after, failed before
        self.assertFalse(ph.check_phone(dol, '01012345678')); self.assertTrue(ph.check_phone(new, '01012345678'))
        self.assertFalse(ph.check_phone(new, '0123456')); self.assertFalse(ph.check_phone(new, '012345678901'))

    def test_refuses_unexpected_bytes(self):
        dol = bytearray(_wiilink_dol()); struct.pack_into('>I', dol, ph.to_file(dol, ph.DOL_EDITS[0][0]), 0x60000000)
        with self.assertRaises(ValueError):
            ph.patch_phone_check(bytes(dol))


class Executable(unittest.TestCase):
    def test_both_builds_carry_the_phone_and_address_edits(self):
        for path in (BUILD10, HW9):
            dol = decompress_lz11(_contents(path)[1])
            for va, old, new, _ in ph.DOL_EDITS:
                self.assertEqual(ph._word(dol, va), new, '%s phone %08x' % (path.parent.name, va))
            for va, old, new, _ in card.DOL_EDITS:
                self.assertEqual(card._word(dol, va), new, '%s address %08x' % (path.parent.name, va))

    def test_v10_differs_from_v9_by_exactly_the_five_phone_words(self):
        for a, b in ((BUILD9, BUILD10), (HW8, HW9)):
            d9, d10 = decompress_lz11(_contents(a)[1]), decompress_lz11(_contents(b)[1])
            self.assertEqual(len(d9), len(d10))
            diff = [i for i in range(0, len(d9), 4) if d9[i:i + 4] != d10[i:i + 4]]
            self.assertEqual(len(diff), len(ph.DOL_EDITS))
            self.assertEqual(sorted(ph._word(d10, va) for va, _, _, _ in ph.DOL_EDITS), sorted(n for _, _, n, _ in ph.DOL_EDITS))


class Content2(unittest.TestCase):
    def test_v10_changes_only_contents_0_1_2_from_v9(self):
        for a, b in ((BUILD9, BUILD10), (HW8, HW9)):
            ca, cb = _contents(a), _contents(b)
            self.assertEqual([i for i in range(len(ca)) if ca[i] != cb[i]], [0, 1, 2])

    def test_translated_textures_differ_and_keep_topology(self):
        c9, c10 = _contents(BUILD9)[2], _contents(BUILD10)[2]
        o9, o10 = ChannelArchive(c9), ChannelArchive(c10)
        for arc, tpls in TEX_V10.items():
            a, b = ChannelArchive(o9.get('Dtest/' + arc)), ChannelArchive(o10.get('Dtest/' + arc))
            self.assertEqual(set(a.files), set(b.files), arc)
            for tpl in tpls:
                self.assertNotEqual(a.get(tpl), b.get(tpl), arc + '/' + tpl)   # Japanese -> Korean
                self.assertEqual(len(a.get(tpl)), len(b.get(tpl)), arc + '/' + tpl)   # same GX size

    def test_02a_labels_korean_and_fit(self):
        arc, layout = 'DtestOrder.arc', 'Order/blyt/02a_m_layout.brlyt'
        before = _textboxes(_contents(BUILD9)[2], arc, layout)
        after = _textboxes(_contents(BUILD10)[2], arc, layout)
        m = tf.korean_metrics(); mj = tf.stock_metrics(_contents(BUILD9)[3])
        inner = ChannelArchive(ChannelArchive(_contents(BUILD10)[2]).get('Dtest/' + arc))
        boxes = tf.boxes(inner.get(layout))
        for pane_spec in LAY_V10[arc][layout]:
            pane = pane_spec['pane']
            self.assertEqual(before[pane].rstrip('\0'), pane_spec['ja'], pane)   # v9 still Japanese
            self.assertEqual(after[pane].rstrip('\0'), pane_spec['ko'], pane)    # v10 Korean
            box = boxes[pane][0]
            self.assertTrue(tf.fit(m, mj, box, pane_spec['ja'], pane_spec['ko'])['ok'], pane)


class Wordmark(unittest.TestCase):
    def test_bold_wordmark_differs_and_v10_uses_it(self):
        from kwce.food_menu_art import korean_menu_art, YUME_KO_V7
        orig0 = _contents(FOOD / 'originals/food-japan-v512.wad')[0]
        thin, _ = korean_menu_art(orig0, YUME_KO_V7, bold=False)
        bold, rec = korean_menu_art(orig0, YUME_KO_V7, bold=True)
        self.assertNotEqual(thin, bold)
        self.assertTrue(all(r['bold'] for r in rec))
        # content 0 = korean_banner(korean_menu_art(...)): build-v9 keeps the thin wordmark, build-v10 the bold one
        from kwce.food_banner import korean_banner
        self.assertNotEqual(_contents(BUILD9)[0], _contents(BUILD10)[0])
        self.assertEqual(_contents(BUILD9)[0], korean_banner(thin)[0])
        self.assertEqual(_contents(BUILD10)[0], korean_banner(bold)[0])


class Frozen(unittest.TestCase):
    def test_hashes(self):
        for rel, digest in FROZEN.items():
            self.assertEqual(sha256((FOOD / rel).read_bytes()), digest, rel)


if __name__ == '__main__':
    unittest.main()

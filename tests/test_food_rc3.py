"""rc3 W5 Food tests: Korean address card (name order, 5-digit postal code, reading line),
build-v9 / hardware-v8 parity, v7/v8/hardware-v7 immutability. No Dolphin."""
import json, struct, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
from kwce.channels import load_library, ChannelArchive, layout_sections, sha256
from kwce.wiiroom_formats import decompress_lz11
from kwce import bspatch
from kwce import food_address_card as card

FOOD = ROOT / 'workspace/channels/food'
WIILINK_PATCH = FOOD / 'references/wiilink-patcher/bsdiff__demae__Demae_1_Japan.bsdiff'
BUILD9 = FOOD / 'build-v9/food-ko-local-test.wad'
HW8 = FOOD / 'hardware-v8/food-ko-hardware-test.wad'
FROZEN = {'build-v7/food-ko-local-test.wad': '8b259facbfb4fcc987c2e6288fc6b08c5c850acf5659b2d335ba20646b04dbc5',
          'build-v8/food-ko-local-test.wad': '176a28ccb2b7d3aa4d5f7958aa820651604f2d7ad9905ffe1bc10ea8adb99df9',
          'hardware-v7/food-ko-hardware-test.wad': '1666bf92df94a8b93569c57609068d4e7cb9e35a28f0f796cf204e25907999d9'}
_CACHE = {}


def _title(path):
    if path not in _CACHE:
        lib = load_library(); t = lib.title.Title(); t.load_wad(Path(path).read_bytes())
        _CACHE[path] = (t, [t.get_content_by_index(i) for i in range(t.tmd.num_contents)])
    return _CACHE[path]


def _original():
    return _title(FOOD / 'originals/food-japan-v512.wad')[1]


def _wiilink_dol():
    if 'wl' not in _CACHE:
        _CACHE['wl'] = bspatch.apply(_original()[1], WIILINK_PATCH.read_bytes())
    return _CACHE['wl']


def _pane(layout, name):
    for s in layout_sections(layout):
        if s[:4] in (b'pan1', b'pic1', b'txt1', b'wnd1', b'bnd1') and s[12:28].split(b'\0')[0].decode() == name:
            return s
    raise KeyError(name)


class Executable(unittest.TestCase):
    def test_stock_code_reproduces_the_lead_screen(self):
        # korean-spd fictional data: family 홍 (pd.dat 207), given 길동 (271), zip 00000
        sim = card.simulate(_wiilink_dol(), '홍', '길동', '00000')
        self.assertEqual(sim['main_name'], '길동 홍')          # lead review: '길동 홍 님'
        self.assertEqual(sim['address_name'], '길동 홍')
        self.assertEqual(sim['main_postal'], ['000', '0'])    # lead review: '000-0' + 3 empty boxes
        self.assertEqual(sim['address_postal'], '〒00000')

    def test_patched_code_composes_korean_order(self):
        new, rec = card.patch_address_card(_wiilink_dol())
        self.assertEqual(card.simulate(new, '홍', '길동', '12345'),
                         dict(main_name='홍길동', address_name='홍길동', address_postal='12345', main_postal=['123', '45']))
        # a full name kept in one field still shows once, without a stray separator
        self.assertEqual(card.simulate(new, '', '홍길동', '12345')['main_name'], '홍길동')
        self.assertEqual(card.simulate(new, '홍길동', '', '12345')['address_name'], '홍길동')
        self.assertEqual(rec['edited_words'], 9); self.assertEqual(rec['new_sections'], 0)

    def test_only_nine_words_change_and_sections_stay(self):
        dol = _wiilink_dol(); new, _ = card.patch_address_card(dol)
        self.assertEqual(len(new), len(dol)); self.assertEqual(new[:0x100], dol[:0x100])   # DOL header/section table
        diff = [i for i in range(0, len(dol), 4) if dol[i:i + 4] != new[i:i + 4]]
        self.assertEqual(len(diff), len(card.DOL_EDITS))

    def test_refuses_unexpected_bytes(self):
        dol = bytearray(_wiilink_dol()); va = card.DOL_EDITS[0][0]
        struct.pack_into('>I', dol, card._offset(dol, va), 0x60000000)
        with self.assertRaises(ValueError):
            card.patch_address_card(bytes(dol))

    def test_built_executables_carry_exactly_the_edits(self):
        for path in (BUILD9, HW8):
            dol = decompress_lz11(_title(path)[1][1])
            for va, old, new, _ in card.DOL_EDITS:
                self.assertEqual(card._word(dol, va), new, '%s %08x' % (path.name, va))
            self.assertEqual(card._sections(dol), card._sections(_wiilink_dol()))
        v8 = decompress_lz11(_title(FOOD / 'build-v8/food-ko-local-test.wad')[1][1])
        v9 = decompress_lz11(_title(BUILD9)[1][1])
        diff = [i for i in range(0, len(v8), 4) if v8[i:i + 4] != v9[i:i + 4]]
        self.assertEqual(len(diff), 9)


class Content2(unittest.TestCase):
    def setUp(self):
        self.c8 = _title(FOOD / 'build-v8/food-ko-local-test.wad')[1][2]
        self.c9 = _title(BUILD9)[1][2]

    def _inner(self, c2):
        return ChannelArchive(ChannelArchive(c2).get(card.TITLE_ARC))

    def test_only_three_title_files_change(self):
        a, b = ChannelArchive(self.c8), ChannelArchive(self.c9)
        self.assertEqual(set(a.files), set(b.files))
        self.assertEqual([n for n in a.files if a.get(n) != b.get(n)], [card.TITLE_ARC])
        ia, ib = self._inner(self.c8), self._inner(self.c9)
        self.assertEqual(sorted(n for n in ia.files if ia.get(n) != ib.get(n)),
                         sorted([card.POST_TPL, card.MAIN_LAYOUT, card.ADDRESS_LAYOUT]))

    def test_five_postal_boxes_same_palette(self):
        old, new = self._inner(self.c8).get(card.POST_TPL), self._inner(self.c9).get(card.POST_TPL)
        self.assertEqual(card.box_columns(old), [0, 19, 38, 61, 80, 99, 118])
        self.assertEqual(card.box_columns(new), [0, 19, 38, 57, 76])
        off = card._ci4_layout(new)['offset']
        self.assertEqual(len(new), len(old)); self.assertEqual(new[:off], old[:off])   # header + palette

    def test_digits_line_up_with_the_boxes(self):
        main = self._inner(self.c9).get(card.MAIN_LAYOUT)
        x0 = struct.unpack_from('>f', _pane(main, '01_T_win_post00'), 0x24)[0]
        x1 = struct.unpack_from('>f', _pane(main, '01_T_win_post01'), 0x24)[0]
        # stock: post00 sits 3 units inside box 1; post01 must sit 3 units inside box 4 (19-unit pitch)
        self.assertEqual(x1 - x0, 57.0)
        old = self._inner(self.c8).get(card.MAIN_LAYOUT)
        self.assertEqual(struct.unpack_from('>f', _pane(old, '01_T_win_post01'), 0x24)[0], -133.0)

    def test_reading_lines_hidden_name_and_honorific_kept(self):
        for layout, hidden, kept in ((card.MAIN_LAYOUT, '01_T_win_huriga', ('01_T_win_nama', '01_Tc_win_sama')),
                                     (card.ADDRESS_LAYOUT, 'adT_09_huriga', ('adT_09_user-name', 'adTc_09_sama'))):
            new, old = self._inner(self.c9).get(layout), self._inner(self.c8).get(layout)
            self.assertEqual(len(new), len(old))
            self.assertTrue(_pane(old, hidden)[8] & 1); self.assertFalse(_pane(new, hidden)[8] & 1)
            for name in kept:
                self.assertEqual(_pane(new, name), _pane(old, name))
            sama = _pane(new, kept[1]); off = struct.unpack_from('>I', sama, 0x58)[0]
            self.assertEqual(sama[off:off + 2].decode('utf-16-be'), '님')
            changed = [i for i, (x, y) in enumerate(zip(layout_sections(old), layout_sections(new))) if x != y]
            self.assertEqual(len(changed), 2 if layout == card.MAIN_LAYOUT else 1)


class Builds(unittest.TestCase):
    def test_hardware_v8_region_and_no_loopback(self):
        t, c = _title(HW8)
        self.assertEqual(t.tmd.region, 4)
        dol = decompress_lz11(c[1])
        self.assertNotIn(b'127.0.0', dol); self.assertNotIn(b'localhost', dol)
        m = json.loads((FOOD / 'hardware-v8/build-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(m['hardware_checks']['local_reference_counts'], {'127.0.0': 0, 'localhost': 0})
        self.assertEqual(m['content_revision'], 9); self.assertFalse(m['hardware_success_verified'])

    def test_local_and_hardware_share_non_executable_contents(self):
        local, hw = _title(BUILD9)[1], _title(HW8)[1]
        self.assertEqual([i for i in range(len(local)) if local[i] != hw[i]], [1])

    def test_v9_differs_from_v8_in_contents_1_and_2_only(self):
        v8, v9 = _title(FOOD / 'build-v8/food-ko-local-test.wad')[1], _title(BUILD9)[1]
        self.assertEqual([i for i in range(len(v8)) if v8[i] != v9[i]], [1, 2])
        m = json.loads((FOOD / 'build-v9/build-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(m['wad_sha256'], sha256(BUILD9.read_bytes()))
        self.assertEqual(m['address_card_executable']['edited_words'], 9)

    def test_older_revisions_unchanged(self):
        for rel, digest in FROZEN.items():
            self.assertEqual(sha256((FOOD / rel).read_bytes()), digest, rel)


if __name__ == '__main__':
    unittest.main()

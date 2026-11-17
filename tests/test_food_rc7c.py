"""rc7c Z-Food tests (revision 13 / hardware-v12): the category photo tiles 02_btn_menu_* and the
two 단골 tiles redrawn from the stock texture (exact plate restore from the photo-free sibling +
stock-style Korean lettering, kwce.food_texture_v12 retext `plate`), content-2-only change against
rev 12, and rev <= 12 immutability. No Dolphin.

Run: .venv\\Scripts\\python.exe -m unittest tests.test_food_rc7c
"""
import json, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
from kwce.channels import load_library, ChannelArchive, sha256
from kwce.channel_texture import texture_records
from kwce.food_menu_art import decode_any
from kwce import food_texture_v12 as ft

FOOD = ROOT / 'workspace/channels/food'
STOCK = FOOD / 'originals/food-japan-v512.wad'
BUILD12 = FOOD / 'build-v12/food-ko-local-test.wad'
BUILD13 = FOOD / 'build-v13/food-ko-local-test.wad'
HW11 = FOOD / 'hardware-v11/food-ko-hardware-test.wad'
HW12 = FOOD / 'hardware-v12/food-ko-hardware-test.wad'
ARC = 'DtestOrder.arc'
TEX13 = json.loads((ROOT / 'configs/food-textures-v13-ko.json').read_text(encoding='utf-8'))['textures']
SPECS = TEX13[ARC]
GENRES = ['piz', 'ben', 'sushi', 'wa', 'tyu', 'you', 'fast', 'curry', 'party', 'drink', 'etc']
PHOTO = ['Order/timg/02_btn_menu_%s.tpl' % g for g in GENRES]
REGULAR = ['Order/timg/02_btn_menu_all.tpl', 'Order/timg/02_btn_menu_all_yo.tpl']
FROZEN = {'build-v13/food-ko-local-test.wad': '156e46ed6e1546fdea56016d89d851bfeb3a04f358ca178093ec178c4c8a6de9',
          'hardware-v12/food-ko-hardware-test.wad': 'c9bbda617ed394c5867e09fcb5fe26a232b909a17fc1be2ef0c3725df0f005d9',
          'build-v12/food-ko-local-test.wad': 'b104d47a9915ebfa29a7586100ef0e37ae5799292fb7bcabced717d9a416efb7',
          'hardware-v11/food-ko-hardware-test.wad': 'b99cde1be6e4da3bc2af56411e5c1475b0789efba645b0752ef897530e11ce76',
          'build-v11/food-ko-local-test.wad': 'a70a24d49bd7496ffb927f32c6212ef3f20be53ce4a9ffa602e6a9788966b456',
          'hardware-v10/food-ko-hardware-test.wad': 'e204f1e95b14d67abde7f6aafd753008278c8d3f970e636f08ebf748dfe400bf'}
_CACHE = {}


def _contents(path):
    if path not in _CACHE:
        lib = load_library(); t = lib.title.Title(); t.load_wad(Path(path).read_bytes())
        _CACHE[path] = [t.get_content_by_index(i) for i in range(t.tmd.num_contents)]
    return _CACHE[path]


def _inner(path, arc=ARC):
    return ChannelArchive(ChannelArchive(_contents(path)[2]).get('Dtest/' + arc))


def _img(path, name):
    key = ('img', path, name)
    if key not in _CACHE:
        _CACHE[key] = decode_any(_inner(path).get(name), 0).convert('RGBA')
    return _CACHE[key]


def _plate(spec):
    return ft.plate_image(_inner(STOCK).get(spec['plate']['from']), spec['plate'])


def _lum(p):
    return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]


def _in(rect, x, y):
    return rect[0] <= x < rect[2] and rect[1] <= y < rect[3]


class Contents(unittest.TestCase):
    def test_rev13_changes_content_2_only(self):
        for a, b in ((BUILD12, BUILD13), (HW11, HW12)):
            ca, cb = _contents(a), _contents(b)
            self.assertEqual([i for i in range(len(ca)) if ca[i] != cb[i]], [2], b.parent.name)

    def test_only_the_category_tiles_changed(self):
        for a, b in ((BUILD12, BUILD13), (HW11, HW12)):
            oa, ob = ChannelArchive(_contents(a)[2]), ChannelArchive(_contents(b)[2])
            self.assertEqual(set(oa.files), set(ob.files))
            self.assertEqual([n for n in sorted(oa.files) if oa.get(n) != ob.get(n)], ['Dtest/' + ARC])
            ia, ib = _inner(a), _inner(b)
            self.assertEqual(set(ia.files), set(ib.files))
            self.assertEqual(sorted(f for f in ia.files if ia.get(f) != ib.get(f)), sorted(PHOTO + REGULAR))

    def test_frozen_hashes(self):
        for rel, digest in FROZEN.items():
            self.assertEqual(sha256((FOOD / rel).read_bytes()), digest, rel)

    def test_config_covers_photo_tiles_and_regulars_only(self):
        self.assertEqual(list(TEX13), [ARC]); self.assertEqual(sorted(SPECS), sorted(PHOTO + REGULAR))
        self.assertNotIn('Order/timg/02_btn_menu_NOdata.tpl', SPECS); self.assertNotIn('Order/timg/02_btn_menu_asu.tpl', SPECS)


class Tiles(unittest.TestCase):
    def test_same_gx_format_size_header(self):
        stock = _inner(STOCK)
        for path in (BUILD13, HW12):
            new_in = _inner(path)
            for name in SPECS:
                old, new = stock.get(name), new_in.get(name)
                self.assertEqual(len(new), len(old), name)
                ra, rb = texture_records(old), texture_records(new)
                self.assertEqual([(r['format'], r['width'], r['height'], r['offset']) for r in ra],
                                 [(r['format'], r['width'], r['height'], r['offset']) for r in rb], name)
                self.assertEqual(ra[0]['format'], 6, name)                       # RGBA8: lossless, pixel-exact checks
                self.assertEqual(new[:ra[0]['offset']], old[:ra[0]['offset']], name)
                self.assertNotEqual(new, old, name)

    def test_outside_plate_rect_pixel_identical(self):
        # food photo (x 7-90), 단골 icon (x <= 62), orange frame and its shadow: untouched
        for name, spec in SPECS.items():
            rect = spec['plate']['rect']; a, b = _img(STOCK, name).load(), _img(HW12, name).load()
            self.assertLessEqual(rect[0], 91 if name in PHOTO else 64)
            self.assertGreaterEqual(rect[0], 91 if name in PHOTO else 63)
            bad = [(x, y) for y in range(66) for x in range(172) if not _in(rect, x, y) and a[x, y] != b[x, y]]
            self.assertEqual(bad, [], name)

    def test_no_japanese_trace(self):
        # inside the plate rect the tile is exactly: Korean drawn on the lettering-free plate
        for name, spec in SPECS.items():
            plate = _plate(spec); rect = spec['plate']['rect']
            korean = plate
            for part in spec['parts']:
                korean, _ = ft.draw_shadowed(korean, part)
            k, b, s, p = korean.load(), _img(HW12, name).load(), _img(STOCK, name).load(), plate.load()
            stock_letters = [(x, y) for y in range(rect[1], rect[3]) for x in range(rect[0], rect[2]) if s[x, y] != p[x, y]]
            self.assertGreater(len(stock_letters), 1000, name)                  # the Japanese was there
            for y in range(rect[1], rect[3]):
                for x in range(rect[0], rect[2]):
                    self.assertEqual(b[x, y], k[x, y], (name, x, y))
            footprint = {(x, y) for y in range(66) for x in range(172) if k[x, y] != p[x, y]}
            leftover = [q for q in stock_letters if q not in footprint and b[q] != p[q]]
            self.assertEqual(leftover, [], name)

    def test_stock_lettering_lies_inside_rect(self):
        # nothing of the Japanese can survive outside the restored rect: its exact colours never occur
        # there (right of the photo / icon), and the photo tiles' frame equals the plate template there
        ink = {(0xff, 0xf4, 0xb6), (0x8b, 0x58, 0x2b), (0x9f, 0x8c, 0x6b)}
        for name, spec in SPECS.items():
            rect = spec['plate']['rect']; s = _img(STOCK, name).load(); p = _plate(spec).load()
            out = [(x, y) for y in range(66) for x in range(rect[0], 172) if not _in(rect, x, y)]
            self.assertFalse([q for q in out if s[q][:3] in ink], name)
            if name in PHOTO:
                self.assertFalse([q for q in out if s[q] != p[q]], name)

    def test_plate_template_is_the_stock_plate(self):
        # sibling frame == photo-tile frame; the sibling's own lettering box is flat white plate
        stock = _inner(STOCK); sib = decode_any(stock.get('Order/timg/02b_btn_menu_piz.tpl'), 0).convert('RGBA').load()
        tiles = [decode_any(stock.get('Order/timg/%s_btn_menu_%s.tpl' % (pre, g)), 0).convert('RGBA').load()
                 for pre in ('02', '02b') for g in GENRES]
        tiles += [decode_any(stock.get(n), 0).convert('RGBA').load() for n in REGULAR]
        spec = SPECS[PHOTO[0]]; (bx0, by0, bx1, by1), = spec['plate']['flat']; white = (255, 255, 255, 255)
        for name in PHOTO + REGULAR:
            self.assertEqual(SPECS[name]['plate'], dict(spec['plate'], rect=SPECS[name]['plate']['rect']))
        plate = _plate(spec).load()
        for y in range(66):
            for x in range(172):
                in_box = bx0 <= x < bx1 and by0 <= y < by1
                self.assertEqual(plate[x, y], white if in_box else sib[x, y], (x, y))
        # the sibling's plate interior is pure white except its rounded corners (x <= 14 / >= 150), and the
        # flat box sits well inside: the box is that same flat white
        corner = lambda x, y: (x <= 14 or x >= 150) and (y <= 11 or y >= 52)
        self.assertFalse([(x, y) for x in range(9, 160) for y in range(8, 56)
                          if not (bx0 <= x < bx1 and by0 <= y < by1) and not corner(x, y) and sib[x, y] != white])
        self.assertTrue(bx0 > 14 + 6 and bx1 < 150 - 6 and by0 >= 10 and by1 <= 55)
        # where the plate is used (x >= 64) the stock tiles show it white at >= 99 % of the box pixels; the
        # rest (lettering in every tile) is assumed to continue the flat white interior [추정]
        used = [(x, y) for x in range(64, bx1) for y in range(by0, by1)]
        seen = sum(1 for x, y in used if any(t[x, y] == white for t in tiles))
        self.assertGreaterEqual(seen / len(used), 0.99, (seen, len(used)))
        # the photo-free genre buttons share the frame: outside their lettering they equal the template
        for g in GENRES:
            t = decode_any(stock.get('Order/timg/02b_btn_menu_%s.tpl' % g), 0).convert('RGBA').load()
            self.assertFalse([(x, y) for y in range(66) for x in list(range(0, 27)) + list(range(144, 172)) if t[x, y] != plate[x, y]], g)

    def test_no_dark_plate(self):
        # rev 12 drew a dark scrim; rev 13 has nothing darker than the stock brown outline on the plate
        floor = _lum((0x8b, 0x58, 0x2b)) - 3
        for name, spec in SPECS.items():
            rect = spec['plate']['rect']; new, old = _img(HW12, name).load(), _img(HW11, name).load()
            dark_new = sum(1 for y in range(rect[1], rect[3]) for x in range(rect[0], rect[2]) if _lum(new[x, y]) < floor)
            self.assertEqual(dark_new, 0, name)
            if name in PHOTO:
                dark_old = sum(1 for y in range(rect[1], rect[3]) for x in range(rect[0], rect[2]) if _lum(old[x, y]) < 60)
                self.assertGreater(dark_old, 1000, name)

    def test_stock_lettering_style(self):
        for name, spec in SPECS.items():
            for part in spec['parts']:
                self.assertEqual((part['fill'], part['outline'], part['shadow'], list(part['shadow_offset'])),
                                 ('#fff4b6', '#8b582b', '#9f8c6b', [2, 2]), name)
            # the stock tile carries the same three colours (measured)
            colours = {'%02x%02x%02x' % p[:3] for p in _img(STOCK, name).getdata()}
            self.assertTrue({'fff4b6', '8b582b', '9f8c6b'} <= colours, name)

    def test_even_sizes_and_fit(self):
        sizes = {}
        for name, spec in SPECS.items():
            part, = spec['parts']; ko = part['ko']
            kind = 'two-line' if '\n' in ko else 'long' if len(ko) >= 3 else 'short'
            sizes.setdefault(kind, set()).add((part['size'], part['stroke'], part.get('weight', 0), part.get('scale_x', 1.0)))
            _, meta = ft.draw_shadowed(_plate(spec), part)                    # raises when the block overflows its box
            x0, y0, x1, y1 = meta['block']; bx0, by0, bx1, by1 = part['box']
            self.assertTrue(bx0 <= x0 and by0 <= y0 and x1 <= bx1 and y1 <= by1, name)
            self.assertGreaterEqual(x0, spec['plate']['rect'][0] + 1, name)   # clear of the photo / icon
        self.assertEqual(sizes['short'], {(29, 3, 0.5, 1.0)})
        self.assertEqual(sizes['long'], {(25, 3, 0.5, 0.8)})                  # 도시락
        self.assertEqual(sizes['two-line'], {(20, 2.5, 0.5, 1.0)})

    def test_genre_names_as_rev12(self):
        v11 = json.loads((ROOT / 'configs/food-textures-v11-ko.json').read_text(encoding='utf-8'))['textures'][ARC]
        v12 = json.loads((ROOT / 'configs/food-textures-v12-ko.json').read_text(encoding='utf-8'))['textures'][ARC]
        for name in PHOTO:
            self.assertEqual(SPECS[name]['ko'].replace('\n', ''), v11[name]['ko'].replace('·', ''), name)
            self.assertEqual(SPECS[name]['parts'][0]['ko'], SPECS[name]['ko'])
        self.assertEqual(SPECS[PHOTO[8]]['ko'], '케이\n터링')
        for name in REGULAR:
            self.assertEqual(SPECS[name]['ko'], '단골')
        self.assertEqual(v12['Order/timg/02_btn_menu_all_yo.tpl']['ko'], '단골')

    def test_untouched_neighbours(self):
        # NOdata stays transparent (v11), asu stays the v11 redraw, the 02b buttons stay rev 12
        for name in ('Order/timg/02_btn_menu_NOdata.tpl', 'Order/timg/02_btn_menu_asu.tpl') + tuple(
                'Order/timg/02b_btn_menu_%s.tpl' % g for g in GENRES):
            self.assertEqual(_inner(HW12).get(name), _inner(HW11).get(name), name)
        self.assertTrue(all(p[3] == 0 for p in _img(HW12, 'Order/timg/02_btn_menu_NOdata.tpl').getdata()))


class Module(unittest.TestCase):
    def test_retext_without_plate_unchanged_path(self):
        # a rev 12 spec still goes through the v12 path (byte-identical rev 12 output is checked by FROZEN)
        v12 = json.loads((ROOT / 'configs/food-textures-v12-ko.json').read_text(encoding='utf-8'))['textures'][ARC]
        name = 'Order/timg/02b_btn_menu_piz.tpl'
        new, meta = ft.retext(_inner(STOCK).get(name), v12[name])
        self.assertEqual(new, _inner(HW11).get(name)); self.assertNotIn('plate', meta)

    def test_plate_needs_sibling_and_stock_input(self):
        with self.assertRaises(ValueError):
            ft.retext(_inner(STOCK).get(PHOTO[0]), SPECS[PHOTO[0]])            # no sibling given
        spec = SPECS[PHOTO[0]]
        new, meta = ft.retext(_inner(STOCK).get(PHOTO[0]), spec, plate=_inner(STOCK).get(spec['plate']['from']))
        self.assertEqual(new, _inner(HW12).get(PHOTO[0])); self.assertGreater(meta['removed_pixels'], 1000)


if __name__ == '__main__':
    unittest.main()

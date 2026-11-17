"""Unit tests for the Korean Food (Demae) channel work. No Dolphin, no WAD build.

Run: .venv\\Scripts\\python.exe -m unittest tests.test_food
"""
import json, hashlib, re, unittest, tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
from kwce.channels import load_library, ChannelArchive, sha256
from kwce.wiiroom_formats import decompress_lz11
from kwce import bspatch
from kwce.food_compat import patch_korean_area, SCGETAREA, MATCH_SITE, CAVE
from kwce.food_banner import korean_banner
from kwce.food_fixtures import write_feed, ACTIONS, BLOCKED, CATS, MULTI_ROOT_V2

WAD = ROOT / 'workspace/channels/food/originals/food-japan-v512.wad'
PATCH = ROOT / 'workspace/channels/food/references/wiilink-patcher/bsdiff__demae__Demae_1_Japan.bsdiff'
CFG = ROOT / 'configs/food-executable-v1-ko.json'


def _contents():
    lib = load_library(); t = lib.title.Title(); t.load_wad(WAD.read_bytes())
    return t, [t.get_content_by_index(i) for i in range(t.tmd.num_contents)]


class Identity(unittest.TestCase):
    def test_title(self):
        t, c = _contents()
        self.assertEqual(t.tmd.title_id, '000100014843484a')
        self.assertEqual(t.tmd.boot_index, 9)
        self.assertEqual(t.tmd.num_contents, 10)


class WiiLinkPatch(unittest.TestCase):
    def test_apply(self):
        t, c = _contents()
        wl = bspatch.apply(c[1], PATCH.read_bytes())
        self.assertEqual(wl[:4], b'\x00\x00\x01\x00')         # uncompressed DOL
        self.assertIn(b'food.wiilink24.com', wl)
        self.assertNotIn(b'demae-can.com', wl)
        self.assertEqual(bspatch.describe(PATCH.read_bytes())['new_size'], len(wl))


class KoreanArea(unittest.TestCase):
    def test_bridge_stock_and_wiilink(self):
        t, c = _contents()
        stock = decompress_lz11(c[1])
        wl = bspatch.apply(c[1], PATCH.read_bytes())
        for dol in (stock, wl):
            out, rec = patch_korean_area(dol)
            self.assertEqual(len(out), len(dol))
            self.assertEqual(rec['source_area'], 6)
            self.assertEqual(rec['resource_area'], 0)
            self.assertFalse(rec['hardware_verified'])
            # match site now branches; cave carries cmpwi 6 + li 0
            self.assertEqual(out[_fileoff(out, MATCH_SITE)] >> 2, 0x12)  # branch opcode (18)
            cave_at = _fileoff(out, CAVE)
            self.assertIn(b'\x2c\x03\x00\x06', out[cave_at:cave_at + 24])  # cmpwi r3,6
            # only the match site + cave bytes changed
            diff = [i for i in range(len(dol)) if dol[i] != out[i]]
            self.assertTrue(all(_fileoff(dol, MATCH_SITE) <= i < _fileoff(dol, MATCH_SITE) + 4
                                or _fileoff(dol, CAVE) <= i < _fileoff(dol, CAVE) + 24 for i in diff))

    def test_refuses_wrong_bytes(self):
        with self.assertRaises(ValueError):
            patch_korean_area(b'\x00' * 0x600000)


def _fileoff(dol, va):
    import struct
    off = struct.unpack_from('>18I', dol, 0); addr = struct.unpack_from('>18I', dol, 0x48); size = struct.unpack_from('>18I', dol, 0x90)
    for i in range(18):
        if size[i] and addr[i] <= va < addr[i] + size[i]:
            return off[i] + va - addr[i]
    raise AssertionError('va not mapped')


class Banner(unittest.TestCase):
    def test_korean_names(self):
        t, c = _contents()
        out, rec = korean_banner(c[0])
        self.assertEqual(len(out), len(c[0]))
        self.assertEqual(out[0x9c:0x9c + 16].decode('utf-16-be'), '음식 배달 채널')
        # MD5 integrity field recomputed consistently
        from kwce.food_banner import _imet_md5, MD5_AT
        self.assertEqual(_imet_md5(out), out[MD5_AT:MD5_AT + 16])


class Executable(unittest.TestCase):
    def test_config_fits_and_present(self):
        t, c = _contents()
        dol = decompress_lz11(c[1])
        cfg = json.loads(CFG.read_text(encoding='utf-8'))
        self.assertEqual(sha256(dol), cfg['source_sha256'])
        self.assertGreaterEqual(len(cfg['utf16']), 40)
        self.assertEqual(cfg['sjis'], {})     # Shift-JIS cannot carry Hangul
        for src, tgt in cfg['utf16'].items():
            needle = src.encode('utf-16-be') + b'\0\0'
            at = dol.find(needle)
            self.assertGreaterEqual(at, 0, 'missing ' + repr(src[:12]))
            end = at + len(src.encode('utf-16-be')); slot = end + 2
            while slot + 2 <= len(dol) and dol[slot:slot + 2] == b'\0\0':
                slot += 2
            self.assertLessEqual(len(tgt.encode('utf-16-be')) + 2, slot - at, 'overflow ' + repr(tgt[:12]))
            self.assertEqual(re.findall(r'%[-+0-9.*]*[a-zA-Z]', src), re.findall(r'%[-+0-9.*]*[a-zA-Z]', tgt))

    def test_apply_and_redirect(self):
        import build_food
        t, c = _contents()
        dol = decompress_lz11(c[1])
        cfg = json.loads(CFG.read_text(encoding='utf-8'))
        out, n = build_food.apply_executable(dol, cfg)
        self.assertGreaterEqual(n, len(cfg['utf16']))
        self.assertEqual(len(out), len(dol))
        out2, ep = build_food.redirect_endpoints(out)
        self.assertEqual(ep['hosts'], 4)
        self.assertNotIn(b'demae-can.com', out2)
        self.assertEqual(out2.count(b'127.0.0.2'), 4)
        self.assertIn(b'http://\x00\x00http://', out2)


class PersonalData(unittest.TestCase):
    def test_pd_library_uses_bridged_scgetarea(self):
        from kwce import food_personal_data as fpd
        t, c = _contents()
        stock = decompress_lz11(c[1]); wl = bspatch.apply(c[1], PATCH.read_bytes())
        for dol in (stock, wl):
            for site in sum(fpd.CALL_SITES.values(), []):
                w = int.from_bytes(dol[_fileoff(dol, site):_fileoff(dol, site) + 4], 'big')
                self.assertEqual(w >> 26, 18); self.assertTrue(w & 1)          # bl
                d = w & 0x3fffffc
                if d & 0x2000000:
                    d -= 0x4000000
                self.assertEqual(site + d, fpd.SCGETAREA, hex(site))
        table = lambda dol, off: dol[_fileoff(dol, fpd.PATH_TABLE + off):].split(b'\0', 1)[0].decode()
        self.assertEqual(table(stock, 0), fpd.PD_PATH)                       # JPN slot = HCCJ
        for off in (0, 44, 88):                                              # WiiLink: all HCCJ
            self.assertEqual(table(wl, off), fpd.PD_PATH)

    def test_fictional_variants(self):
        from kwce import food_personal_data as fpd
        from kwce import personal_data_format as fmt
        for name in ('korean', 'jp-compatible'):
            plain = fpd.variant(name)
            fmt.check(plain)
            s = fpd.summary(plain)
            self.assertTrue(s['home_address_set'] and s['kana_set'])
            self.assertFalse(s['pin_protected'])
            enc = fmt.encrypt(plain, fmt.DOLPHIN_DEFAULT_DEVICE_ID)
            self.assertEqual(fmt.decrypt(enc, fmt.DOLPHIN_DEFAULT_DEVICE_ID), plain)
        self.assertTrue(fpd.summary(fpd.variant('jp-compatible'))['sjis_encodable'])

    def test_bridge_in_both_builds(self):
        from kwce.food_compat import CAVE as cave
        lib = load_library(); seen = 0
        for p in sorted((ROOT / 'workspace/channels/food').glob('*-v*/food-ko-*-test.wad')):
            # This bridge belongs to the standard Korean/Japanese-compatible
            # builds. Named service editions have their own endpoint checks.
            if not re.fullmatch(r'(?:build|hardware)-v\d+', p.parent.name):
                continue
            rel = p.parent.name; seen += 1
            t = lib.title.Title(); t.load_wad(p.read_bytes())
            dol = decompress_lz11(t.get_content_by_index(1))
            w = int.from_bytes(dol[_fileoff(dol, MATCH_SITE):_fileoff(dol, MATCH_SITE) + 4], 'big')
            d = w & 0x3fffffc
            if d & 0x2000000:
                d -= 0x4000000
            self.assertEqual((w >> 26, MATCH_SITE + d), (18, cave), rel)
            at = _fileoff(dol, cave)
            self.assertIn(b'\x2c\x03\x00\x06', dol[at:at + 24], rel)
            local = rel.startswith('build-')
            self.assertEqual(b'127.0.0.2' in dol, local, rel)
            if local:
                self.assertEqual(dol.count(b'127.0.0.2'), 4, rel)
                self.assertNotIn(b'demae-can.com', dol, rel); self.assertNotIn(b'wiilink24', dol, rel)
            else:
                self.assertIn(b'food.wiilink24.com', dol, rel)
        if not seen:
            self.skipTest('no builds present')


class ExecutableV3(unittest.TestCase):
    def test_v3_table(self):
        import make_food_translations_v3 as gen
        cfg = json.loads((ROOT / 'configs/food-executable-v3-ko.json').read_text(encoding='utf-8'))
        t, c = _contents()
        wl = bspatch.apply(c[1], PATCH.read_bytes())
        self.assertEqual(sha256(wl), cfg['source_sha256'])
        glyphs = gen.korean_font_map()
        for src, tgt in cfg['utf16'].items():
            slots = gen.literal_slots(wl, src)
            self.assertTrue(slots, 'not a whole literal: ' + repr(src[:12]))
            self.assertTrue(all(len(tgt.encode('utf-16-be')) + 2 <= e - s for s, e in slots), repr(tgt[:12]))
            self.assertEqual([ch for ch in tgt if ch != '\n' and ord(ch) not in glyphs], [], repr(tgt[:12]))
        for token in ('Meal', 'Pizza', 'Sushi'):   # protocol tokens untouched
            self.assertNotIn(token, cfg['utf16'])
        self.assertGreaterEqual(len(cfg['utf16']), 110)


class HomeCsv(unittest.TestCase):
    def test_all_columns_korean(self):
        from kwce.food_resources import korean_home_csv, HOME_CSV
        t, c = _contents()
        raw = ChannelArchive(c[2]).get(HOME_CSV)
        out, rec = korean_home_csv(raw)
        cells = re.findall(r'"([^"]*)"', out[2:].decode('utf-16-be'))
        self.assertEqual(len(cells), 40)
        for r in range(4):
            self.assertEqual(len(set(cells[r * 10:(r + 1) * 10])), 1)
        self.assertTrue(cells[20].startswith('Wii 메뉴로'))
        self.assertEqual(rec['glyphs_missing'], 0)


class Feed(unittest.TestCase):
    def test_browse_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = Path(tmp) / 'local-feed'
            m = write_feed(feed)
            self.assertTrue(m['local_only'] and m['synthetic'])
            for action in BLOCKED:
                self.assertEqual(list((feed / 'nwapi').glob(action + '*.xml')), [], action)
            for action in ACTIONS:
                self.assertTrue(list((feed / 'nwapi').glob(action + '*.xml')), action)
            # every served file is well-formed Shift-JIS XML
            import xml.dom.minidom as dom
            for p in (feed / 'nwapi').glob('*.xml'):
                dom.parseString(p.read_bytes().decode('shift-jis'))

    def test_v1_regenerates_identically(self):
        ref = ROOT / 'workspace/channels/food/local-feed-v1'
        with tempfile.TemporaryDirectory() as tmp:
            m = write_feed(Path(tmp), 1)
            for name in m['files'] + ['fixture-manifest.json']:
                self.assertEqual(sha256((Path(tmp) / name).read_bytes()), sha256((ref / name).read_bytes()), name)

    def test_v2_wiilink_shape(self):
        import xml.dom.minidom as dom
        with tempfile.TemporaryDirectory() as tmp:
            feed = Path(tmp)
            m = write_feed(feed, 2)
            self.assertEqual(m['revision'], 2)
            self.assertEqual(sorted(m['sha256']), sorted(m['files']))
            for action in BLOCKED:
                self.assertEqual(list((feed / 'nwapi').glob(action + '*.xml')), [], action)

            def elements(nodes):
                return [n for n in nodes if n.nodeType == n.ELEMENT_NODE]

            for name in m['files']:
                if not name.endswith('.xml'):
                    continue
                text = (feed / name).read_bytes().decode('shift-jis')
                roots = elements(dom.parseString('<doc>' + text + '</doc>').documentElement.childNodes)
                action = name[len('nwapi/'):-len('.xml')]
                if any(action.startswith(a) for a in MULTI_ROOT_V2):
                    tail = [r.tagName for r in roots[-2:]]
                else:  # @response: status nodes are the last two children of <response>
                    self.assertEqual(roots[0].tagName, 'response', name)
                    tail = [c.tagName for c in elements(roots[0].childNodes)[-2:]]
                self.assertEqual(tail, ['apiStatus', 'version'], name)
            cats = (feed / 'nwapi/webApi_category_list.xml').read_text(encoding='shift-jis')
            self.assertIn('<Placeholder>', cats)
            self.assertEqual(cats.count('<Shop>'), sum(len(c[3]) for c in CATS))
            self.assertIn('<menu2>', (feed / 'nwapi/webApi_menu_list.xml').read_text(encoding='shift-jis'))
            self.assertIn('<selectedArea>', (feed / 'nwapi/webApi_area_list.xml').read_text(encoding='shift-jis'))

    def test_v3_every_category_has_a_shop(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = Path(tmp)
            m = write_feed(feed, 3)
            self.assertEqual(m['revision'], 3)
            for action in BLOCKED:
                self.assertEqual(list((feed / 'nwapi').glob(action + '*.xml')), [], action)
            cats = (feed / 'nwapi/webApi_category_list.xml').read_text(encoding='shift-jis')
            self.assertNotIn('<Shop/>', cats)
            self.assertEqual(cats.count('<TestingCategory>'), 12)
            self.assertEqual(cats.count('<Shop>'), 12 + sum(len(c[3]) for c in CATS) - 3)
            self.assertTrue(cats.rstrip().endswith('<version><![CDATA[1]]></version>'))

    def test_v4_shop_list_single_category(self):
        import xml.dom.minidom as dom
        with tempfile.TemporaryDirectory() as tmp:
            feed = Path(tmp)
            write_feed(feed, 4)
            text = (feed / 'nwapi/webApi_shop_list.xml').read_text(encoding='shift-jis')
            root = dom.parseString(text).documentElement  # one root: a normal response
            names = [c.tagName for c in root.childNodes if c.nodeType == c.ELEMENT_NODE]
            self.assertEqual((root.tagName, names), ('response', ['Pizza', 'version', 'apiStatus']))
            self.assertNotIn('Placeholder', text)
            self.assertIn('<Placeholder>', (feed / 'nwapi/webApi_category_list.xml').read_text(encoding='shift-jis'))


class Revision4(unittest.TestCase):
    def test_content2_rev4_layouts_and_tiles(self):
        from kwce.food_resources import korean_content2
        t, c = _contents()
        base2, _ = korean_content2(c[2], revision=2)
        out, rec = korean_content2(c[2], revision=4)
        self.assertIn('v4_layouts', rec); self.assertIn('v4_textures', rec)
        # rev4 translates the welcome + address layouts and the category tiles
        self.assertIn('DtestWelcome.arc', rec['v4_layouts'])
        tiles = sum(len(v) for v in rec['v4_textures'].values())
        self.assertGreaterEqual(tiles, 15)
        # rev4 changes at least the arcs rev2 did, plus Welcome/Order layouts
        self.assertNotEqual(out, base2)

    def test_v4_exec_has_area_confirm(self):
        import json
        cfg = json.loads((ROOT / 'configs/food-executable-v4-ko.json').read_text(encoding='utf-8'))
        self.assertIn('\n\nこれで正しいですか？', cfg['utf16'])
        self.assertGreaterEqual(len(cfg['utf16']), 115)

    def test_korean_name_order(self):
        from kwce import food_personal_data as fpd, personal_data_format as fmt
        f = fmt.fields(fpd.variant('korean'))
        self.assertEqual(f['last_name'], '')            # family field cleared
        self.assertGreaterEqual(len(f['first_name']), 2)  # full Korean name in given field
        self.assertFalse(f['pin_protected'])


if __name__ == '__main__':
    unittest.main()

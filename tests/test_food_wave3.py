"""Wave-3 Food tests: Korean save-data banner (content-2 Dtest/Nand/banner.tpl),
build-v8 / hardware-v7 parity, and v1-v7 immutability. No Dolphin."""
import json, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
from kwce.channels import load_library, ChannelArchive, sha256
from kwce import tpl
from kwce.food_save_banner import korean_save_banner, BANNER, WORD_KO

FOOD = ROOT / 'workspace/channels/food'
BUILD7 = FOOD / 'build-v7/food-ko-local-test.wad'
BUILD8 = FOOD / 'build-v8/food-ko-local-test.wad'
HW7 = FOOD / 'hardware-v7/food-ko-hardware-test.wad'
MASCOT_BOX = (72, 3, 110, 41)   # isolated-mascot bounding box (extract_chef2)


def _original_content2():
    lib = load_library(); t = lib.title.Title()
    t.load_wad((FOOD / 'originals/food-japan-v512.wad').read_bytes())
    return t.get_content_by_index(2)


def _orange(c):
    r, g, b, a = c
    return a >= 90 and r > 165 and 30 < g < 205 and b < 125 and (r - b) > 70


def _mascot_orange(img):
    x0, y0, x1, y1 = MASCOT_BOX
    px = img.load()
    return sum(1 for x in range(x0, x1 + 1) for y in range(y0, y1 + 1) if _orange(px[x, y]))


class SaveBanner(unittest.TestCase):
    def setUp(self):
        self.c2 = _original_content2()
        self.new, self.rec = korean_save_banner(self.c2)

    def test_only_banner_tpl_changes(self):
        a, b = ChannelArchive(self.c2), ChannelArchive(self.new)
        self.assertEqual(set(a.files), set(b.files))
        changed = [n for n in a.files if a.get(n) != b.get(n)]
        self.assertEqual(changed, [BANNER])

    def test_banner_stays_192x64_rgb5a3(self):
        raw = ChannelArchive(self.new).get(BANNER)
        recs = tpl.texture_records(raw)
        self.assertEqual(len(recs), 1)
        self.assertEqual((recs[0]['width'], recs[0]['height'], recs[0]['format']), (192, 64, 5))
        self.assertEqual(len(raw), len(ChannelArchive(self.c2).get(BANNER)))

    def test_mascot_preserved_and_wordmark_changed(self):
        old = tpl.decode(ChannelArchive(self.c2).get(BANNER), 0)
        new = tpl.decode(ChannelArchive(self.new).get(BANNER), 0)
        # mascot orange mass is preserved (re-quantized, so allow a small tolerance)
        self.assertGreater(_mascot_orange(new), 300)
        self.assertLessEqual(abs(_mascot_orange(new) - _mascot_orange(old)), 40)
        # the wordmark band (below the mascot) is redrawn -> differs from stock
        px_old, px_new = old.load(), new.load()
        band_diff = sum(1 for x in range(192) for y in range(44, 64) if px_old[x, y] != px_new[x, y])
        self.assertGreater(band_diff, 150)
        self.assertEqual(self.rec['wordmark'], WORD_KO)
        self.assertTrue(self.rec['mascot_preserved'])

    def test_deterministic(self):
        again, _ = korean_save_banner(self.c2)
        self.assertEqual(self.new, again)


class RevisionGating(unittest.TestCase):
    def test_rev7_does_not_touch_banner_but_rev8_does(self):
        from kwce.food_resources import korean_content2
        orig = _original_content2()
        c7 = korean_content2(orig, revision=7)[0]
        c8 = korean_content2(orig, revision=8)[0]
        a, b7, b8 = ChannelArchive(orig), ChannelArchive(c7), ChannelArchive(c8)
        self.assertEqual(a.get(BANNER), b7.get(BANNER))      # rev<=7 leaves the save banner Japanese
        self.assertNotEqual(a.get(BANNER), b8.get(BANNER))   # rev8 localizes it
        # rev8 == rev7 everywhere else
        other = [n for n in a.files if n != BANNER and b7.get(n) != b8.get(n)]
        self.assertEqual(other, [])


@unittest.skipUnless(BUILD8.exists() and HW7.exists(), 'build-v8 / hardware-v7 not built')
class BuildV8(unittest.TestCase):
    def _title(self, path):
        lib = load_library(); t = lib.title.Title(); t.load_wad(path.read_bytes()); return t

    def test_v8_differs_from_v7_only_in_save_banner(self):
        v7, v8 = self._title(BUILD7), self._title(BUILD8)
        diff = [i for i in range(v7.tmd.num_contents) if v7.get_content_by_index(i) != v8.get_content_by_index(i)]
        self.assertEqual(diff, [2])
        a, b = ChannelArchive(v7.get_content_by_index(2)), ChannelArchive(v8.get_content_by_index(2))
        self.assertEqual([n for n in a.files if a.get(n) != b.get(n)], [BANNER])

    def test_region_and_manifest(self):
        for path in (BUILD8, HW7):
            t = self._title(path)
            self.assertEqual(t.tmd.region, 4)
            self.assertEqual((t.tmd.title_id, t.tmd.boot_index), ('000100014843484a', 9))
            meta = json.loads(path.with_name('build-manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(meta['wad_sha256'], sha256(path.read_bytes()))
            self.assertIn('save_banner', meta['content2'])

    def test_v8_local_and_hw7_share_content2(self):
        self.assertEqual(self._title(BUILD8).get_content_by_index(2), self._title(HW7).get_content_by_index(2))

    def test_hw7_keeps_live_host_no_loopback(self):
        from kwce.wiiroom_formats import decompress_lz11
        dol = decompress_lz11(self._title(HW7).get_content_by_index(1))
        self.assertIn(b'food.wiilink24.com', dol)
        self.assertNotIn(b'127.0.0', dol)


if __name__ == '__main__':
    unittest.main()

"""Photo Prints revision 12: Korean manual.jpg, save-data banner and HOME network prompt.

Synthetic tests always run. Tests marked 'local data' use the project's own
ignored builds and are skipped when those files are absent.
"""
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import photoprints_manual as pm  # noqa: E402

BASE = ROOT / 'workspace/channels/photoprints'
PAIRS = ((BASE / 'build-v11/photoprints-ko-local-test.wad', BASE / 'build-v12/photoprints-ko-local-test.wad'),
         (BASE / 'hardware-v7/photoprints-ko-hardware-test.wad', BASE / 'hardware-v8/photoprints-ko-hardware-test.wad'))


def _csv(rows):
    return b'\xfe\xff' + ''.join('\t'.join(f'"{c}"' for c in row) + '\r\n' for row in rows).encode('utf-16-be')


class NetworkPrompt(unittest.TestCase):
    KO = 'Wii 메뉴로 돌아가시겠습니까?\r\n(저장되지 않은 내용은 사라집니다)'

    def home(self, ko=KO):
        rows = [[f'r{r}c{c}' for c in range(10)] for r in range(4)]
        rows[2][9] = ko
        return _csv(rows)

    def network(self):
        return b'\xfe\xff' + ('\t'.join(f'"{c}"' for c in ['JP', pm.NETWORK_SOURCE, 'DE', 'FR', 'ES', 'IT', 'NL']) + '\r\n').encode('utf-16-be')

    def test_ten_columns_with_home_korean(self):
        out, rec = pm.korean_network_csv(self.network(), self.home())
        cells = pm._cells(out)
        self.assertEqual(len(cells), 10)
        self.assertEqual(cells[9], self.KO)
        self.assertEqual(cells[7:9], [pm.NETWORK_SOURCE] * 2)  # SC/TC keep English, as in Kirby TV
        self.assertEqual((rec['columns_before'], rec['columns_after'], rec['korean_column']), (7, 10, 9))

    def test_rejects_other_home_text(self):
        with self.assertRaises(ValueError):
            pm.korean_network_csv(self.network(), self.home(ko='리셋하시겠습니까?'))


class ManualLayout(unittest.TestCase):
    def test_tables(self):
        self.assertEqual(len(pm.ROW_TEXTS), len(pm.ROWS))
        self.assertEqual(len(pm.JAPANESE['rows']), len(pm.ROWS))
        for (a0, a1), (b0, b1) in zip(pm.ROWS, pm.ROWS[1:]):
            self.assertLess(a0, a1)
            self.assertLessEqual(a1, b0)
        self.assertLessEqual(pm.ROWS[-1][1], pm.MANUAL_SIZE[1])
        self.assertLess(pm.TEXT_X, pm.TEXT_RIGHT)
        self.assertLess(pm.TEXT_RIGHT, pm.RIGHT_CELL[1])
        self.assertTrue(all(any('\uac00' <= c <= '\ud7a3' for c in t) for t in pm.ROW_TEXTS + [pm.HEADER_TEXT]))


@unittest.skipUnless(all(p.exists() for pair in PAIRS for p in pair), 'local data')
class Revision12(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kwce.channels import load_library
        cls.lib = load_library()

    def load(self, path):
        t = self.lib.title.Title()
        t.load_wad(path.read_bytes())
        return t

    def test_reproduces(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import build_photoprints_v12 as b12
        (local, local_meta), (hardware, hardware_meta), _ = b12.build()
        self.assertEqual(local, PAIRS[0][1].read_bytes())
        self.assertEqual(hardware, PAIRS[1][1].read_bytes())
        stored = json.loads((BASE / 'build-v12/build-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(stored['wad_sha256'], local_meta['wad_sha256'])
        self.assertFalse(stored['full_localization_complete'] or stored['hardware_success_verified'])

    def test_scope_and_resources(self):
        from kwce.channels import ChannelArchive
        from kwce.hardware import local_reference_counts
        from kwce import tpl
        from libWiiPy.archive import decompress_lz77
        from PIL import Image, JpegImagePlugin
        new_c2 = []
        for old_path, new_path in PAIRS:
            old, new = self.load(old_path), self.load(new_path)
            n = old.tmd.num_contents
            self.assertEqual([i for i in range(n) if old.get_content_by_index(i) != new.get_content_by_index(i)], [2])
            a, b = ChannelArchive(old.get_content_by_index(2)), ChannelArchive(new.get_content_by_index(2))
            self.assertEqual(set(a.files), set(b.files))
            self.assertEqual(sorted(f for f in a.files if a.get(f) != b.get(f)), sorted([pm.MANUAL, pm.BANNER, pm.NETWORK]))
            self.assertEqual(new.tmd.region, old.tmd.region)
            self.assertEqual(local_reference_counts(new), local_reference_counts(old))
            new_c2.append(new.get_content_by_index(2))
            # manual.jpg: same size, baseline 4:4:4, original quantisation, not larger; icons untouched
            m0, m1 = a.get(pm.MANUAL), b.get(pm.MANUAL)
            i0, i1 = Image.open(io.BytesIO(m0)), Image.open(io.BytesIO(m1))
            self.assertEqual(i1.size, (556, 257))
            self.assertFalse(i1.info.get('progressive'))
            self.assertEqual(JpegImagePlugin.get_sampling(i1), 0)
            self.assertEqual(i1.quantization, i0.quantization)
            self.assertLessEqual(len(m1), len(m0))
            g0, g1 = i0.convert('L'), i1.convert('L')
            for y0, y1 in pm.ROWS[1:]:   # control icons of rows 2-5 and the grid
                box = (8, y0 + 1, 98, y1 - 1)
                d = [abs(p - q) for p, q in zip(g0.crop(box).getdata(), g1.crop(box).getdata())]
                self.assertLess(sum(d) / len(d), 3.0)
            # save banner: one RGB5A3 192x64 texture; outside the erase box the pixels are unchanged
            t0, t1 = decompress_lz77(a.get(pm.BANNER)), decompress_lz77(b.get(pm.BANNER))
            self.assertEqual(len(t0), len(t1))
            p0, p1 = tpl.decode(t0, 0).convert('RGBA'), tpl.decode(t1, 0).convert('RGBA')
            x0, y0, x1, y1 = pm.BANNER_ERASE
            outside = [(x, y) for y in range(64) for x in range(192) if not (x0 <= x < x1 and y0 <= y < y1)]
            self.assertTrue(all(p0.getpixel(xy) == p1.getpixel(xy) for xy in outside))
            self.assertNotEqual(p0.crop(pm.BANNER_ERASE).tobytes(), p1.crop(pm.BANNER_ERASE).tobytes())
            # network prompt: ten columns, Korean glyphs all used by the Korean HOME messages
            cells = pm._cells(b.get(pm.NETWORK))
            home = pm._cells(b.get(pm.HOME))
            self.assertEqual(len(cells), 10)
            self.assertTrue(set(cells[9]) <= set(''.join(home[r * 10 + 9] for r in range(4))))
            self.assertEqual(pm._cells(a.get(pm.NETWORK)), cells[:7])
        self.assertEqual(new_c2[0], new_c2[1])  # local and hardware share content 2
        self.assertTrue(self.load(PAIRS[1][1]).get_is_fakesigned())


if __name__ == '__main__':
    unittest.main()

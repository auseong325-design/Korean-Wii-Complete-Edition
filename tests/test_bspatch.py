import bz2
import hashlib
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import bspatch  # noqa: E402


def offt(value):
    return (abs(value) | (1 << 63 if value < 0 else 0)).to_bytes(8, 'little')


def make_patch(steps, diff, extra, new_size):
    control = b''.join(offt(a) + offt(b) + offt(c) for a, b, c in steps)
    c, d, e = bz2.compress(control), bz2.compress(diff), bz2.compress(extra)
    return b'BSDIFF40' + offt(len(c)) + offt(len(d)) + offt(new_size) + c + d + e


class BspatchTest(unittest.TestCase):
    def test_synthetic_add_copy_seek(self):
        old = bytes(range(16))
        # add 4 bytes (+1 each), copy 2 extra bytes, seek back 2, add 3 (+0)
        patch = make_patch([(4, 2, -2), (3, 0, 0)], bytes([1, 1, 1, 1, 0, 0, 0]), b'XY', 9)
        self.assertEqual(bspatch.apply(old, patch), bytes([1, 2, 3, 4]) + b'XY' + bytes([2, 3, 4]))

    def test_rejects_overrun(self):
        patch = make_patch([(20, 0, 0)], bytes(20), b'', 4)
        with self.assertRaises(ValueError):
            bspatch.apply(b'abcd', patch)

    def test_wiilink_food_patches_produce_valid_structures(self):
        # WiiLink's own TMD keeps the stock content hashes (libWiiPy recomputes
        # records when dumping), so it cannot serve as a hash reference. Check
        # that each patched content parses as the expected container instead.
        base = ROOT / 'workspace/channels/food'
        wad = base / 'originals/food-japan-v512.wad'
        refs = base / 'references/wiilink-patcher'
        if not wad.exists() or not (refs / 'bsdiff__demae__Demae_1_Japan.bsdiff').exists():
            self.skipTest('ignored originals not present')
        from kwce.channels import load_library, ChannelArchive
        from kwce.wiiroom_formats import decompress_lz11
        lib = load_library()
        title = lib.title.Title()
        title.load_wad(wad.read_bytes())
        stock = [title.get_content_by_index(i) for i in range(3)]
        japan = bspatch.apply(stock[1], (refs / 'bsdiff__demae__Demae_1_Japan.bsdiff').read_bytes())
        self.assertEqual(struct.unpack_from('>I', japan, 0)[0], 0x100)  # raw DOL, text0 at 0x100
        self.assertEqual(len(japan), len(decompress_lz11(bspatch.apply(stock[1], (refs / 'bsdiff__demae__Demae_1_English.bsdiff').read_bytes()))))
        banner = bspatch.apply(stock[0], (refs / 'bsdiff__demae__Demae_0_English.bsdiff').read_bytes())
        self.assertIn(b'IMET', (banner[0x40:0x44], banner[0x80:0x84]))
        resources = ChannelArchive(bspatch.apply(stock[2], (refs / 'bsdiff__demae__Demae_2_English.bsdiff').read_bytes()))
        self.assertEqual(len(resources.files), len(ChannelArchive(stock[2]).files))
        self.assertNotEqual(hashlib.sha256(japan).digest(), hashlib.sha256(stock[1]).digest())


if __name__ == '__main__':
    unittest.main()

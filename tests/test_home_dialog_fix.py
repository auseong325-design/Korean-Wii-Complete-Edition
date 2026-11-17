"""Food hardware-v18 / Nintendo v20: HOME dialog keeps its layout font size; Food HOME projection 228."""
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = dict(food=('hardware-v17', 'hardware-v18', 'food-ko-hardware-test.wad', True),
             nintendo=('build-v19', 'build-v20', 'nintendo-ko-ui-test.wad', False))


def contents(path):
    from kwce.channels import load_library
    t = load_library().title.Title(); t.load_wad(path.read_bytes())
    return [t.get_content_by_index(i) for i in range(len(t.tmd.content_records))]


class HomeDialogFixTests(unittest.TestCase):
    def check(self, channel):
        from kwce import home_dialog_fix as fix
        from kwce.ppc_patch import to_file
        from kwce.wiiroom_formats import decompress_lz11
        parent, child, name, compressed = PAIRS[channel]
        a, b = (ROOT / f'workspace/channels/{channel}/{d}/{name}' for d in (parent, child))
        if not (a.is_file() and b.is_file()): self.skipTest('builds not present')
        old, new = contents(a), contents(b)
        self.assertEqual([i for i in range(len(old)) if old[i] != new[i]], [1])
        x, y = (decompress_lz11(c[1]) if compressed else c[1] for c in (old, new))
        spec = fix.FOOD if channel == 'food' else fix.NINTENDO
        sites = {to_file(x, s, 4): (o, n) for s, o, n in spec['edits']}
        self.assertEqual(len(x), len(y))
        diff = sorted({i - i % 4 for i in range(len(x)) if x[i] != y[i]})
        self.assertEqual(diff, sorted(sites))
        for at, (o, n) in sites.items():
            self.assertEqual(struct.unpack_from('>I', x, at)[0], o)
            self.assertEqual(struct.unpack_from('>I', y, at)[0], n)

    def test_food(self): self.check('food')
    def test_nintendo(self): self.check('nintendo')


if __name__ == '__main__':
    unittest.main()

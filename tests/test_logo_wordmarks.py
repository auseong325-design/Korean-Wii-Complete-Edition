"""Wii Room build-v66 (candidate K) and Mii Contest build-v32 (candidate B): only wordmark resources change."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOM = {n: ROOT / f'workspace/channels/wiiroom/build-v{n}/wiiroom-ko-local-test.wad' for n in (60, 66)}
MII = {n: ROOT / f'workspace/channels/mii-contest/build-v{n}/mii-contest-ko-ui-test.wad' for n in (31, 32)}


def contents(path):
    from kwce.channels import load_library
    t = load_library().title.Title(); t.load_wad(path.read_bytes())
    return [t.get_content_by_index(i) for i in range(len(t.tmd.content_records))]


class LogoWordmarkTests(unittest.TestCase):
    @unittest.skipUnless(all(p.is_file() for p in ROOM.values()), 'Wii Room v60/v66 not present')
    def test_wiiroom_changes_only_banner_and_resources(self):
        old, new = contents(ROOM[60]), contents(ROOM[66])
        self.assertEqual([i for i in range(len(old)) if old[i] != new[i]], [0, 2])
        self.assertEqual(len(old[2]), len(new[2]))
        meta = json.loads((ROOM[66].parent / 'build-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual((meta['parent_revision'], meta['wordmark_v62']['narrow']), (60, 0.94))

    def test_wiiroom_letter_gaps_are_even(self):
        from kwce import wiiroom_wordmark_v62 as wm
        t = wm.tight_targets('banner'); f = wm.ink_fractions(wm.letter_mask)
        stem_right = t['Rect_b'][0] + 6.5
        no_left, no_right = t['No'][0] - 40 + 80 * f['의'][0], t['No'][0] - 40 + 80 * f['의'][1]
        ma_left = t['Ma'][0] - 40 + 80 * f['방'][0]
        self.assertAlmostEqual(no_left - stem_right, 13, delta=0.1)
        self.assertAlmostEqual(ma_left - no_right, 13, delta=0.1)
        self.assertAlmostEqual(t['Rect_b'][0] - t['Rect_a'][0], 26, delta=0.01)     # native i-to-i spacing kept

    @unittest.skipUnless(all(p.is_file() for p in MII.values()), 'Mii Contest v31/v32 not present')
    def test_mii_contest_changes_only_six_banner_letters(self):
        from kwce.channels import ChannelArchive, load_library
        load_library()
        from libWiiPy.archive import decompress_lz77
        old, new = contents(MII[31]), contents(MII[32])
        self.assertEqual([i for i in range(len(old)) if old[i] != new[i]], [0])
        arcs = [ChannelArchive(c[0x640:]) for c in (old[0], new[0])]
        self.assertEqual(arcs[0].get('meta/icon.bin'), arcs[1].get('meta/icon.bin'))
        a, b = (ChannelArchive(decompress_lz77(x.get('meta/banner.bin')[32:])) for x in arcs)
        changed = sorted(p.rsplit('/', 1)[-1] for p in a.files if a.get(p) != b.get(p))
        from kwce.mii_contest_wordmark_v32 import TEXTURES
        self.assertEqual(changed, sorted(TEXTURES.values()))


if __name__ == '__main__':
    unittest.main()

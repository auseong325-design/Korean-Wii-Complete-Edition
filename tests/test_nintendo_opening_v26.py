"""Nintendo build-v26: only the two opening animations in content 5 change, and the five Korean
letters (front + reflection) settle by loop frame 51 with an even 3-frame stagger."""
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V25 = ROOT / 'workspace/channels/nintendo/build-v25/nintendo-ko-ui-test.wad'
V26 = ROOT / 'workspace/channels/nintendo/build-v26/nintendo-ko-ui-test.wad'


def contents(path):
    from kwce.channels import load_library
    t = load_library().title.Title(); t.load_wad(path.read_bytes())
    return [t.get_content_by_index(i) for i in range(len(t.tmd.content_records))]


class NintendoOpeningV26Tests(unittest.TestCase):
    def setUp(self):
        if not (V25.is_file() and V26.is_file()):
            self.skipTest('builds not present')

    def test_only_opening_animations_change(self):
        from kwce.channels import ChannelArchive
        old, new = contents(V25), contents(V26)
        self.assertEqual([i for i in range(len(old)) if old[i] != new[i]], [5])
        a, b = ChannelArchive(old[5]), ChannelArchive(new[5])
        self.assertEqual([p for p in a.files if a.get(p) != b.get(p)], ['layout/option.arc'])
        x, y = ChannelArchive(a.get('layout/option.arc')), ChannelArchive(b.get('layout/option.arc'))
        self.assertEqual(sorted(p for p in x.files if x.get(p) != y.get(p)),
                         ['arc/anim/opening_00_in.brlan', 'arc/anim/opening_00_loop.brlan'])

    def test_letters_settle_early_and_evenly(self):
        from kwce.channels import ChannelArchive
        from kwce.disk_dvd_anim import _contents
        from kwce.nintendo_menu_art_v9 import TITLE
        inner = ChannelArchive(ChannelArchive(contents(V26)[5]).get('layout/option.arc'))
        raw = inner.get('arc/anim/opening_00_loop.brlan')
        spans = {}
        for name, material, tags in _contents(raw):
            if not material and name in {p for t in TITLE for p in (t[1], t[2])}:
                f = [struct.unpack_from('>f', raw, k)[0] for _, _, tr in tags for _, _, _, ks in tr for k in ks]
                spans[name] = (min(f), max(f))
        starts = [spans[t[1]][0] for t in TITLE]
        self.assertEqual([s - starts[0] for s in starts], [0, 3, 6, 12, 15])
        self.assertLessEqual(max(e for _, e in spans.values()) - starts[0], 51)
        for t in TITLE:
            self.assertEqual(spans[t[1]], spans[t[2]])      # reflection moves with its letter


if __name__ == '__main__':
    unittest.main()

"""Wii Room v70: only the settings region icon (Area_Btn / Area_Btn_B) changes."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V69 = ROOT / 'workspace/channels/wiiroom/build-v69/wiiroom-ko-local-test.wad'
V70 = ROOT / 'workspace/channels/wiiroom/build-v70/wiiroom-ko-local-test.wad'


@unittest.skipUnless(V69.is_file() and V70.is_file(), 'Wii Room v69/v70 builds not present')
class RegionIconTests(unittest.TestCase):
    def test_only_region_icon_textures_change(self):
        from kwce.channels import load_library, ChannelArchive
        from kwce.wiiroom_formats import decompress_lz11
        from kwce.channel_texture import texture_records
        from kwce.wiiroom_region_icon import LEXES, TEXTURE
        lib = load_library()
        a, b = (lib.title.Title() for _ in range(2)); a.load_wad(V69.read_bytes()); b.load_wad(V70.read_bytes())
        n = len(a.tmd.content_records)
        self.assertEqual([i for i in range(n) if a.get_content_by_index(i) != b.get_content_by_index(i)], [2])
        x, y = ChannelArchive(a.get_content_by_index(2)), ChannelArchive(b.get_content_by_index(2))
        self.assertEqual(set(x.files), set(y.files))
        self.assertEqual(sorted(p for p in x.files if x.get(p) != y.get(p)), sorted(LEXES))
        for lex in LEXES:
            p, q = ChannelArchive(decompress_lz11(x.get(lex))), ChannelArchive(decompress_lz11(y.get(lex)))
            changed = [f for f in p.files if p.get(f) != q.get(f)]
            self.assertEqual(len(changed), 1); self.assertTrue(changed[0].endswith(TEXTURE))
            r = texture_records(q.get(changed[0]))[0]
            self.assertEqual((r['width'], r['height'], r['format']), (25, 26, 2))


if __name__ == '__main__':
    unittest.main()

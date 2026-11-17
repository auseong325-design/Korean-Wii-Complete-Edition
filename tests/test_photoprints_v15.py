"""Photo Prints revision 15 / hardware-v11: name-card phone header back to the stock 電話番号.

The WiiLink print server (references/cam-server-ab059bc0/render.py) only replaces the exact
header '電話番号' with 'Phone Number:'. Tests use the project's ignored builds and skip when absent.
"""
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = ROOT / 'workspace/channels/photoprints'
STOCK = BASE / 'originals/digicam-japan-v1024.wad'
PAIRS = ((BASE / 'build-v14/photoprints-ko-local-test.wad', BASE / 'build-v15/photoprints-ko-local-test.wad'),
         (BASE / 'hardware-v10/photoprints-ko-hardware-test.wad', BASE / 'hardware-v11/photoprints-ko-hardware-test.wad'))
RENDER = BASE / 'references/cam-server-ab059bc0/render.py'
BRLYT = 'arc/blyt/Ref_print_template_name_cardC.brlyt'
HAVE = STOCK.exists() and all(p.exists() for pair in PAIRS for p in pair)


@unittest.skipUnless(HAVE, 'local data')
class PhoneHeader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kwce.channels import ChannelArchive, load_library
        cls.lib = load_library()
        from libWiiPy.archive import decompress_lz77
        cls.CA, cls.lz = ChannelArchive, staticmethod(decompress_lz77)

    def title(self, path):
        t = self.lib.title.Title()
        t.load_wad(path.read_bytes())
        return t

    def layout(self, title):
        return self.CA(self.lz(self.CA(title.get_content_by_index(2)).get('layout.arc.LZ')))

    def test_only_the_header_section_changes(self):
        from kwce.channels import layout_sections, textbox
        stock = layout_sections(self.layout(self.title(STOCK)).get(BRLYT))
        stock_head = next(s for s in stock if (textbox(s) or ('',))[0] == 'TelNumHead')
        for old_path, new_path in PAIRS:
            old, new = self.title(old_path), self.title(new_path)
            n = len(old.tmd.content_records)
            self.assertEqual([i for i in range(n) if old.get_content_by_index(i) != new.get_content_by_index(i)], [2])
            a, b = self.CA(old.get_content_by_index(2)), self.CA(new.get_content_by_index(2))
            self.assertEqual(set(a.files), set(b.files))
            self.assertEqual([f for f in a.files if a.get(f) != b.get(f)], ['layout.arc.LZ'])
            la, lb = self.layout(old), self.layout(new)
            self.assertEqual([f for f in la.files if la.get(f) != lb.get(f)], [BRLYT])
            sa, sb = layout_sections(la.get(BRLYT)), layout_sections(lb.get(BRLYT))
            changed = [i for i, (x, y) in enumerate(zip(sa, sb)) if x != y]
            self.assertEqual(len(sa), len(sb))
            self.assertEqual([textbox(sb[i])[0] for i in changed], ['TelNumHead'])
            self.assertEqual(sb[changed[0]], stock_head)
            self.assertEqual(textbox(sb[changed[0]])[1], '電話番号')
            wii = next(s for s in sb if (textbox(s) or ('',))[0] == 'WiiAdrHead')
            self.assertEqual(' '.join(textbox(wii)[1].split()), 'W i i 番 号')

    def test_server_rule_and_font(self):
        from kwce.photoprints_font import find_glyph
        source = RENDER.read_text(encoding='utf-8')
        self.assertIn('text == "電話番号"', source)
        self.assertIn('"Phone Number:"', source)
        font = self.CA(self.title(PAIRS[1][1]).get_content_by_index(2)).get('font_rodan_28.brfna')
        for ch in '電話番号':
            self.assertIsNotNone(find_glyph(font, ord(ch)), ch)

    def test_hardware_identity(self):
        old, new = self.title(PAIRS[1][0]), self.title(PAIRS[1][1])
        self.assertTrue(new.get_is_fakesigned())
        self.assertEqual((new.tmd.title_id, new.tmd.ios_tid, new.tmd.region), (old.tmd.title_id, old.tmd.ios_tid, old.tmd.region))
        self.assertEqual(hashlib.sha256(new.get_content_by_index(1)).digest(), hashlib.sha256(old.get_content_by_index(1)).digest())


if __name__ == '__main__':
    unittest.main()

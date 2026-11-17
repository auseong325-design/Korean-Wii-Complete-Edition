"""2026-11-16 menu-title choices: Mii Contest v34, Nintendo v21, Internet hardware-v12 (content 0 only)."""
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = {'mii-contest': ('build-v33', 'build-v34', 'mii-contest-ko-ui-test.wad'),
         'nintendo': ('build-v20', 'build-v21', 'nintendo-ko-ui-test.wad'),
         'internet': ('hardware-v8', 'hardware-v12', 'internet-ko-hardware-candidate.wad')}


def contents(path):
    from kwce.channels import load_library
    t = load_library().title.Title(); t.load_wad(path.read_bytes())
    return [t.get_content_by_index(i) for i in range(len(t.tmd.content_records))]


def member(content0, name):
    from kwce.channels import ChannelArchive
    from libWiiPy.archive import decompress_lz77
    return ChannelArchive(decompress_lz77(ChannelArchive(content0[0x640:]).get(name)[32:]))


class MenuWordmark1116Tests(unittest.TestCase):
    def pair(self, channel):
        parent, child, name = PAIRS[channel]
        a, b = (ROOT / f'workspace/channels/{channel}/{d}/{name}' for d in (parent, child))
        if not (a.is_file() and b.is_file()): self.skipTest('builds not present')
        old, new = contents(a), contents(b)
        self.assertEqual([i for i in range(len(old)) if old[i] != new[i]], [0])
        return old[0], new[0]

    def changed_members(self, old, new):
        from kwce.channels import ChannelArchive
        a, b = ChannelArchive(old[0x640:]), ChannelArchive(new[0x640:])
        self.assertEqual(set(a.files), set(b.files))
        self.assertEqual(old[:0x40], new[:0x40])
        return sorted(p for p in a.files if a.get(p) != b.get(p))

    def test_mii_contest(self):
        from kwce import tpl
        old, new = self.pair('mii-contest')
        self.assertEqual(self.changed_members(old, new), ['meta/banner.bin', 'meta/icon.bin'])
        before, after = member(old, 'meta/icon.bin'), member(new, 'meta/icon.bin')
        self.assertEqual([p for p in before.files if before.get(p) != after.get(p)], ['arc/timg/stMcLogoUsEn.tpl'])
        image = tpl.decode(after.get('arc/timg/stMcLogoUsEn.tpl'), 0)
        self.assertEqual(image.size, (112, 65))
        # teal 'Mii' on top, white block letters below
        r, g, b, a = image.convert('RGBA').getpixel((56, 8))
        self.assertTrue(a > 0 and g > r)
        banner = member(new, 'meta/banner.bin')
        self.assertTrue(any(p.endswith('st_alf_capC_00.tpl') for p in banner.files))

    def test_nintendo(self):
        from kwce import tpl
        old, new = self.pair('nintendo')
        self.assertEqual(self.changed_members(old, new), ['meta/banner.bin', 'meta/icon.bin'])
        image = tpl.decode(member(new, 'meta/icon.bin').get('arc/timg/oh_proLogo_E_00.tpl'), 0).convert('L')
        self.assertEqual(image.size, (120, 32))
        rows = [[image.getpixel((x, y)) for x in range(120)] for y in range(32)]
        ink = [y for y in range(32) if max(rows[y]) > 16]
        self.assertEqual((min(ink), max(ink)), (1, 30))
        for y in range(1, 15):          # unfaded mirror about the US axis (rows 15/16)
            self.assertEqual(rows[y], rows[31 - y])
        cols = [x for x in range(120) if any(rows[y][x] > 16 for y in range(15))]
        self.assertGreaterEqual(cols[-1] - cols[0], 100)

    def test_internet(self):
        from kwce.channel_font import font_data
        from kwce.channels import layout_sections
        from kwce import internet_title_font as f
        old, new = self.pair('internet')
        self.assertEqual(self.changed_members(old, new), ['meta/banner.bin', 'meta/icon.bin'])
        for kind in ('banner', 'icon'):
            a, b = member(old, f'meta/{kind}.bin'), member(new, f'meta/{kind}.bin')
            # the Wii Menu resolves arc/... from the U8 root: no '.' directory may appear (hardware-v9 bug)
            self.assertEqual(f.u8_has_dot_root(b.data), f.u8_has_dot_root(a.data))
            self.assertFalse(f.u8_has_dot_root(b.data))
            changed = sorted(p for p in a.files if a.get(p) != b.get(p))
            sa, sb = (layout_sections(x.get(f'arc/blyt/{kind}.brlyt')) for x in (a, b))
            if kind == 'icon':
                # no font and no new panes in the icon (Wii Menu memory, hardware-v10/v11 bugs): four title
                # boxes of other languages become offset copies of the KOR box
                self.assertEqual(changed, ['arc/anim/icon.brlan', 'arc/blyt/icon.brlyt'])
                self.assertEqual(set(b.files), set(a.files))
                self.assertLessEqual(len(b.data), len(a.data))
                self.assertEqual([x[:4] for x in sa], [y[:4] for y in sb])
                name = lambda s: s[0xc:0x1c].split(b'\0')[0].decode()
                eng = next(s for s in sb if s[:4] == b'txt1' and name(s) == f.ICON_BOX)
                old_eng = next(s for s in sa if s[:4] == b'txt1' and name(s) == f.ICON_BOX)
                for i in (0x64, 0x68):
                    self.assertAlmostEqual(struct.unpack_from('>f', eng, i)[0], struct.unpack_from('>f', old_eng, i)[0] * f.SIZE, places=2)
                donors = {d: (dx, dy) for d, dx, dy in f.ICON_DONORS}
                for x, y in zip(sa, sb):
                    if y[:4] == b'txt1' and name(y) in donors:
                        dx, dy = donors[name(y)]
                        self.assertEqual(y[0x24:0x2c], struct.pack('>ff', struct.unpack_from('>f', eng, 0x24)[0] + dx, struct.unpack_from('>f', eng, 0x28)[0] + dy))
                        self.assertEqual(y[0x50:0x52], eng[0x50:0x52])            # KOR material
                        self.assertEqual(y[0x52:0x74], eng[0x52:0x74][:0x6] + y[0x58:0x5c] + eng[0x5c:0x74])
                        self.assertEqual(y[0x74:0x74 + 14].decode('utf-16-be'), '인터넷\n채널\0')
                    elif y[:4] == b'grp1' and y[8:11] == b'KOR':
                        self.assertEqual(struct.unpack_from('>H', y, 0x18)[0], 1 + len(donors))
                    elif y[:4] == b'grp1' and y[8:11].decode() in ('GER', 'FRA', 'SPA', 'ITA'):
                        self.assertEqual(struct.unpack_from('>H', y, 0x18)[0], 0)
                    elif not (y[:4] == b'txt1' and name(y) == f.ICON_BOX):
                        self.assertEqual(x, y)
                continue
            self.assertEqual(changed, [f'arc/blyt/{kind}.brlyt'])
            self.assertEqual(set(b.files), set(a.files) | {f.FONT_PATH})
            _, mapping, _ = font_data(b.get(f.FONT_PATH))
            self.assertEqual({chr(c) for c in mapping}, set(f.TEXT))
            fnl = next(s for s in sb if s[:4] == b'fnl1')
            self.assertEqual(struct.unpack_from('>H', fnl, 8)[0], 2)
            self.assertIn(f.FONT_NAME.encode(), fnl)
            self.assertEqual(len(sa), len(sb))
            for x, y in zip(sa, sb):
                if y[:4] != b'txt1':
                    if y[:4] != b'fnl1': self.assertEqual(x, y)
                    continue
                name = y[0xc:0x1c].split(b'\0')[0].decode()
                if name not in f.BOXES['banner']:
                    self.assertEqual(x, y); continue
                self.assertEqual(struct.unpack_from('>H', y, 0x52)[0], 1)
                for i in (0x64, 0x68):
                    self.assertAlmostEqual(struct.unpack_from('>f', y, i)[0], struct.unpack_from('>f', x, i)[0] * f.SIZE, places=2)
                self.assertEqual(x[:0x52] + x[0x54:0x64] + x[0x6c:], y[:0x52] + y[0x54:0x64] + y[0x6c:])

if __name__ == '__main__':
    unittest.main()

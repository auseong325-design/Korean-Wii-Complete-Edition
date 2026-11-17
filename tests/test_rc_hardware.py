import re
import unittest
from pathlib import Path

from kwce import rc_hardware
from kwce.priiloader_hacks import DVD_GROUP, GC_LAYOUT_GROUP
from kwce.priiloader_legacy import parse, apply as legacy_apply
from kwce.gc_native import patch_gc_native
from kwce.gc_disc_layout import patch_gc_only_layout
from kwce.dvd_disc_banner_hook_v12 import patch_dvd_banner_hook

ROOT = Path(__file__).resolve().parents[1]
MENU = ROOT / 'workspace/console-baseline/menu-original-43K.dol'


class TestRcHardware(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.menu = MENU.read_bytes()

    def test_config_channels_unique(self):
        chans = rc_hardware.config()['channels']
        ids = [c['id'] for c in chans]
        self.assertEqual(len(ids), len(set(ids)))
        for c in chans:
            self.assertEqual(len(c['tid']), 16)
            self.assertIn(c['source'], ('korean_original', 'hardware', 'dvd'))
        # Version must match the installer's VERSION define (kept in lockstep across RC bumps).
        src = (ROOT / 'homebrew/kwce-installer-rc/source/main.c').read_text(encoding='utf-8')
        m = re.search(r'#define VERSION "([^"]+)"', src)
        self.assertEqual(rc_hardware.config()['version'], m.group(1))

    def test_forbidden_symbols(self):
        rc_hardware.forbidden_symbols('0001 T ES_AddTitleStart\n0002 T main\n0003 T read_console_model')
        for bad in ('menu_install', 'ISFS_Write', 'ISFS_Delete', 'ISFS_CreateFile'):
            with self.assertRaises(ValueError):
                rc_hardware.forbidden_symbols(f'0001 T {bad}\n0002 T main')

    def test_gc_only_ini_is_two_disc_no_dvd(self):
        raw, rec = rc_hardware.disc_ini(self.menu, dvd=False)
        self.assertEqual(rec['mode'], 'gc-only')
        self.assertTrue(rec['gc_only_layout'])
        self.assertFalse(rec['dvd_hook'])
        self.assertNotIn(DVD_GROUP, rec['sections'])
        # Through the old parser, the GC-only profile reproduces GC-native + two-disc layout.
        expected = patch_gc_only_layout(patch_gc_native(self.menu, japanese_cards=True, japanese_comments=True)[0],
                                        require_original=False)[0]
        self.assertEqual(legacy_apply(self.menu, parse(raw)), expected)

    def test_gc_dvd_ini_keeps_dvd_hook(self):
        raw, rec = rc_hardware.disc_ini(self.menu, dvd=True)
        self.assertEqual(rec['mode'], 'gc-dvd')
        self.assertFalse(rec['gc_only_layout'])
        self.assertTrue(rec['dvd_hook'])
        self.assertIn(DVD_GROUP, rec['sections'])
        self.assertNotIn(GC_LAYOUT_GROUP, rec['sections'])
        # The GC+DVD profile reproduces GC-native + the DVD banner hook (three-disc _R layout kept).
        expected = patch_dvd_banner_hook(patch_gc_native(self.menu, japanese_cards=True, japanese_comments=True)[0])[0]
        self.assertEqual(legacy_apply(self.menu, parse(raw)), expected)

    def test_allowed_paths(self):
        self.assertTrue(rc_hardware.allowed('apps/kwce-installer-rc/boot.dol'))
        self.assertTrue(rc_hardware.allowed('kwce-rc/food/korean.wad'))
        self.assertTrue(rc_hardware.allowed('kwce-rc/priiloader/gc-only.ini'))
        self.assertTrue(rc_hardware.allowed('kwce-rc/priiloader/fragment-gc-only.ini'))
        self.assertTrue(rc_hardware.allowed('kwce-rc/priiloader/fragment-gc-dvd.ini'))
        self.assertTrue(rc_hardware.allowed('kwce-rc/versions.txt'))
        for name in ('boot.dol', 'meta.xml', 'icon.png', 'LICENSE', 'SOURCE.txt', 'source.zip'):
            self.assertTrue(rc_hardware.allowed(f'kwce-rc/extras/wiilink-mail-patcher/{name}'))
        self.assertFalse(rc_hardware.allowed('kwce-rc/extras/wiilink-mail-patcher/other.bin'))
        self.assertFalse(rc_hardware.allowed('kwce-rc/extras/evil/boot.dol'))
        self.assertFalse(rc_hardware.allowed('kwce-rc/../escape.wad'))
        self.assertFalse(rc_hardware.allowed('apps/kwce-installer-rc/menu_res.c'))
        self.assertFalse(rc_hardware.allowed('apps/Priiloader/hacks_hash.ini'))

    # ---- RC3: complete disc profiles that keep the card's other hacks ----

    STANDARD = ('[Block Disc Updates]\r\nmaxversion=518\r\nminversion=518\r\namount=1\r\n'
                'hash=0x7c0802a6,0x9421ffe0\r\npatch=0x4e800020\r\n'
                '[Remove Deflicker]\r\nmaxversion=518\r\nminversion=518\r\namount=1\r\n'
                'hash=0x38000001,0x98030000\r\npatch=0x38000000\r\n').encode('ascii')

    def test_merge_keeps_other_hacks_and_switches_modes(self):
        gc_only, _ = rc_hardware.disc_ini(self.menu, dvd=False)
        gc_dvd, _ = rc_hardware.disc_ini(self.menu, dvd=True)
        card = rc_hardware.merge_disc_profile(self.STANDARD, gc_dvd)       # what an earlier deploy left
        self.assertTrue(card.startswith(self.STANDARD))
        only = rc_hardware.merge_disc_profile(card, gc_only)
        names = [n.decode() for n in re.findall(rb'^\[([^\]\r\n]+)\]', only, re.M)]
        self.assertEqual(names[:2], ['Block Disc Updates', 'Remove Deflicker'])
        self.assertIn(GC_LAYOUT_GROUP, names)
        self.assertNotIn(DVD_GROUP, names)
        self.assertEqual(rc_hardware.merge_disc_profile(only, gc_only), only)    # idempotent
        self.assertEqual(rc_hardware.merge_disc_profile(only, gc_dvd), card)     # switching back is exact
        self.assertNotIn(b'\n', only.replace(b'\r\n', b''))                     # CRLF only (old parser)
        parse(only)
        # The GC-only fragment through the old parser == GC-native + the original two-disc layout.
        expected = patch_gc_only_layout(patch_gc_native(self.menu, japanese_cards=True, japanese_comments=True)[0],
                                        require_original=False)[0]
        self.assertEqual(legacy_apply(self.menu, parse(gc_only)), expected)

    def test_merge_refuses_foreign_fragment_and_unparsable_card(self):
        with self.assertRaises(ValueError):
            rc_hardware.merge_disc_profile(self.STANDARD, self.STANDARD)
        gc_only, _ = rc_hardware.disc_ini(self.menu, dvd=False)
        newer = b'[New Style Hack]\r\nversion=518\r\nmaster=1\r\n'
        with self.assertRaises(ValueError):
            rc_hardware.merge_disc_profile(self.STANDARD + newer, gc_only)
        self.assertTrue(rc_hardware.merge_disc_profile(b'', gc_only).startswith(b'[KWCE GC:'))

    def test_restore_region_changes_only_the_region(self):
        from kwce.channels import load_library
        lib = load_library()
        wad = (ROOT / 'workspace/channels/personal-data/originals').glob('*.wad')
        src = sorted(wad)[0].read_bytes()
        before = lib.title.Title()
        before.load_wad(src)
        out, rec = rc_hardware.restore_region(src, 4)
        after = lib.title.Title()
        after.load_wad(out)
        self.assertEqual((rec['source_region'], rec['target_region']), (before.tmd.region, 4))
        self.assertEqual(after.tmd.region, 4)
        self.assertTrue(after.get_is_fakesigned())
        self.assertEqual(after.tmd.title_id, before.tmd.title_id)
        self.assertEqual(after.tmd.ios_tid, before.tmd.ios_tid)
        for i in range(len(before.tmd.content_records)):
            self.assertEqual(after.get_content_by_index(i), before.get_content_by_index(i))
        same, rec2 = rc_hardware.restore_region(out, 4)                     # already launchable
        self.assertEqual(same, out)
        self.assertFalse(rec2['changed'])
        self.assertEqual(rc_hardware.restore_region(src, None)[0], src)     # RC1/RC2 behaviour

    def test_rc3_config_flags(self):
        cfg = rc_hardware.config()
        self.assertEqual(cfg.get('restore_region'), 4)
        self.assertTrue(cfg.get('priiloader_merge'))
        tv = [c for c in cfg['channels'] if c['id'] == 'tvguide']
        self.assertEqual(len(tv), 1)
        self.assertTrue(tv[0]['experimental'])

    # ---- RC4: build identity + version list (must match homebrew/.../versions.c) ----

    RC3 = ROOT / 'workspace/hardware/kwce-rc-sd-v3'

    @staticmethod
    def _tmd(count=2, region=4):
        t = bytearray(0x1E4 + 36 * count)
        t[0x184:0x18C] = (0x0000000100000038).to_bytes(8, 'big')     # IOS56
        t[0x18C:0x194] = bytes.fromhex('000100014843464b')
        t[0x19C:0x19E] = region.to_bytes(2, 'big')
        t[0x1DC:0x1DE] = (512).to_bytes(2, 'big')
        t[0x1DE:0x1E0] = count.to_bytes(2, 'big')
        for i in range(count):
            r = 0x1E4 + 36 * i
            t[r:r + 4] = i.to_bytes(4, 'big')
            t[r + 4:r + 6] = i.to_bytes(2, 'big')
            t[r + 6:r + 8] = (1).to_bytes(2, 'big')
            t[r + 8:r + 16] = (0x40 * (i + 1)).to_bytes(8, 'big')
            t[r + 16:r + 36] = bytes([i + 1]) * 20
        return t

    def test_fnv_vectors_and_identity_invariants(self):
        self.assertEqual(rc_hardware.fnv1a64(b''), 0xcbf29ce484222325)
        self.assertEqual(rc_hardware.fnv1a64(b'a'), 0xaf63dc4c8601ec8c)
        base = self._tmd()
        fp, tid, ver, region = rc_hardware.tmd_identity(base)
        self.assertEqual((tid, ver, region), ('000100014843464b', 512, 4))
        resigned = bytearray(base)
        resigned[4:0x104] = b'\x5a' * 0x100          # signature
        resigned[0x1E2:0x1E4] = b'\x12\x34'          # fakesign brute-force field
        self.assertEqual(rc_hardware.tmd_identity(resigned)[0], fp)
        for offset in (0x19D, 0x1DD, 0x1E4 + 16, 0x1E4 + 36 + 35, 0x18F, 0x1D8):
            changed = bytearray(base)
            changed[offset] ^= 1
            self.assertNotEqual(rc_hardware.tmd_identity(changed)[0], fp, hex(offset))
        with self.assertRaises(ValueError):
            rc_hardware.tmd_identity(base[:-1])

    def test_identity_matches_libwiipy_on_package_wads(self):
        from kwce.channels import load_library
        lib = load_library()
        for name in ('wiispeak/korean.wad', 'wiispeak/original.wad', 'personal-data/korean.wad'):
            path = self.RC3 / 'kwce-rc' / name
            title = lib.title.Title()
            title.load_wad(path.read_bytes())
            fp, tid, ver, region = rc_hardware.tmd_identity(rc_hardware.read_wad_tmd(path))
            self.assertEqual(tid, title.tmd.title_id.lower(), name)
            self.assertEqual(ver, title.tmd.title_version, name)
            self.assertEqual(region, title.tmd.region, name)
            self.assertEqual(rc_hardware.tmd_identity(title.tmd.dump())[0], fp, name)

    def test_version_list_format_and_marks(self):
        channels = [dict(id='wiispeak', tid='000100014843464b')]
        sources = ['workspace/hardware/kwce-rc-sd-v3/kwce-rc/wiispeak/korean.wad',
                   'workspace/hardware/kwce-rc-sd-v3/kwce-rc/wiispeak/original.wad',
                   'workspace/channels/wiispeak/originals/wiispeak-korea-v512.wad',
                   'workspace/channels/wiispeak/originals/wiispeak-usa-v512.wad']
        raw, rec = rc_hardware.version_list(ROOT, channels, 4, '1.0-rc4', sources)
        lines = raw.decode('ascii').splitlines()
        self.assertEqual(lines[0], 'kwce-versions|1|4|1.0-rc4')
        builds = [l.split('|') for l in lines if l.startswith('build|')]
        marks = [l.split('|') for l in lines if l.startswith('mark|')]
        for b in builds:
            self.assertEqual(len(b), 6)
            self.assertRegex(b[2], r'^[0-9a-f]{16}$')
        korean_fp = rc_hardware.tmd_identity(rc_hardware.read_wad_tmd(ROOT / sources[0]))[0]
        k = [b for b in builds if b[3] == 'K']
        self.assertEqual([(b[2], b[4], b[5]) for b in k], [(f'{korean_fp:016x}', '3', 'RC3')])
        self.assertTrue(all(b[5] == 'original' for b in builds if b[3] == 'O'))
        # RC3 original.wad == the Korean v512 original (one identity); the USA Wii Speak is
        # another title (HCFE), so the version list must not list it under this channel.
        self.assertEqual(len([b for b in builds if b[3] == 'O']), 1)
        usa = rc_hardware.tmd_identity(rc_hardware.read_wad_tmd(ROOT / sources[3]))
        self.assertNotEqual(usa[1], '000100014843464b')
        self.assertNotIn(f'{usa[0]:016x}', raw.decode('ascii'))
        self.assertTrue(marks)
        original_prefixes = {r[16:24].hex() for s in sources[1:]
                             for r in rc_hardware.tmd_records(rc_hardware.read_wad_tmd(ROOT / s))}
        self.assertFalse({m[2] for m in marks} & original_prefixes)
        self.assertEqual((rec['builds'], rec['marks']), (len(builds), len(marks)))

    def test_version_sources_only_older_packages(self):
        channels = [dict(id='wiispeak', tid='000100014843464b')]
        src = rc_hardware.version_sources(ROOT, channels, 'kwce-rc-sd-v2')
        self.assertTrue(any(s.startswith('workspace/hardware/kwce-rc-sd-v1/') for s in src))
        self.assertFalse(any(s.startswith(('workspace/hardware/kwce-rc-sd-v2/', 'workspace/hardware/kwce-rc-sd-v3/'))
                             for s in src))
        self.assertTrue(any(s.startswith('workspace/channels/wiispeak/originals/') for s in src))
        self.assertEqual(src, sorted(src))

    def test_rc4_config_has_version_list(self):
        cfg = rc_hardware.config()
        self.assertTrue(cfg.get('versions'))
        self.assertGreaterEqual(rc_hardware.release_of(cfg['version']), 4)
        self.assertEqual(rc_hardware.release_of('1.0-rc12'), 12)
        self.assertEqual(rc_hardware.release_of('0.2-alpha'), 0)
        # The final personal release follows RC31 (FINAL_1_0 in the installer source).
        self.assertEqual(rc_hardware.release_of('1.0'), 32)
        self.assertEqual((rc_hardware.release_name('1.0'), rc_hardware.release_name('1.0-rc31')), ('1.0', 'RC31'))
        main = (rc_hardware.ROOT / 'homebrew/kwce-installer-rc/source/main.c').read_text()
        self.assertIn('#define FINAL_1_0 32', main)
        self.assertEqual((rc_hardware.release_of('1.0.1'), rc_hardware.release_name('1.0.1')), (33, '1.0.1'))
        self.assertEqual((rc_hardware.release_of('1.0.2'), rc_hardware.release_name('1.0.2')), (34, '1.0.2'))
        self.assertIn('"1.0.2") == 0) return FINAL_1_0 + 2', main)
        self.assertEqual((rc_hardware.release_of('1.0.3'), rc_hardware.release_name('1.0.3')), (35, '1.0.3'))
        self.assertEqual((rc_hardware.release_of('1.0.4'), rc_hardware.release_name('1.0.4')), (36, '1.0.4'))
        self.assertEqual((rc_hardware.release_of('1.0.5'), rc_hardware.release_name('1.0.5')), (37, '1.0.5'))
        self.assertIn('"1.0.5") == 0) return FINAL_1_0 + 5', main)
        self.assertEqual((rc_hardware.release_of('1.0.6'), rc_hardware.release_name('1.0.6')), (38, '1.0.6'))
        self.assertEqual((rc_hardware.release_of('1.0.7'), rc_hardware.release_name('1.0.7')), (39, '1.0.7'))
        self.assertEqual((rc_hardware.release_of('1.0.8'), rc_hardware.release_name('1.0.8')), (40, '1.0.8'))
        self.assertEqual((rc_hardware.release_of('1.0.9'), rc_hardware.release_name('1.0.9')), (41, '1.0.9'))


if __name__ == '__main__':
    unittest.main()

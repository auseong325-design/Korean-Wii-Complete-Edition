"""Forwarder delivery: small resident loader, pinned player on SD."""
import json
import struct
import tempfile
import unittest
from pathlib import Path

from kwce.dvd_forwarder_sd import (ROOT, TARGETS, HOOK, PREVIOUS_HOOK, PLAYER, EXTRA, PREVIOUS_PACKAGE,
                                   VERSIONS, frozen_inputs, previous_runtime, qualified, sha)
from kwce.dvd_integrated_sd import REQUIRED
from kwce.dvd_native_relocate import validate_payload, validate_ash_mapping
from kwce.dvd_native_loader import inspect_dol
from kwce.dvd_player_trace_sd import upgrade
from kwce.formats import ash_decompress
from kwce.priiloader_legacy import parse
from kwce.priiloader_hacks import DVD_GROUP


class ForwarderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module, cls.player = frozen_inputs()
        cls.forwarder = ash_decompress(cls.module)
        cls.hook = json.loads((ROOT/f'workspace/experiments/dvd-native-hook-v{HOOK}/manifest.json').read_text())

    def test_resident_bundle_is_small_and_menu_source_is_the_hardware_proven_one(self):
        old = json.loads((ROOT/'workspace/experiments/dvd-native-hook-v72/manifest.json').read_text())  # last resident-player build
        self.assertEqual(self.hook['source_revision'], 37)
        self.assertEqual(self.hook['sources'], old['sources'])  # identical menu-side C
        self.assertEqual(self.hook['sites'], old['sites'])
        self.assertLess(self.hook['bundle_size'], 512*1024)
        self.assertGreater(old['bundle_size'], 7*1024*1024)

    def test_forwarder_layout_fits_the_reviewed_menu_relocator(self):
        validate_payload(self.forwarder); validate_ash_mapping(self.forwarder)
        entry, regions = inspect_dol(self.forwarder)
        self.assertEqual(entry, 0x80003f00)
        self.assertLess(max(r.start+r.size for r in regions), 0x80100000)

    def test_forwarder_pins_exact_player_and_stays_in_scope(self):
        import hashlib
        digest = hashlib.sha1(self.player).digest()
        self.assertEqual(self.forwarder.count(digest), 1)
        source = (ROOT/'homebrew/kwce-dvd-forwarder/r1/source/main.c').read_text()
        for needle in ('memcmp(digest, PLAYER_SHA1, 20)', 'SYS_ResetSystem(SYS_RETURNTOMENU',
                       'sd:/kwce/dvd/player.dol'):
            self.assertIn(needle, source)
        for forbidden in ('IOS_ReloadIOS', 'ISFS_', 'DI_', 'net_', 'WPAD_', 'VIDEO_'):
            self.assertNotIn(forbidden, source)
        # The image is placed in MEM2 so MEM1 is free for the player's sections.
        self.assertIn('SYS_GetArena2Lo()', source)
        _, regions = inspect_dol(self.player)
        self.assertTrue(all(0x80003400 <= r.start and r.start+r.size <= 0x81800000 for r in regions))

    def test_embedded_relocator_copies_player_sections_and_clears_bss(self):
        """Run the exact stub bytes the forwarder embeds against the real player."""
        from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN
        from unicorn.ppc_const import UC_PPC_REG_3, UC_PPC_REG_PC
        from kwce.dvd_native_relocate import compile_relocator
        from kwce.ppc_patch import sections
        stub = compile_relocator(ash=False)
        self.assertEqual(self.forwarder.count(stub), 1)
        u = Uc(UC_ARCH_PPC, UC_MODE_32 | UC_MODE_BIG_ENDIAN)
        u.mem_map(0x80000000, 0x1800000); u.mem_map(0x90000000, 0x1000000)
        image, at = 0x90002000, 0x90002000+((len(self.player)+31) & ~31)
        u.mem_write(0x80000000, b'\xa5'*0x1800000)
        u.mem_write(image, self.player); u.mem_write(at, stub)
        entry, regions = inspect_dol(self.player)
        u.reg_write(UC_PPC_REG_3, image)
        u.emu_start(at, entry, count=400_000_000)
        self.assertEqual(u.reg_read(UC_PPC_REG_PC), entry)  # reached the player's entry
        self.assertEqual(u.reg_read(UC_PPC_REG_3), 0)       # same r3=0 contract as the menu handoff
        for _, offset, address, size in sections(self.player):
            self.assertEqual(bytes(u.mem_read(address, size)), self.player[offset:offset+size])
        bss, n = struct.unpack_from('>II', self.player, 0xd8)
        covered = [(a, a+s) for _, _, a, s in sections(self.player)]
        probe = next(x for x in range(bss, bss+n, 4096) if not any(lo <= x < hi for lo, hi in covered))
        self.assertEqual(bytes(u.mem_read(probe, 64)), bytes(64))

    def test_definition_upgrade_preserves_every_other_hack(self):
        for rel in TARGETS:
            raw = (ROOT/'workspace/hardware'/PREVIOUS_PACKAGE/rel).read_bytes()
            before, after = parse(raw), parse(upgrade(raw, PREVIOUS_HOOK, HOOK))
            self.assertEqual([x['name'] for x in before], [x['name'] for x in after])
            self.assertEqual([x for x in before if x['name'] != DVD_GROUP],
                             [x for x in after if x['name'] != DVD_GROUP])
        with self.assertRaises(ValueError): upgrade(raw, 72, HOOK)

    def test_incomplete_qualification_is_refused(self):
        folder = ROOT/f'workspace/experiments/dvd-native-hook-v{HOOK}'
        good = dict(revision=HOOK, source_revision=37, sha256=sha(folder/'menu.dol'),
                    card_encoding_sha256=sha(folder/'menu-with-card-encoding.dol'),
                    physical_dvd_verified=False, checks={k: True for k in REQUIRED | EXTRA},
                    evidence={f'workspace/experiments/dvd-native-hook-v{HOOK}/manifest.json': sha(folder/'manifest.json')})
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'q.json'; p.write_text(json.dumps(good)); qualified(p, HOOK)
            for key in REQUIRED:
                p.write_text(json.dumps({**good, 'checks': {**good['checks'], key: False}}))
                with self.assertRaises(ValueError): qualified(p, HOOK)
            p.write_text(json.dumps({**good, 'revision': 76}))
            with self.assertRaises(ValueError): qualified(p, HOOK)

    def test_restored_drive_cache_and_kept_disable_bit_clear(self):
        from kwce.dvd_player_fork import patches
        new, old = json.dumps(patches(61)), json.dumps(patches(58))
        self.assertIn('DI_UseCache(false)', old); self.assertNotIn('DI_UseCache(false)', new)
        self.assertIn('old & ~0x00200000u', new)
        self.assertNotIn('KwceProbeFirstReads', new)


    def test_every_delivery_keeps_its_frozen_pair_and_card_precondition(self):
        for version in VERSIONS:
            module, player = frozen_inputs(version)
            self.assertLess(len(module), 512*1024); self.assertGreater(len(player), 8*1024*1024)
        # v2 replaces the v1 loader and player, so the card must hold exactly those first.
        v1 = json.loads((ROOT/'workspace/hardware/kwce-dvd-forwarder-v1/package-manifest.json').read_text())
        runtime = previous_runtime(2)
        self.assertEqual(runtime['kwce/dvd/boot.ash'], v1['files']['kwce/dvd/boot.ash'])
        self.assertEqual(runtime['kwce/dvd/player.dol'], v1['files']['kwce/dvd/player.dol'])
        self.assertNotIn('kwce/dvd/player.dol', previous_runtime(1))


if __name__ == '__main__': unittest.main()

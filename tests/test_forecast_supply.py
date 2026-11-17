import json
import struct
import unittest
from pathlib import Path

from kwce.channels import load_library
from kwce.forecast_cache import public_source
from kwce.forecast_data import localize_forecast, forecast_mapping
from kwce import forecast_supply as fs

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / 'workspace/channels/forecast/originals/forecast-usa-wiilink-archive.wad'
BUILD_V105 = ROOT / 'workspace/channels/forecast/build-v105'


def _decompress(payload):
    load_library()
    from libWiiPy.archive import decompress_lz77
    return decompress_lz77(payload)


def _original_content1():
    lib = load_library()
    title = lib.title.Title()
    title.load_wad(ORIGINAL.read_bytes())
    return title.get_content_by_index(1)


def _parse_table(table):
    n = struct.unpack_from('>I', table, 0)[0]
    off = 4
    pairs = {}
    for _ in range(n):
        sl, dl = struct.unpack_from('>HH', table, off)
        off += 4
        src = table[off:off + sl]
        dst = table[off + sl:off + sl + dl]
        off += sl + dl
        pairs[src] = dst
    return n, off, pairs


class TableTest(unittest.TestCase):
    def test_table_format_round_trip_and_slot_limit(self):
        mapping = forecast_mapping()
        table, entries = fs.build_table(mapping)
        self.assertEqual(entries, len(mapping))
        n, consumed, pairs = _parse_table(table)
        self.assertEqual(n, len(mapping))
        self.assertEqual(consumed, len(table))                 # exact, no trailing bytes
        self.assertEqual(len(pairs), len(mapping))             # no collisions
        for english, korean in mapping.items():
            src = english.encode('utf-16-be')
            dst = korean.encode('utf-16-be')
            self.assertIn(src, pairs)
            self.assertEqual(pairs[src], dst)
            self.assertLessEqual(len(dst), len(src))           # every overlay fits its slot
            self.assertEqual(len(src) % 2, 0)

    def test_overlong_entry_is_refused(self):
        with self.assertRaises(ValueError):
            fs.build_table({'A': '한국'})                       # 2 bytes -> 4 bytes


class ReferenceEquivalenceTest(unittest.TestCase):
    """The compiled hook mirrors apply_supply_reference; pin that to localize_forecast."""

    def test_reference_matches_localize_forecast_on_real_payload(self):
        mapping = forecast_mapping()
        payload = public_source('forecast').read_bytes()[320:]
        localized = _decompress(localize_forecast(payload, mapping)[0])
        ref, modified = fs.apply_supply_reference(_decompress(payload), mapping)
        self.assertGreater(modified, 0)
        self.assertEqual(ref, localized)                       # byte-identical to the PC tool
        import zlib
        self.assertEqual(zlib.crc32(ref[12:]) & 0xffffffff, struct.unpack_from('>I', ref, 8)[0])

    def test_short_buffer_left_untouched(self):
        mapping = forecast_mapping()
        short = _decompress(public_source('short').read_bytes()[320:])
        out, modified = fs.apply_supply_reference(short, mapping)
        self.assertEqual(modified, 0)
        self.assertEqual(out, short)

    def test_idempotent(self):
        mapping = forecast_mapping()
        once, _ = fs.apply_supply_reference(_decompress(public_source('forecast').read_bytes()[320:]), mapping)
        twice, modified = fs.apply_supply_reference(once, mapping)
        self.assertEqual(modified, 0)
        self.assertEqual(twice, once)

    def test_shape_failsafe_leaves_buffer_untouched(self):
        mapping = forecast_mapping()
        good = _decompress(public_source('forecast').read_bytes()[320:])
        # Corrupt the country byte -> whole buffer must be left untouched.
        bad = bytearray(good)
        bad[20] ^= 1
        out, modified = fs.apply_supply_reference(bytes(bad), mapping)
        self.assertEqual(modified, 0)
        self.assertEqual(out, bytes(bad))
        # Corrupt a string pointer in the location table to out-of-bounds.
        bad2 = bytearray(good)
        count, offset = struct.unpack_from('>II', bad2, 80)
        struct.pack_into('>I', bad2, offset + 4, len(bad2) + 4)   # pointer past end
        out2, modified2 = fs.apply_supply_reference(bytes(bad2), mapping)
        self.assertEqual(modified2, 0)
        self.assertEqual(out2, bytes(bad2))


class PatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = _original_content1()
        cls.mapping = forecast_mapping()
        cls.blob, cls.blob_rec = fs.build_blob(fs.build_table(cls.mapping)[0])
        cls.patched, cls.rec = fs.patch_executable(cls.original, cls.mapping)

    def _word(self, buf, va):
        from kwce.ppc_patch import to_file
        at = to_file(buf, va, 4)
        return struct.unpack_from('>I', buf, at)[0]

    def test_hook_sites_rewritten_to_section(self):
        for va in fs.HOOK_SITES:
            delta = (fs.SECTION_VA - va) & 0x3fffffc
            self.assertEqual(self._word(self.patched, va), 0x48000000 | delta | 1)   # bl SECTION_VA

    def test_only_hook_words_and_new_section_change(self):
        # Within the original length, only the two hook words and the DOL header slot that
        # registers the appended section may change; the section itself is appended past the end.
        changed = [i for i in range(len(self.original)) if self.original[i] != self.patched[i]]
        from kwce.ppc_patch import to_file
        allowed = set()
        for va in fs.HOOK_SITES:
            base = to_file(self.original, va, 4)
            allowed.update(range(base, base + 4))
        slot = self.rec['dol_section_slot']
        for header_base in (0x00, 0x48, 0x90):                 # section offsets / addresses / sizes
            allowed.update(range(header_base + 4 * slot, header_base + 4 * slot + 4))
        arena_at = to_file(self.original, fs.ARENA_HI_SITE, 4)  # the one-word ArenaHi reservation
        allowed.update(range(arena_at, arena_at + 4))
        self.assertTrue(set(changed) <= allowed, set(changed) - allowed)
        # Both hook words must have actually changed (every byte except the shared 0x48 opcode top).
        for va in fs.HOOK_SITES:
            at = to_file(self.original, va, 4)
            self.assertNotEqual(self.original[at:at + 4], self.patched[at:at + 4])
        # ArenaHi setter rewritten to reserve the section.
        self.assertEqual(struct.unpack_from('>I', self.patched, arena_at)[0], fs.ARENA_HI_NEW)
        self.assertEqual(len(self.patched) - len(self.original), (len(self.blob) + 31) & ~31)

    def test_arena_reservation_is_consistent_and_clear_of_sda_stack(self):
        # SDA (r13=0x80337540) and SDA2 (r2=0x80339900) reach +/-32KiB; stack base 0x803437A8.
        self.assertGreater(fs.SECTION_VA, 0x80339900 + 0x8000)   # above the SDA2 window
        self.assertGreater(fs.SECTION_VA, 0x803437A8)            # above the stack base
        self.assertEqual(fs.SECTION_VA, fs.ARENA_HI_DEFAULT - fs.ARENA_RESERVE)
        self.assertEqual(self.rec['arena_reservation']['arena_hi_after'], hex(fs.SECTION_VA))
        self.assertLessEqual((len(self.blob) + 31) & ~31, fs.ARENA_RESERVE)
        self.assertLessEqual(fs.SECTION_VA + ((len(self.blob) + 31) & ~31), fs.ARENA_HI_DEFAULT)
        # new ArenaHi (0x816f9000) decoded from the patched addi must equal SECTION_VA.
        imm = fs.ARENA_HI_NEW & 0xffff
        imm = imm - 0x10000 if imm & 0x8000 else imm
        self.assertEqual(fs.ARENA_HI_DEFAULT + imm, fs.SECTION_VA)

    def test_new_section_carries_blob_and_table(self):
        from kwce.ppc_patch import sections
        mine = [(o, a, s) for i, o, a, s in sections(self.patched) if a == fs.SECTION_VA]
        self.assertEqual(len(mine), 1)
        o, a, s = mine[0]
        self.assertEqual(self.patched[o:o + len(self.blob)], self.blob)
        table_off = int(self.rec['fc_table'], 16) - fs.SECTION_VA
        table, _ = fs.build_table(self.mapping)
        self.assertEqual(self.blob[table_off:table_off + len(table)], table)

    def test_context_and_site_guards(self):
        for va in list(fs.CONTEXT)[:1] + list(fs.HOOK_SITES) + [fs.ARENA_HI_SITE]:
            bad = bytearray(self.original)
            from kwce.ppc_patch import to_file
            at = to_file(bad, va, 4)
            bad[at] ^= 0x01
            with self.assertRaises(ValueError):
                fs.patch_executable(bytes(bad), self.mapping)

    def test_reused_routines_and_record(self):
        self.assertEqual(self.rec['reused_routines'], {'verify': hex(fs.VERIFY), 'crc32': hex(fs.CRC32)})
        self.assertEqual(self.rec['fc_stub'], hex(fs.SECTION_VA))
        self.assertEqual(set(self.rec['hook_sites']), {hex(v) for v in fs.HOOK_SITES})


class RegenTest(unittest.TestCase):
    def test_blob_build_is_deterministic(self):
        table, _ = fs.build_table(forecast_mapping())
        a, reca = fs.build_blob(table)
        b, recb = fs.build_blob(table)
        self.assertEqual(a, b)
        self.assertEqual(reca['blob_sha256'], recb['blob_sha256'])

    def test_build_v105_blob_matches(self):
        if not (BUILD_V105 / 'build-manifest.json').exists():
            self.skipTest('build-v105 not present')
        manifest = json.loads((BUILD_V105 / 'build-manifest.json').read_text(encoding='utf-8'))
        _, rec = fs.build_blob(fs.build_table(forecast_mapping())[0])
        self.assertEqual(manifest['supply_conversion']['blob_sha256'], rec['blob_sha256'])
        self.assertEqual(manifest['TMD_region_after'], 4)
        self.assertEqual(manifest['supply_conversion']['arena_reservation']['arena_hi_after'], hex(fs.SECTION_VA))

    def test_build_v105_content1_has_hook_and_arena_patch(self):
        wad = BUILD_V105 / 'forecast-ko-personal-test.wad'
        if not wad.exists():
            self.skipTest('build-v105 not present')
        lib = load_library()
        title = lib.title.Title()
        title.load_wad(wad.read_bytes())
        dol = title.get_content_by_index(1)
        from kwce.ppc_patch import sections, to_file
        self.assertTrue(any(a == fs.SECTION_VA for _, _, a, _ in sections(dol)))
        for va in fs.HOOK_SITES:
            delta = (fs.SECTION_VA - va) & 0x3fffffc
            at = to_file(dol, va, 4)
            self.assertEqual(struct.unpack_from('>I', dol, at)[0], 0x48000000 | delta | 1)
        arena_at = to_file(dol, fs.ARENA_HI_SITE, 4)
        self.assertEqual(struct.unpack_from('>I', dol, arena_at)[0], fs.ARENA_HI_NEW)


if __name__ == '__main__':
    unittest.main()

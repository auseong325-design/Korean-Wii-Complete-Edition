"""Containment and actual PPC read-validation tests for the opt-in candidate."""
import hashlib
from pathlib import Path
import struct
import unittest

from kwce.gc_card_encoding import encoding_stub, patch_card_encodings
from kwce.gc_native import dol_offset, patch_gc_native

ROOT = Path(__file__).resolve().parents[1]
MENU = ROOT / 'workspace/console-baseline/menu-original-43K.dol'


class EncodingInputTests(unittest.TestCase):
    def test_unrelated_input_refused(self):
        with self.assertRaises(ValueError):
            patch_card_encodings(bytes(512))


@unittest.skipUnless(MENU.exists(), 'pinned local 43K original required')
class PerCardEncodingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = MENU.read_bytes()
        cls.base = patch_gc_native(cls.original, japanese_cards=True, japanese_comments=True)[0]

    def test_existing_cp932_adapter_and_other_bytes_preserved(self):
        result, record = patch_card_encodings(self.base)
        call = dol_offset(self.base, 0x81539718)
        cave = dol_offset(self.base, 0x81545a00)
        allowed = set(range(call, call+4)) | set(range(cave, cave+20))
        self.assertEqual(len(result), len(self.base))
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(self.base, result))))
        start = dol_offset(self.base, 0x815458d8)
        self.assertEqual(result[start:start+264], self.base[start:start+264])
        self.assertFalse(record['card_data_writes'])
        self.assertFalse(record['format_default_changed'])

    def test_changed_validator_or_occupied_cave_refused(self):
        for address in (0x815393e8, 0x81545a00, 0x81545864):
            changed = bytearray(self.base)
            changed[dol_offset(changed, address)] ^= 1
            with self.subTest(address=address), self.assertRaises(ValueError):
                patch_card_encodings(bytes(changed))

    def test_nonvolatile_header_register_and_card_bytes_preserved(self):
        from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN
        from unicorn.ppc_const import UC_PPC_REG_1, UC_PPC_REG_3, UC_PPC_REG_29, UC_PPC_REG_LR, UC_PPC_REG_PC
        u = Uc(UC_ARCH_PPC, UC_MODE_32 | UC_MODE_BIG_ENDIAN)
        u.mem_map(0x80000000, 0x1800000)
        u.mem_write(0x81545a00, encoding_stub())
        header, stack, end = 0x80010000, 0x80020000, 0x80003000
        for encoding in (0, 1, 2, 255, 65535):
            raw = bytearray(512)
            struct.pack_into('>H', raw, 0x24, encoding)
            u.mem_write(header, bytes(raw))
            u.reg_write(UC_PPC_REG_1, stack)
            u.reg_write(UC_PPC_REG_29, header)
            u.reg_write(UC_PPC_REG_LR, end)
            u.emu_start(0x81545a00, end, count=20)
            self.assertEqual(u.reg_read(UC_PPC_REG_PC), end)
            self.assertEqual(u.reg_read(UC_PPC_REG_3), encoding if encoding <= 1 else 1)
            self.assertEqual(u.reg_read(UC_PPC_REG_29), header)
            self.assertEqual(u.reg_read(UC_PPC_REG_1), stack)
            self.assertEqual(bytes(u.mem_read(header, 512)), raw)

    def test_actual_validator_both_slots_valid_invalid_and_checksum_cases(self):
        from gc_encoding_harness import run
        for font in (0, 1):
            for slot in (0, 1):
                for encoding in (0, 1, 2, 65535):
                    for corrupt in (False, True):
                        with self.subTest(font=font, slot=slot, encoding=encoding, corrupt=corrupt):
                            result = run(font, True, encoding, corrupt, candidate=True, slot=slot)
                            expected = -6 if corrupt else 0 if encoding in (0, 1) else -13
                            self.assertEqual(result['result'], expected)
                            self.assertTrue(result['card_unchanged'])

    def test_legacy_priiloader_stream_matches_patched_candidate(self):
        from kwce.priiloader_hacks import hacks, _runs, _unique_hash, _words
        from kwce.priiloader_legacy import checked_ini, parse, apply_streaming
        result, _ = patch_card_encodings(self.base)
        pairs = [(_unique_hash(self.original, a, (b-a)//4), _words(result, a, b))
                 for a, b in _runs(self.base, result)]
        entries = hacks(self.original) + [dict(name='KWCE GC: Per-card ANSI-SJIS validation (test)', pairs=pairs)]
        ini = checked_ini(self.original, entries, packed=True)
        self.assertEqual(apply_streaming(self.original, parse(ini)), result)


if __name__ == '__main__':
    unittest.main()

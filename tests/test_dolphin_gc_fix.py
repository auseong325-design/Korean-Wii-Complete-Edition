"""Guard the local emulator derivative; Nintendo assets are not test fixtures."""
import hashlib
import json
import unittest
from pathlib import Path

from kwce.dolphin_gc_fix import BASE_SHA256, patch_mios_ipc

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'tools/dolphin-2609a/Dolphin-x64/Dolphin.exe'


class RuntimeFixTests(unittest.TestCase):
    def test_unrecognized_executable_refused(self):
        with self.assertRaises(ValueError):
            patch_mios_ipc(b'MZ' + bytes(4094))

    @unittest.skipUnless(BASE.exists(), 'Frozen local Dolphin required')
    def test_derivative_reproducible_and_locked(self):
        original = BASE.read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), BASE_SHA256)
        modified, record = patch_mios_ipc(original)
        self.assertEqual(patch_mios_ipc(original), (modified, record))
        self.assertEqual(record, json.loads((ROOT / 'configs/gc-runtime.lock.json').read_text()))
        self.assertEqual(len(original), len(modified))
        self.assertLess(sum(a != b for a, b in zip(original, modified)), 64)
        with self.assertRaises(ValueError):
            patch_mios_ipc(modified)

    @unittest.skipUnless(BASE.exists(), 'Frozen local Dolphin required')
    def test_single_byte_change_in_source_refused(self):
        corrupt = bytearray(BASE.read_bytes())
        corrupt[-1] ^= 1
        with self.assertRaises(ValueError):
            patch_mios_ipc(corrupt)


if __name__ == '__main__':
    unittest.main()

import hashlib
import unittest

from kwce.channels import compress_lz10, load_library
from kwce.u8_build import build_u8
from scripts.audit_nintendo_menu_art import unpack


class NintendoMenuAuditTest(unittest.TestCase):
    def test_valid_and_corrupted_imd5(self):
        load_library()
        archive = build_u8({"arc/example.bin": b"synthetic"}, dot=False)
        payload = b"LZ77" + compress_lz10(archive)
        wrapped = (b"IMD5" + len(payload).to_bytes(4, "big") + bytes(8)
                   + hashlib.md5(payload).digest() + payload)
        self.assertEqual(unpack(wrapped).get("arc/example.bin"), b"synthetic")
        corrupted = bytearray(wrapped)
        corrupted[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "wrapper"):
            unpack(bytes(corrupted))
        with self.assertRaisesRegex(ValueError, "wrapper"):
            unpack(wrapped[:-1])


if __name__ == "__main__":
    unittest.main()

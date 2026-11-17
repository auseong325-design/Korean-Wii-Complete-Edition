import struct
import unittest

from scripts.audit_nintendo_error_sites import SITES, validate


def fake_executable():
    """Four synthetic text sections containing only the expected constants."""
    data = bytearray(0x100 + 32*len(SITES))
    for index, site in enumerate(SITES):
        offset = 0x100 + index*32
        struct.pack_into('>I', data, 4*index, offset)
        struct.pack_into('>I', data, 0x48+4*index, site-24)
        struct.pack_into('>I', data, 0x90+4*index, 32)
        for pos in range(offset, offset+32, 4):
            struct.pack_into('>I', data, pos, 0x60000000)
        struct.pack_into('>I', data, offset+20, 0x3c600004)  # lis r3,4
        struct.pack_into('>I', data, offset+24, 0x3863ff70)  # addi r3,r3,-144
    return data


class NintendoErrorSiteTest(unittest.TestCase):
    def test_checks_all_constants_and_rejects_mutation(self):
        data = fake_executable()
        report = validate(data)
        self.assertEqual(report['static_site_count'], 4)
        self.assertFalse(report['real_console_site_identified'])
        struct.pack_into('>I', data, 0x100+32+24, 0x60000000)
        with self.assertRaises(ValueError):
            validate(data)


if __name__ == '__main__':
    unittest.main()

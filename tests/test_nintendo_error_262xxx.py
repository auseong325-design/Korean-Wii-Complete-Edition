"""Locks the Nintendo Channel error-262xxx findings (RC3 W4 Goal B) against the shipped DOL, and
exercises the CSData decrypt+check pipeline on a synthetic, in-repo WC24 file (no network, no
console data). This is EVIDENCE for the service/environment-side conclusion, not an executable patch.
"""
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC3 = ROOT / 'workspace/channels/nintendo/rc3'
sys.path.insert(0, str(RC3))

try:
    from dol import Dol, load_dol
    from scan_codes import scan
    import csdata_check as cc
    HAVE = True
except Exception:  # pragma: no cover - capstone/pycryptodome missing
    HAVE = False


@unittest.skipUnless(HAVE, 'rc3 analysis deps (capstone/pycryptodome) unavailable')
class NintendoError262xxxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dol = Dol(load_dol())
        cls.codes = {x['code'] for x in scan(cls.dol, 260000, 269999)}

    def test_262xxx_constant_map(self):
        # the constants that actually exist in build-v13 content 1
        self.assertLessEqual({262000, 262102, 262103, 262105, 262106, 262301, 262302, 262303}, self.codes)
        # 262104 is NOT a constant in this DOL (matches the v4 note); it is only ever runtime-composed
        self.assertNotIn(262104, self.codes)

    def test_262000_vs_262303_site(self):
        # func 0x80053310 builds BOTH: 262000 when the download-manager object *(0x80476704) is null,
        # 262303 when it exists but its inner record is empty. Confirm both constants sit in that function.
        sites = {x['code']: x for x in scan(self.dol, 262000, 262303) if x['func'] == '0x80053310'}
        self.assertIn(262000, sites)
        self.assertIn(262303, sites)

    def _synthetic_csdata(self):
        body = bytearray(0x200)
        struct.pack_into('>H', body, 0, 0)        # +0 u16 == 0 (version_ok needs this)
        body[2] = 6                               # version >= 6
        body[0x28] = 0                            # flag clear
        body[0x35:0x35 + 10] = b'short/path'      # +0x35 string, short
        struct.pack_into('>I', body, 4, len(body))
        import binascii
        struct.pack_into('>I', body, 8, binascii.crc32(bytes(body)) & 0xffffffff)
        return bytes(body)

    def test_reimplemented_checks_accept_valid_csdata(self):
        cc.STR35_LIMIT = cc.str35_limit(self.dol)
        code, detail = cc.checks(self._synthetic_csdata())
        self.assertEqual(code, 0)
        self.assertTrue(detail['size_ok'] and detail['crc_ok'] and detail['version_ok'] and detail['str35_len_ok'])

    def test_bad_version_is_262000(self):
        cc.STR35_LIMIT = cc.str35_limit(self.dol)
        bad = bytearray(self._synthetic_csdata())
        bad[2] = 5                                # version < 6
        import binascii
        struct.pack_into('>I', bad, 8, 0)
        struct.pack_into('>I', bad, 8, binascii.crc32(bytes(bad)) & 0xffffffff)
        self.assertEqual(cc.checks(bytes(bad))[0], 262000)


if __name__ == '__main__':
    unittest.main()

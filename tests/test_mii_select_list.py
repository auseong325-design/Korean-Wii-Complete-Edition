"""Validate the synthetic Mii Contest condition-search feed (select_list{code*10+gender}.ces).

258404 was HTTP 404 on the search path because the test NAND feed lacked these files; the public
WiiLink service generates them (MakeSelectList). This builds them with the same MakeList ('LL')
format as the plaza lists, so the condition-search results screen renders instead of 258404.  The
on-screen result is confirmed by the lead in Dolphin.
"""
import hashlib
import hmac
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))

from Crypto.Cipher import AES  # noqa: E402
import make_channel_access_fixtures as mk  # noqa: E402

WRITER = ROOT / 'workspace/channels/mii-contest/references/server-source/common/writer.go'


def _lz10_decompress(data):
    assert data[0] == 0x10
    size = int.from_bytes(data[1:4], 'little')
    out = bytearray()
    pos = 4
    while len(out) < size:
        flags = data[pos]; pos += 1
        for bit in range(7, -1, -1):
            if len(out) >= size:
                break
            if flags & (1 << bit):
                b0, b1 = data[pos], data[pos + 1]; pos += 2
                length = (b0 >> 4) + 3
                dist = (((b0 & 0xF) << 8) | b1) + 1
                for _ in range(length):
                    out.append(out[-dist])
            else:
                out.append(data[pos]); pos += 1
    return bytes(out[:size])


class MiiSelectListTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files, cls.routes = mk.make_mii_rich()
        src = WRITER.read_text()
        cls.key, cls.iv, cls.mac = (mk.source_array(src, n) for n in ('aesKey', 'aesIv', 'hmacKey'))

    def _expected_names(self):
        return {f'select_list{s * 10 + g:03d}.ces' for s in range(1, 20) for g in (1, 2)}

    def test_all_38_select_lists_present(self):
        names = {n for n in self.files if n.startswith('select_list')}
        self.assertEqual(names, self._expected_names())

    def test_routes_cover_both_region_prefixes(self):
        for n in self._expected_names():
            self.assertEqual(self.routes['* /151/' + n], n)
            self.assertEqual(self.routes['* /0/' + n], n)

    def test_mc_wrapper_hmac_and_miilist(self):
        # skill 11, gender 1 -> list number 111
        blob = self.files['select_list111.ces']
        self.assertEqual(blob[:4], b'MC\x00\x01')
        body = blob[24:]
        self.assertEqual(hmac.new(self.mac, body, hashlib.sha1).digest(), blob[4:24])
        plain = AES.new(self.key, AES.MODE_CBC, self.iv).decrypt(body)
        mii_list = _lz10_decompress(plain)
        self.assertEqual(mii_list[:2], b'LL')                       # SelectList tag
        self.assertEqual(struct.unpack_from('>I', mii_list, 4)[0], 151)   # CountryRegion
        self.assertEqual(struct.unpack_from('>I', mii_list, 8)[0], 111)   # ListNumber == code*10+gender
        self.assertEqual(mii_list[32:34], b'PN')                    # MiiPairNumber tag (after 32-byte header)
        self.assertIn(b'PM', mii_list)                               # at least one Mii pair

    def test_select_list_bytes_are_deterministic(self):
        # The select_list files carry no time-based fields, so they regenerate identically.
        again, _ = mk.make_mii_rich()
        for n in self._expected_names():
            self.assertEqual(again[n], self.files[n])


if __name__ == '__main__':
    unittest.main()

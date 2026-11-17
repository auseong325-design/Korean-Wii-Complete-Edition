"""Validate the synthetic Votes feed against the client parser's documented rules.

These checks mirror decodeFirstPlayInfoData (@0x80062d40) and decodePackData (@0x80062f54) as
reverse-engineered in workspace/channels/votes/references/protocol-research.md, so a pass means the
isolated channel accepts the feed (no Dolphin needed to prove acceptance).  They do not prove the
on-screen layout; the lead confirms that in Dolphin.
"""
import hashlib
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from kwce import votes_feed
from kwce.channel_access import validate_fixtures

ROOT = Path(__file__).resolve().parents[1]


def _unwrap(signed):
    """Strip the 320-byte signature block and decode the LZ11 literal stream back to the pack."""
    assert len(signed) > 320
    stream = signed[320:]
    assert stream[0] == 0x11, 'LZ11 tag'
    size = int.from_bytes(stream[1:4], 'little')
    out = bytearray()
    pos = 4
    while len(out) < size:
        flags = stream[pos]; pos += 1
        for bit in range(7, -1, -1):
            if len(out) >= size:
                break
            if flags & (1 << bit):
                raise AssertionError('feed uses literal blocks only')
            out.append(stream[pos]); pos += 1
    return bytes(out[:size])


def _crc_ok(pack):
    return zlib.crc32(pack[12:]) & 0xffffffff == struct.unpack_from('>I', pack, 8)[0]


def _tables(pack):
    h = lambda o: struct.unpack_from('>I', pack, o)[0]
    w = lambda o: struct.unpack_from('>H', pack, o)[0]
    return dict(
        nat_q=(pack[0x14], h(0x15)), ww_q=(pack[0x19], h(0x1A)), qtext=(pack[0x1E], h(0x1F)),
        nat_r=(pack[0x23], h(0x24)), det_nat=(w(0x28), h(0x2A)), pos=(w(0x2E), h(0x30)),
        ww_r=(pack[0x34], h(0x35)), det_ww=(w(0x39), h(0x3B)), country=(w(0x3F), h(0x41)),
    )


class VotesFeedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files, cls.routes = votes_feed.build_feed()
        cls.first = _unwrap(cls.files['first_data.bin'])
        cls.voting = _unwrap(cls.files['voting.bin'])

    def test_feed_is_deterministic(self):
        a, _ = votes_feed.build_feed()
        b, _ = votes_feed.build_feed()
        self.assertEqual(a, b)

    def test_first_data_lists_korea_with_languages(self):
        pack = self.first
        self.assertEqual(struct.unpack_from('>I', pack, 0)[0], 1)
        self.assertEqual(struct.unpack_from('>I', pack, 4)[0], len(pack))
        self.assertTrue(_crc_ok(pack))
        num_countries = pack[0x0C]
        table_off = struct.unpack_from('>I', pack, 0x0D)[0]
        num_lang = pack[0x11]
        self.assertEqual(table_off, 18 + num_lang * 4)
        codes = {}
        for i in range(num_countries):
            at = table_off + i * 6
            codes[pack[at]] = [pack[at + 2 + j] for j in range(pack[at + 1])]
        self.assertIn(136, codes)
        self.assertTrue(1 <= len(codes[136]) < 5)
        for i in range(num_lang):
            off = struct.unpack_from('>I', pack, 18 + i * 4)[0]
            self.assertTrue(18 <= off < len(pack))
            self.assertIn(b'\0\0', pack[off:off + 64])

    def test_voting_header_bounds_and_crc(self):
        pack = self.voting
        self.assertTrue(0x46 <= len(pack) <= 0x10000)
        self.assertEqual(struct.unpack_from('>I', pack, 4)[0], len(pack))
        self.assertTrue(_crc_ok(pack))
        for off in (0x15, 0x1A, 0x1F, 0x24, 0x2A, 0x30, 0x35, 0x3B, 0x41):
            self.assertLess(struct.unpack_from('>I', pack, off)[0], len(pack))
        t = _tables(pack)
        self.assertLessEqual(t['det_ww'][0], 0x80)
        self.assertLessEqual(t['nat_q'][0], 6)
        self.assertLessEqual(t['ww_q'][0], 2)
        self.assertLessEqual(t['nat_r'][0], 13)
        self.assertEqual(t['ww_r'][0], 1)

    def test_question_info_window_and_entry_bounds(self):
        pack = self.voting
        t = _tables(pack)
        num_text = t['qtext'][0]
        for count, base in (t['nat_q'], t['ww_q']):
            for i in range(count):
                at = base + i * 0x13
                start = struct.unpack_from('>I', pack, at + 6)[0]
                end = struct.unpack_from('>I', pack, at + 10)[0]
                self.assertTrue(votes_feed.WINDOW_LO <= start <= votes_feed.WINDOW_HI)
                self.assertTrue(votes_feed.WINDOW_LO <= end <= votes_feed.WINDOW_HI)
                self.assertGreaterEqual(end, start)
                self.assertLess(pack[at + 0x0E], 5)
                self.assertLess(struct.unpack_from('>I', pack, at + 0x0F)[0], num_text)

    def test_question_text_offsets_resolve(self):
        pack = self.voting
        count, base = _tables(pack)['qtext']
        seen_languages = set()
        for i in range(count):
            at = base + i * 0x0D
            seen_languages.add(pack[at])
            for field in (1, 5, 9):
                off = struct.unpack_from('>I', pack, at + field)[0]
                self.assertTrue(0x45 <= off < len(pack))
                self.assertIn(b'\0\0', pack[off:off + 512])
        self.assertGreaterEqual(len(seen_languages), 2)

    def test_national_detail_and_position_indices(self):
        pack = self.voting
        t = _tables(pack)
        npos = t['pos'][0]
        nr_count, nr_base = t['nat_r']
        detail_total = t['det_nat'][0]
        for i in range(nr_count):
            at = nr_base + i * 0x23
            self.assertEqual(pack[at + 0x1D], 1)
            detail_num = pack[at + 0x1E]
            detail_start = struct.unpack_from('>I', pack, at + 0x1F)[0]
            self.assertLessEqual(detail_start + detail_num, detail_total)
        dc, db = t['det_nat']
        for i in range(dc):
            at = db + i * 0x0D
            pcount = pack[at + 8]
            pnum = struct.unpack_from('>I', pack, at + 9)[0]
            self.assertLessEqual(pnum + pcount, npos)

    def test_worldwide_country_table_indices(self):
        pack = self.voting
        t = _tables(pack)
        country_rows = t['country'][0]
        dc, db = t['det_ww']
        self.assertGreaterEqual(dc, 8)
        for i in range(dc):
            at = db + i * 0x1A
            cols = pack[at + 0x15]
            num = struct.unpack_from('>I', pack, at + 0x16)[0]
            self.assertLessEqual(num + cols, country_rows)
        _, cbase = t['country']
        for i in range(country_rows):
            at = cbase + i * 5
            off = struct.unpack_from('>I', pack, at + 1)[0]
            self.assertTrue(0x45 <= off < len(pack))
            self.assertIn(b'\0\0', pack[off:off + 512])

    def test_fixture_manifest_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for name, data in self.files.items():
                (tmp / name).write_bytes(data)
            route_bytes = ''.join(k + '\t' + v + '\n' for k, v in self.routes.items()).encode('ascii')
            (tmp / 'routes.tsv').write_bytes(route_bytes)
            (tmp / 'fixture-manifest.json').write_text(json.dumps(dict(
                channel='votes', synthetic=True, routes_sha256=hashlib.sha256(route_bytes).hexdigest(),
                files=[dict(path=n, size=len(d), sha256=hashlib.sha256(d).hexdigest())
                       for n, d in self.files.items()])))
            rows, seen = validate_fixtures(tmp, 'votes')
            self.assertEqual(rows, 3)
            self.assertEqual(seen, len(self.routes))


if __name__ == '__main__':
    unittest.main()

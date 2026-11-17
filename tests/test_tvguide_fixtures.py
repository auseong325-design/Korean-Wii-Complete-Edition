import struct,unittest
from kwce.tvguide_fixtures import header_fixture,pack_hdp,unpack_hdp

class TvGuideFixtureTests(unittest.TestCase):
    def test_korean_synthetic_header_has_bounded_relocations(self):
        raw=header_fixture();data,rels,roots=unpack_hdp(raw)
        self.assertEqual(roots,{'basi':0});self.assertIn('시험 방송'.encode('utf-16-be'),data)
        self.assertEqual(struct.unpack_from('>I',data,0)[0],1)
        self.assertEqual(struct.unpack_from('>I',data,0x34)[0],1)
        self.assertEqual(struct.unpack_from('>I',data,0x3c)[0],47)
        self.assertTrue(all(struct.unpack_from('>I',data,p)[0]<len(data)for p in rels))
    def test_truncation_corrupt_lengths_and_outside_pointer_rejected(self):
        raw=header_fixture()
        for invalid in (raw[:-1],raw+b'\0',raw[:8]+bytes(4)+raw[12:]):
            with self.assertRaises(ValueError):unpack_hdp(invalid)
        data,rels,roots=unpack_hdp(raw);data=bytearray(data);struct.pack_into('>I',data,rels[0],len(data))
        with self.assertRaises(ValueError):pack_hdp(data,rels,roots)
    def test_unaligned_duplicate_relocations_and_unsafe_root_rejected(self):
        for data,rels,roots in [(bytes(32),[1],{'basi':0}),(bytes(32),[0,0],{'basi':0}),(bytes(32),[],{'basi':32}),(bytes(32),[],{'../bad':0})]:
            with self.assertRaises(ValueError):pack_hdp(data,rels,roots)
    def test_corrected_native_header_root_and_encrypted_transport(self):
        from kwce.tvguide_fixtures import encrypted_header,compressed_header
        from Crypto.Cipher import AES
        data,rels,roots=unpack_hdp(header_fixture(schema=2));self.assertEqual(roots,{'main':0})
        module=bytes(512)+bytes(range(16))+bytes(16);wrapped=encrypted_header(module,schema=2)
        self.assertEqual(wrapped[:4],b'WC24');self.assertEqual(len(wrapped)-320,len(compressed_header(2)))
        self.assertEqual(AES.new(module[512:528],AES.MODE_OFB,iv=wrapped[48:64]).decrypt(wrapped[320:]),compressed_header(2))



class TvGuideScheduleFeedTests(unittest.TestCase):
    """wave 3: header+epg+str consistency against the DOL validators.

    Validators ported from static analysis of the TV Guide DOL (content 1):
      HeaderValidate 0x803a2580, EpgValidate 0x803a2950 (cross-references the
      header station table via lookupStationById 0x803a2704), StrValidate
      0x803a2cac. HDPK pointers are payload-relative offsets.
    """
    MODULE = bytes(512) + bytes(range(16)) + bytes(16)  # 544B test module, no real key

    @staticmethod
    def _root(raw):
        data, rels, roots = unpack_hdp(raw)
        assert 'main' in roots
        return data, roots['main']

    @classmethod
    def _u32(cls, d, at):
        return struct.unpack_from('>I', d, at)[0]

    @classmethod
    def header_validate(cls, raw):
        d, b = cls._root(raw)
        if cls._u32(d, b + 0x34) == 0:
            return 0x11
        if cls._u32(d, b + 0x38) == 0:
            return 8
        cntB = cls._u32(d, b + 0x3c)
        if cntB == 0:
            return 0x13
        if cls._u32(d, b + 0x40) == 0:
            return 9
        for c, p, err in [(0x44, 0x48, 0xa), (0x4c, 0x50, 0xb), (0x54, 0x58, 0xc),
                          (0x5c, 0x60, 0xd), (0x64, 0x68, 0xe), (0x6c, 0x70, 0xf)]:
            if cls._u32(d, b + c) != 0 and cls._u32(d, b + p) == 0:
                return err
        areas = cls._u32(d, b + 0x40)
        for i in range(cntB):
            rec = areas + i * 0x10
            if cls._u32(d, rec + 8) == 0:
                return 0x12
            if cls._u32(d, rec + 0xc) == 0:
                return 0x10
        return 0

    @classmethod
    def _lookup_station(cls, header_raw, sid):
        d, b = cls._root(header_raw)
        cnt = cls._u32(d, b + 0x34)
        ptr = cls._u32(d, b + 0x38)
        return any(cls._u32(d, ptr + i * 0xc) == sid for i in range(cnt))

    @classmethod
    def epg_validate(cls, epg_raw, header_raw):
        d, b = cls._root(epg_raw)
        cnt = cls._u32(d, b + 0x1c)
        if cnt == 0:
            return 0x1a
        ptr = cls._u32(d, b + 0x20)
        if ptr == 0:
            return 0x15
        if cls._u32(d, b + 0x24) != 0 and cls._u32(d, b + 0x28) == 0:
            return 0x16
        for i in range(cnt):
            e = ptr + i * 0xc
            if cls._u32(d, e + 4) != 0 and cls._u32(d, e + 8) == 0:
                return 0x17
            if cls._u32(d, cls._u32(d, e + 8) + 4) == 0:
                return 0x18
            if not cls._lookup_station(header_raw, cls._u32(d, e + 0)):
                return 0x1b
        return 0

    @classmethod
    def str_validate(cls, str_raw):
        d, b = cls._root(str_raw)
        if cls._u32(d, b + 0x18) != 0 and cls._u32(d, b + 0x1c) == 0:
            return 0x1d
        return 0

    def test_header_schema_2_and_3_pass_header_validate(self):
        for schema in (2, 3):
            self.assertEqual(self.header_validate(header_fixture(schema=schema)), 0)

    def test_epg_and_str_pass_and_cross_reference_header(self):
        from kwce.tvguide_fixtures import epg_payload, str_payload
        header = header_fixture(schema=3)
        self.assertEqual(self.epg_validate(epg_payload((1,)), header), 0)
        self.assertEqual(self.str_validate(str_payload()), 0)
        self.assertEqual(self.str_validate(str_payload(('가', '나'))), 0)

    def test_epg_with_unknown_station_is_rejected_by_cross_reference(self):
        from kwce.tvguide_fixtures import epg_payload
        header = header_fixture(schema=3)  # only station id 1 exists
        self.assertEqual(self.epg_validate(epg_payload((999,)), header), 0x1b)

    def test_feed_v7_resources_are_enveloped_and_roundtrip(self):
        from kwce.tvguide_fixtures import feed_v7_resources, compressed_resource, epg_payload
        from Crypto.Cipher import AES
        res = feed_v7_resources(self.MODULE)
        self.assertEqual(set(res), {'header', 'epg', 'string'})
        for payload in res.values():
            self.assertEqual(payload[:4], b'WC24')
        expected = compressed_resource(epg_payload((1,)))
        got = AES.new(self.MODULE[512:528], AES.MODE_OFB, iv=res['epg'][48:64]).decrypt(res['epg'][320:])
        self.assertEqual(got, expected)

    def test_feed_v7_on_disk_matches_fixtures_and_routes_cover_three_files(self):
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        feed = root / 'workspace/channels/tvguide/local-feed-v7'
        if not feed.is_dir():
            self.skipTest('local-feed-v7 not built')
        module = (root / 'workspace/sandbox/tvguide-test-v1/user/Wii/title/00010001/48424e4a/data/wc24pubk.mod').read_bytes()
        from kwce.tvguide_fixtures import feed_v7_resources
        res = feed_v7_resources(module)
        self.assertEqual((feed / 'header.bin').read_bytes(), res['header'])
        self.assertEqual((feed / 'epg.bin').read_bytes(), res['epg'])
        self.assertEqual((feed / 'str.bin').read_bytes(), res['string'])
        routes = (feed / 'routes.tsv').read_text()
        for name in ('header.bin', 'epg.bin', 'str.bin'):
            self.assertIn('* /%s\t%s' % (name, name), routes)
        manifest = json.loads((feed / 'fixture-manifest.json').read_text())
        self.assertEqual(manifest['revision'], 7)
        self.assertTrue(manifest['serves_schedule'])
import struct,unittest,random,zlib,tempfile,hashlib,sys
from pathlib import Path
from kwce.channels import ChannelArchive,layout_sections,textbox,replace_textbox,rebuild_layout,fit_korean_textbox,patch_utf16_literals,compress_lz10,load_library
from kwce.channel_vff import VFF
from test_formats import archive

class ChannelTests(unittest.TestCase):
    def test_short_label_fits_without_changing_pane_or_height(self):
        section=bytearray(116);section[:4]=b'txt1';struct.pack_into('>fff',section,68,69,28,24);struct.pack_into('>ff',section,100,24,28)
        after=fit_korean_textbox(section,'지구본')
        self.assertLessEqual(struct.unpack_from('>f',after,100)[0]*3,69)
        self.assertEqual(after[:100],section[:100]);self.assertEqual(after[104:],section[104:])

    def test_utf16_constants_keep_printf_tokens_and_neighbor_bytes(self):
        original=b'\0\0'+('As of %02d:%02d a.m.\0').encode('utf-16-be')+b'unchanged'
        changed,count=patch_utf16_literals(original,{'As of':'기준',' a.m.':' 오전'})
        self.assertEqual(count,2);self.assertEqual(len(changed),len(original));self.assertTrue(changed.endswith(b'unchanged'))
        self.assertIn('%02d:%02d'.encode('utf-16-be'),changed)
        with self.assertRaises(ValueError):patch_utf16_literals(original,{'%02d:%02d':'%s'})
        with self.assertRaises(ValueError):patch_utf16_literals(original,{'As of':'원본보다 훨씬 긴 문자열'})
        with self.assertRaises(ValueError):patch_utf16_literals(original,{'not present':'없음'})

    def test_lz10_overlapping_and_window_boundary_roundtrips(self):
        load_library();from libWiiPy.archive import decompress_lz77
        rng=random.Random(631)
        for data in [b'',b'A',b'A'*8000,bytes(range(256))*32,rng.randbytes(10000),rng.randbytes(4096)*2]:
            with self.subTest(size=len(data)):self.assertEqual(decompress_lz77(compress_lz10(data)),data)

    def test_private_delta_growth_shrink_and_wrong_base(self):
        from kwce.channel_patch import make_patch,apply_patch
        for before,after in [(b'',b'added'),(b'x'*9000,b'x'*4096+b'changed'+b'x'*4100),(b'x'*100,b'')]:
            with self.subTest(size=len(after)):
                patch=make_patch(before,after);self.assertEqual(apply_patch(before,patch),after)
                with self.assertRaises(ValueError):apply_patch(before+b'wrong',patch)
                with self.assertRaises(ValueError):apply_patch(before,patch[:-1])

    @staticmethod
    def forecast_fixture():
        data=bytearray(256);struct.pack_into('>II',data,0,0,len(data));data[20]=136;data[24]=1
        struct.pack_into('>II',data,48,1,88);struct.pack_into('>II',data,80,1,96)
        struct.pack_into('>I',data,92,160);struct.pack_into('>III',data,100,176,0,192)
        for at,text in [(160,'Sunny'),(176,'Seoul'),(192,'South Korea')]:data[at:at+len(text)*2]=text.encode('utf-16-be')
        struct.pack_into('>I',data,8,zlib.crc32(data[12:])&0xffffffff)
        return data

    def test_forecast_overlay_preserves_numbers_coordinates_and_pointers(self):
        from kwce.forecast_data import localize_forecast
        load_library();from libWiiPy.archive import decompress_lz77
        before=self.forecast_fixture();after,record=localize_forecast(compress_lz10(before),{'Sunny':'맑음','Seoul':'서울','South Korea':'대한민국'})
        after=decompress_lz77(after);self.assertEqual(after[12:160],before[12:160]);self.assertEqual(record['translated_unique_strings'],3)
        self.assertEqual(zlib.crc32(after[12:])&0xffffffff,struct.unpack_from('>I',after,8)[0])
        self.assertIn('서울'.encode('utf-16-be'),after)

    def test_forecast_wrong_crc_country_and_slot_overflow_rejected(self):
        from kwce.forecast_data import localize_forecast
        for at in [8,20,24]:
            data=self.forecast_fixture();data[at]^=1
            with self.subTest(at=at),self.assertRaises(ValueError):localize_forecast(compress_lz10(data),{})
        with self.assertRaises(ValueError):localize_forecast(compress_lz10(self.forecast_fixture()),{'Seoul':'지나치게 긴 도시 이름'})

    def test_public_download_envelope_identity_crc_and_size_guards(self):
        from kwce.forecast_cache import inspect_public_download
        data=self.forecast_fixture();struct.pack_into('>II',data,12,123456,123546);struct.pack_into('>I',data,8,zlib.crc32(data[12:])&0xffffffff)
        raw=bytes(320)+compress_lz10(data);record=inspect_public_download(raw,'forecast')
        self.assertEqual(record['country'],136);self.assertFalse(record['RSA_signature_independently_verified'])
        with self.assertRaises(ValueError):inspect_public_download(raw[:320],'forecast')
        with self.assertRaises(ValueError):inspect_public_download(raw,'other')
        data[20]=49
        with self.assertRaises(ValueError):inspect_public_download(bytes(320)+compress_lz10(data),'forecast')

    def test_cache_replay_rejects_stale_and_future_snapshots(self):
        import datetime
        from kwce.forecast_cache import valid_at
        record={'opened_utc':'2026-10-22T07:00:00+00:00','closed_utc':'2026-10-22T08:03:00+00:00'}
        for text,expected in [('2026-10-22T07:00:00+00:00',True),('2026-10-22T08:02:59+00:00',True),('2026-10-22T08:03:00+00:00',False),('2026-10-22T06:59:59+00:00',False)]:
            with self.subTest(instant=text):self.assertEqual(valid_at(record,datetime.datetime.fromisoformat(text)),expected)
        with self.assertRaises(ValueError):valid_at(record,datetime.datetime(2026,10,22,7))

    def test_public_task_policy_rejects_similar_hosts_regions_and_titles(self):
        sys.path.insert(0,str(Path('scripts').resolve()));from forecast_profile import public_forecast_task
        def task(url):
            data=bytearray(512);struct.pack_into('>II',data,8,0x00010002,0x48414645);data[180:180+len(url)]=url;return data
        self.assertTrue(public_forecast_task(task(b'http://fore.wiilink24.com/1/136/forecast.bin')))
        for url in [b'http://fore.wiilink24.com.evil/1/136/forecast.bin',b'http://fore.wiilink24.com/1/049/forecast.bin',b'https://fore.wiilink24.com/1/136/forecast.bin',b'http://fore.wiilink24.com/1/136/forecast.bin?identifier=1']:
            with self.subTest(url=url):self.assertFalse(public_forecast_task(task(url)))
        bad=task(b'http://fore.wiilink24.com/1/136/forecast.bin');bad[8]=1;self.assertFalse(public_forecast_task(bad))

    def test_installed_shared_content_corruption_is_detected(self):
        from kwce.channel_validation import verify_installed_title
        with tempfile.TemporaryDirectory()as tmp:
            wii=Path(tmp);content=wii/'title/00010002/48414645/content';content.mkdir(parents=True);shared=wii/'shared1';shared.mkdir()
            blob=b'example font';digest=hashlib.sha1(blob).digest();tmd=bytearray(0x1e4+36);struct.pack_into('>H',tmd,0x1de,1);struct.pack_into('>IHHQ',tmd,0x1e4,7,0,0x8001,len(blob));tmd[0x1f4:0x208]=digest
            (content/'title.tmd').write_bytes(tmd);(shared/'content.map').write_bytes(b'00000000'+digest);(shared/'00000000.app').write_bytes(blob)
            self.assertEqual(verify_installed_title(wii,'0001000248414645',bytes(tmd)),1)
            (shared/'00000000.app').write_bytes(b'changed font')
            with self.assertRaises(ValueError):verify_installed_title(wii,'0001000248414645',bytes(tmd))

    def test_virtual_dot_directory_is_safe_and_topology_preserved(self):
        data=archive().replace(b'arc\0',b'.\0\0\0');a=ChannelArchive(data)
        after=a.replace('test',b'larger payload')
        self.assertEqual(ChannelArchive(after).get('other'),b'xyz')
        self.assertEqual(data[44:56],after[44:56])

    def test_dot_file_and_parent_traversal_rejected(self):
        for name in [b'..\0\0',b'a/b\0']:
            with self.subTest(name=name),self.assertRaises(ValueError):ChannelArchive(archive().replace(b'arc\0',name))

    def test_textbox_long_hangul_relocation_keeps_style(self):
        section=bytearray(124);section[:4]=b'txt1';struct.pack_into('>I',section,4,len(section));section[12:17]=b'pane\0'
        struct.pack_into('>HH',section,76,8,8);struct.pack_into('>I',section,88,116);section[116:124]='abc\0'.encode('utf-16-be')
        after=replace_textbox(bytes(section),'긴 한국어 문장\n둘째 줄')
        self.assertEqual(textbox(after),('pane','긴 한국어 문장\n둘째 줄'))
        self.assertEqual(section[8:76],after[8:76]);self.assertEqual(section[92:116],after[92:116])
        header=bytearray(b'RLYT\xfe\xff'+bytes(10));struct.pack_into('>IHH',header,8,16+len(section),16,1)
        rebuilt=rebuild_layout(bytes(header+section),[after]);self.assertEqual(layout_sections(rebuilt),[after])

    def test_textbox_outside_bounds_rejected(self):
        b=bytearray(116);b[:4]=b'txt1';struct.pack_into('>H',b,78,2);struct.pack_into('>I',b,88,117)
        with self.assertRaises(ValueError):textbox(b)

    @staticmethod
    def blank_vff():
        data=bytearray(512*64-480);data[:4]=b'VFF ';struct.pack_into('>H',data,4,0xfeff);struct.pack_into('>I',data,8,512*64);struct.pack_into('>H',data,12,32)
        return bytes(data)

    def test_vff_multi_file_chains_and_redundant_tables(self):
        v=VFF(self.blank_vff());a=bytes(range(256))*7;b=b'second file'*70
        v=VFF(v.add('3.bin',a));v=VFF(v.add('4.bin',b))
        self.assertEqual(v.read('3.bin'),a);self.assertEqual(v.read('4.bin'),b)
        with self.assertRaises(ValueError):v.add('3.bin',b)

    def test_vff_corrupt_table_and_path_rejected(self):
        data=bytearray(self.blank_vff());data[32]=1
        with self.assertRaises(ValueError):VFF(bytes(data))
        v=VFF(self.blank_vff())
        with self.assertRaises(ValueError):v.add('../x.bin',b'data')

    def test_vff_cycle_is_detected(self):
        v=VFF(self.blank_vff());data=bytearray(v.add('3.bin',b'x'*1024))
        for base in [32,32+v.table_size]:data[base+3:base+5]=(2).to_bytes(2,'little')
        with self.assertRaises(ValueError):VFF(bytes(data)).read('3.bin')

    @unittest.skipUnless(Path('workspace/channels/forecast/work/forecast-usa-v7/content9-dec/weather_layout.arc').exists(),'local Forecast resources required')
    def test_font_extension_preserves_original_mapping_and_sheet_bytes(self):
        from kwce.channel_font import extend_font,font_data
        layout=ChannelArchive(Path('workspace/channels/forecast/work/forecast-usa-v7/content9-dec/weather_layout.arc').read_bytes());before=layout.get('arc/font/font_weather.brfnt')
        after,record=extend_font(before,'날씨 채널',Path('workspace/channels/forecast/references/NotoSansKR.ttf'))
        old,map1,_=font_data(before);new,map2,_=font_data(after)
        self.assertTrue(all(map2[c]==g for c,g in map1.items()))
        self.assertTrue(all(ord(c)in map2 for c in '날씨채널'))
        old_t=old[b'TGLP'][1];new_t=new[b'TGLP'][1];old_at=struct.unpack_from('>I',old_t,28)[0];new_at=struct.unpack_from('>I',new_t,28)[0]
        size=struct.unpack_from('>I',old_t,12)[0]*struct.unpack_from('>H',old_t,16)[0]
        self.assertEqual(before[old_at:old_at+size],after[new_at:new_at+size])

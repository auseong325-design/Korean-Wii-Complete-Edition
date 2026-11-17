import struct, unittest, zlib
from pathlib import Path
from kwce.channel_texture import decode_ia4, replace_ia4
from kwce.forecast_visual import layout_metrics
from kwce.channels import load_library, compress_lz10

class ForecastVisualTests(unittest.TestCase):
    def test_icon_korean_title_has_square_metrics_and_fits_without_squeezing(self):
        from kwce.forecast_visual import korean_banner_text
        from kwce.channels import replace_textbox
        raw=bytearray(116);raw[:4]=b'txt1';raw[12:21]=b'titleENG0'
        struct.pack_into('>ff',raw,68,120,38);struct.pack_into('>ff',raw,100,15.04,22.8)
        after,_=korean_banner_text(replace_textbox(raw,'Forecast Channel'),natural_title=True)
        width,height=struct.unpack_from('>ff',after,100)
        self.assertEqual(width,height);self.assertLess(width*4.55,119)
        self.assertEqual(after[36:76],raw[36:76])

    def test_news_banner_title_outline_has_clear_canvas_margin(self):
        from scripts.build_news import caption
        before=caption((432,56),'뉴스 채널','outline')
        after=caption((432,56),'뉴스 채널','outline',safe_outline=True)
        self.assertEqual(before.getbbox()[1],0)
        left,top,right,bottom=after.getbbox()
        self.assertGreaterEqual(top,2);self.assertLessEqual(bottom,54)
        self.assertGreater(left,0);self.assertLess(right,432)

    def test_icon_title_normalizes_non_square_font_design_units(self):
        from kwce.forecast_visual import korean_banner_text
        from kwce.channels import replace_textbox
        raw=bytearray(116);raw[:4]=b'txt1';raw[12:21]=b'titleENG0'
        struct.pack_into('>ff',raw,68,120,38);struct.pack_into('>ff',raw,100,15.04,22.8)
        after,_=korean_banner_text(replace_textbox(raw,'Forecast Channel'),natural_title=True,title_font_ratio=24/28)
        width,height=struct.unpack_from('>ff',after,100)
        self.assertAlmostEqual(width/24,height/28,places=6)
        self.assertLess(width*4.55,119)

    def test_layout_rebuild_updates_count_when_a_compatibility_pane_is_added(self):
        from kwce.channels import layout_sections,rebuild_layout
        header=bytearray(16);header[:6]=b'RLYT\xfe\xff';struct.pack_into('>HH',header,12,16,0);struct.pack_into('>I',header,8,16)
        pane=b'pan1'+struct.pack('>I',76)+bytes(68)
        first=rebuild_layout(bytes(header),[pane]);second=rebuild_layout(first,[pane,pane])
        self.assertEqual(layout_sections(first),[pane]);self.assertEqual(layout_sections(second),[pane,pane])
        self.assertEqual(layout_sections(rebuild_layout(second,[pane])),[pane])

    @unittest.skipUnless(Path('workspace/channels/forecast/originals/forecast-usa-wiilink-archive.wad').exists(),'local original required')
    def test_NASA_pixels_and_unrelated_textures_preserved(self):
        from kwce.channels import ChannelArchive
        from kwce.channel_texture import texture_records
        from kwce.forecast_visual import nasa_captions,globe_caption
        lib=load_library();from libWiiPy.archive import decompress_lz77
        title=lib.title.Title();title.load_wad(Path('workspace/channels/forecast/originals/forecast-usa-wiilink-archive.wad').read_bytes())
        original=decompress_lz77(ChannelArchive(title.get_content_by_index(9)).get('TPLCommon.tpl.LZ'))
        modified,record=nasa_captions(original,Path('workspace/channels/forecast/references/NotoSansKR.ttf'))
        self.assertTrue(all(r['NASA_original_pixels_preserved']for r in record['textures']))
        modified,record=globe_caption(modified)
        self.assertEqual(record['font'],'Batang Regular');self.assertEqual(record['text'],'지구본')
        self.assertEqual(len(original),len(modified));self.assertEqual(texture_records(original),texture_records(modified))
        for i in range(len(texture_records(original))):
            if i in [3,6,102]:continue
            # Decoding every IA4 image also checks alpha/intensity and tile padding bounds.
            r=texture_records(original)[i]
            if r['format']==2 and not r['palette']:self.assertEqual(decode_ia4(original,i).tobytes(),decode_ia4(modified,i).tobytes())

    def test_banner_translation_preserves_original_pane_style(self):
        from kwce.forecast_visual import korean_banner_text
        from kwce.channels import replace_textbox,textbox
        raw=bytearray(116);raw[:4]=b'txt1';raw[12:23]=b'titleENG0\0\0'
        struct.pack_into('>ff',raw,68,262,38);struct.pack_into('>ff',raw,100,28.8,34.2)
        before=replace_textbox(raw,'Forecast Channel');after,record=korean_banner_text(before)
        self.assertEqual(textbox(after)[1],'날씨 채널');self.assertEqual(record['pane'],'titleENG0')
        self.assertEqual(after[8:76],before[8:76]);self.assertEqual(after[92:116],before[92:116])

    def test_banner_fallback_messages_have_explicit_korean_start_instruction(self):
        from kwce.forecast_visual import korean_banner_text
        from kwce.channels import replace_textbox,textbox
        for name in ['textT0ENG','textT1ENG','textT2ENG']:
            raw=bytearray(116);raw[:4]=b'txt1';raw[12:12+len(name)]=name.encode()
            before=replace_textbox(raw,'English placeholder');after,record=korean_banner_text(before)
            self.assertTrue(textbox(after)[1].endswith('시작을 선택해 주세요.'))
            self.assertNotIn('Start',textbox(after)[1]);self.assertEqual(after[36:76],before[36:76])

    def test_partial_tiles_preserve_padding_and_unrelated_bytes(self):
        load_library(); from PIL import Image
        raw=bytearray(140);struct.pack_into('>III',raw,0,0x0020af30,1,12)
        struct.pack_into('>II',raw,12,20,0);struct.pack_into('>HHII',raw,20,3,9,2,64)
        raw[64:128]=bytes([0x67])*64;raw[128:]=b'KEEPTRAILER!'
        pic=Image.new('RGBA',(9,3),(255,255,255,255));out=replace_ia4(bytes(raw),0,pic)
        self.assertEqual(decode_ia4(out,0).tobytes(),pic.tobytes())
        self.assertEqual(out[:64],raw[:64]);self.assertEqual(out[128:],raw[128:])
        self.assertEqual(out[88:96],raw[88:96]);self.assertEqual(out[97:104],raw[97:104])

    def test_texture_rejects_truncation_and_colored_pixels(self):
        load_library();from PIL import Image
        raw=bytearray(96);struct.pack_into('>III',raw,0,0x0020af30,1,12)
        struct.pack_into('>II',raw,12,20,0);struct.pack_into('>HHII',raw,20,4,8,2,64)
        with self.assertRaises(ValueError):decode_ia4(bytes(raw[:-1]),0)
        with self.assertRaises(ValueError):replace_ia4(bytes(raw),0,Image.new('RGBA',(8,4),'red'))

    def test_temperature_both_states_share_center_and_width(self):
        section=bytearray(116);section[:4]=b'txt1';section[84]=5
        for pane,width in [('kion_setTUS0a',120),('kion_setTUS1a',190)]:
            struct.pack_into('>f',section,68,width)
            out=layout_metrics('set',pane,bytes(section))
            self.assertEqual(out[84],4);self.assertEqual(struct.unpack_from('>f',out,68)[0],120)
            self.assertEqual(out[8:68],section[8:68])

    def test_bottom_typography_keeps_hitbox_origin_and_animation_identity(self):
        section=bytearray(116);section[:4]=b'txt1';struct.pack_into('>f',section,40,14)
        struct.pack_into('>ff',section,100,28,28);struct.pack_into('>ff',section,68,200,32)
        out=layout_metrics('forecast','backTUS',bytes(section))
        self.assertEqual(struct.unpack_from('>fff',out,100),(24,24,0))
        self.assertEqual(struct.unpack_from('>f',out,40)[0],12)
        self.assertEqual(out[44:100],section[44:100]);self.assertEqual(out[:40],section[:40])

    def test_uv_table_overlay_preserves_numeric_code_and_pointers(self):
        from kwce.forecast_data import localize_forecast
        load_library();from libWiiPy.archive import decompress_lz77
        raw=bytearray(128);struct.pack_into('>II',raw,0,0,128);raw[20]=136;raw[24]=1
        struct.pack_into('>II',raw,56,1,88);struct.pack_into('>II',raw,88,4,100)
        raw[100:116]='Moderate'.encode('utf-16-be');struct.pack_into('>I',raw,8,zlib.crc32(raw[12:])&0xffffffff)
        out,record=localize_forecast(compress_lz10(raw),{'Moderate':'보통'});out=decompress_lz77(out)
        self.assertEqual(out[12:100],raw[12:100]);self.assertEqual(record['translated_unique_strings'],1)
        self.assertEqual(out[100:104],'보통'.encode('utf-16-be'))

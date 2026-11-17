"""Fast unit tests for the Korean Photo Prints Channel localization.

These exercise the components (patches, strings, font, banner, fixtures, configs)
against the original WAD; they do NOT run the multi-minute full WAD build.
"""
import json,re,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from kwce.channels import load_library,ChannelArchive,layout_sections,textbox
from kwce.wiiroom_formats import decompress_lz11,reencode_lz11_same_size
from kwce import bspatch
from kwce.photoprints_strings import translate_executable,rewrite_local_endpoints,loopback_reference_count
from kwce.photoprints_compat import patch_korean_area
from kwce.photoprints_font import append_hangul
from kwce.photoprints_banner import korean_banner_name,DISPLAY_NAME
from kwce import photoprints_fixtures as fx

WAD=ROOT/'workspace/channels/photoprints/originals/digicam-japan-v1024.wad'
PATCH=ROOT/'workspace/channels/photoprints/references/wiilink-patcher/bsdiff__digicam__Digicam_1_Japan.bsdiff'


def _title():
    lib=load_library();t=lib.title.Title();t.load_wad(WAD.read_bytes());return t


class WiiLinkPatch(unittest.TestCase):
    def test_patch_same_size_and_hosts(self):
        t=_title();c1=t.get_content_by_index(1);wl=bspatch.apply(c1,PATCH.read_bytes())
        self.assertEqual(len(decompress_lz11(wl)),len(decompress_lz11(c1)))
        d=decompress_lz11(wl)
        self.assertIn(b'cam-prod.wiilink24.com',d)
        self.assertNotIn(b'wch.fdinet.fujifilm.co.jp/wii_svr',d)


class Executable(unittest.TestCase):
    def setUp(self):
        self.dol=decompress_lz11(bspatch.apply(_title().get_content_by_index(1),PATCH.read_bytes()))
    def test_literals_fit_and_tokens_preserved(self):
        dol,rec=translate_executable(self.dol)
        self.assertEqual(rec['skipped'],[]);self.assertGreaterEqual(rec['applied'],8)
        self.assertEqual(len(dol),len(self.dol))
        cfg=json.loads((ROOT/'configs/photoprints-executable-v1-ko.json').read_text(encoding='utf-8'))
        for row in cfg['rows']:
            self.assertEqual(re.findall(r'%\w',row['expected']),re.findall(r'%\w',row['ko']))
    def test_local_endpoints(self):
        dol,_=translate_executable(self.dol);dol,_=patch_korean_area(dol)
        loc,rec=rewrite_local_endpoints(dol)
        self.assertEqual(len(loc),len(self.dol));self.assertGreaterEqual(loopback_reference_count(loc),1)
        self.assertNotIn(b'cam-prod',bytes(loc))
        self.assertTrue(reencode_lz11_same_size(bspatch.apply(_title().get_content_by_index(1),PATCH.read_bytes()),loc))
    def test_hardware_keeps_service_host(self):
        dol,_=translate_executable(self.dol);dol,_=patch_korean_area(dol)
        self.assertIn(b'cam-prod.wiilink24.com',bytes(dol));self.assertEqual(loopback_reference_count(dol),0)


class AreaBridge(unittest.TestCase):
    def test_kor_to_jpn(self):
        dol=decompress_lz11(_title().get_content_by_index(1))
        out,rec=patch_korean_area(dol)
        self.assertEqual(rec['bytes_changed'],1);self.assertEqual(rec['source_area'],6);self.assertEqual(rec['resource_area'],0)
        self.assertEqual(sum(a!=b for a,b in zip(dol,out)),1)
    def test_documents_scgetarea_and_both_builds(self):
        _,rec=patch_korean_area(decompress_lz11(_title().get_content_by_index(1)))
        self.assertEqual(rec['getter'],'0x800d0978')
        self.assertEqual(rec['pd_path_selector'],'0x802a81a8')
        self.assertEqual(rec['applied_in'],['local','hardware'])


class Font(unittest.TestCase):
    def test_append_hangul_roundtrip(self):
        from kwce.channel_font import font_data
        rodan=ChannelArchive(_title().get_content_by_index(2)).get('font_rodan_28.brfna')
        syl='가나다라확인취소디지털카메라프린트채널주문'
        new,rec=append_hangul(rodan,syl)
        self.assertEqual(rec['added_glyphs'],len(set(syl)))
        _,mapping,_=font_data(b'RFNT'+new[4:])
        for c in set(syl):self.assertIn(ord(c),mapping)
    def test_covers_fictional_pd_names(self):
        from kwce.channel_font import font_data
        from kwce import personal_data_format as fmt
        pd=''.join(v for v in fmt.FICTIONAL.values())
        syl=''.join(c for c in pd if 0xac00<=ord(c)<=0xd7a3)
        rodan=ChannelArchive(_title().get_content_by_index(2)).get('font_rodan_28.brfna')
        new,_=append_hangul(rodan,syl)
        _,mapping,_=font_data(b'RFNT'+new[4:])
        for c in set(syl):self.assertIn(ord(c),mapping)


class ArchiveFontFix(unittest.TestCase):
    """Boot crash 0x801bdf40 (ArchiveFontBase::FindGlyphIndex, mFontInfo NULL):
    the v1-v3 font lost its GLGR block. v6+ must keep an ArchiveFont-valid RFNA."""
    def setUp(self):
        self.rodan=ChannelArchive(_title().get_content_by_index(2)).get('font_rodan_28.brfna')
    def test_original_and_legacy(self):
        from kwce.photoprints_font import check_rfna
        self.assertEqual(self.rodan[16:20],b'GLGR');check_rfna(self.rodan)
        legacy,_=append_hangul(self.rodan,'가나')
        self.assertNotEqual(legacy[16:20],b'GLGR')   # the defect behind the crash
    def test_fixed_font_valid_and_lookups(self):
        from kwce.photoprints_font import append_hangul_rfna,check_rfna,find_glyph
        syl='가나다라확인취소디지털카메라프린트채널주문홍길동'
        new,rec=append_hangul_rfna(self.rodan,syl)
        self.assertEqual(new[16:20],b'GLGR');self.assertTrue(rec['glgr_preserved'])
        info=check_rfna(new);self.assertEqual(info['cmap'],23);self.assertEqual(info['cwdh'],2);self.assertTrue(info['all_sheets_in_set0'])
        for c in set(syl):self.assertIsNotNone(find_glyph(new,ord(c)))
        for c in 'Aあア写真':self.assertEqual(find_glyph(new,ord(c)),find_glyph(self.rodan,ord(c)))
        self.assertIsNone(find_glyph(new,ord('뷁')))  # not appended -> not found, no crash path


class Diagnostics(unittest.TestCase):
    def test_v4_v5_manifests(self):
        for rev,changed in((4,[]),(5,[1])):
            p=ROOT/f'workspace/channels/photoprints/build-v{rev}/build-manifest.json'
            if not p.exists():self.skipTest('diagnostic builds not present')
            m=json.loads(p.read_text(encoding='utf-8'))
            self.assertTrue(m['diagnostic'] and m['local_only']);self.assertEqual(m['changed_contents'],changed)
        self.assertTrue(json.loads((ROOT/'workspace/channels/photoprints/build-v4/build-manifest.json').read_text(encoding='utf-8'))['identical_to_original'])


class TextFit(unittest.TestCase):
    """Lead's v6 capture: PD_Dialog_Update TextA wrapped '...없습니' / '다.'."""
    @classmethod
    def setUpClass(cls):
        from kwce.photoprints_font import append_hangul_rfna
        from kwce import photoprints_textfit as tf
        from libWiiPy.archive import decompress_lz77
        cls.tf=tf;c2=ChannelArchive(_title().get_content_by_index(2));rodan=c2.get('font_rodan_28.brfna')
        cls.v1=json.loads((ROOT/'configs/photoprints-messages-v1-ko.json').read_text(encoding='utf-8'))['messages']
        cls.v8=json.loads((ROOT/'configs/photoprints-messages-v8-ko.json').read_text(encoding='utf-8'))['messages']
        chars=''.join(sorted({c for v in list(cls.v1.values())+list(cls.v8.values()) for c in v if 0xac00<=ord(c)<=0xd7a3}))
        cls.m=tf.Metrics(append_hangul_rfna(rodan,chars)[0]);cls.mj=tf.Metrics(rodan);cls.boxes={}
        for arc in('layout.arc.LZ','cursor.arc.LZ'):
            for k,v in tf.boxes_by_text(decompress_lz77(c2.get(arc)),set(cls.v8)).items():cls.boxes.setdefault(k,[]).extend(v)
    def test_calibration_matches_observed_wrap(self):
        jp='Wii本体に住所情報の設定ができません。';box=self.boxes[jp][0];ko=self.v1[jp]
        self.assertLessEqual(self.tf.width(self.m,box,ko[:-2]),box.w)       # '...없습니' stayed on line 1
        self.assertGreater(self.tf.width(self.m,box,ko[:-1]),box.w)          # '다' did not fit
        self.assertEqual(self.tf.wrapped_lines(self.m,box,ko),2)
        self.assertEqual(self.tf.overflow_lines(self.m,box,self.v8[jp]),[])
    def test_v8_fits_every_pane(self):
        for jp,ko in self.v8.items():
            for box in self.boxes.get(jp,[]):
                if box.file.split('/')[-1] in self.tf.DEBUG_LAYOUTS:continue
                self.assertLessEqual(len(ko.split('\n')),self.tf.budget(self.mj,box,jp),box.pane)
                self.assertGreaterEqual(self.tf.fit_scale(self.m,box,ko),self.tf.MIN_SCALE,box.pane)
                self.assertEqual(self.m.unmapped(ko),[])
    def test_v1_table_unchanged_for_old_builds(self):
        self.assertEqual(len(self.v1),len(self.v8))
        self.assertEqual(self.v1['Wii本体に住所情報の設定ができません。'],'Wii 본체에 주소 정보를 설정할 수 없습니다.')


class PersonalData(unittest.TestCase):
    def test_pinned_spd_and_fictional_sample(self):
        from kwce import photoprints_personal_data as pdata
        if not pdata.SPD_WAD.exists():self.skipTest('personal-data build-v2 not present')
        title=pdata.spd_title()
        self.assertEqual(title.tmd.title_id.lower(),'000100084843434a');self.assertEqual(title.tmd.ios_tid.lower(),'000000010000003a')
        from kwce import personal_data_format as fmt
        f=fmt.fields(pdata.fictional_plain());self.assertEqual(f['last_name'],'홍');self.assertTrue(f['email_address'].endswith('@example.com'))
    def test_profile_lock(self):
        p=ROOT/'configs/photoprints-runtime.lock.json'
        if not p.exists():self.skipTest('test bed not prepared')
        lock=json.loads(p.read_text())
        if 'personal_data' not in lock:self.skipTest('SPD not installed in the profile')
        rec=lock['personal_data'];self.assertEqual(rec['spd_wad_sha256'],'db968ff1e21d54c12f396d99270f7a4249076fd9ea56b2fbe4f4b606fc06ffcb')
        if rec.get('pd_installed'):self.assertEqual(rec['device_id'],'Dolphin public DEFAULT_DEVICE_ID');self.assertTrue(rec['fictional'])


class GlyphInk(unittest.TestCase):
    """Lead's v8/v9 review: Hangul strokes clipped (디->ㄷ, 터->ㅌ, 만->민 ...).
    nw4r draws a glyph from sheet pixels [cellX+1, cellX+1+glyphWidth) x
    [cellY+1, cellY+1+cellHeight); ink anywhere else in the cell is never shown."""
    REPORTED='디지털데이터만드시겠습니까처음부터클럽닌텐도명함번호만들려면'
    @classmethod
    def setUpClass(cls):
        cls.rodan=ChannelArchive(_title().get_content_by_index(2)).get('font_rodan_28.brfna')
    def test_original_font_follows_the_window(self):
        from kwce.photoprints_font import glyph_ink_report
        rep=glyph_ink_report(self.rodan,range(0,7*40))
        self.assertEqual(rep['clipped'],[]);self.assertEqual(rep['margin_ink_sheets'],[])
    def test_legacy_placement_clipped_the_reported_glyphs(self):
        from kwce.photoprints_font import append_hangul_rfna,glyph_ink_report,find_glyph
        font,rec=append_hangul_rfna(self.rodan,self.REPORTED)
        rep=glyph_ink_report(font,range(rec['first_appended_glyph'] if 'first_appended_glyph' in rec else rec['sheets_before']*7,rec['sheets_before']*7+rec['added_glyphs']))
        for ch in '디터만니번명':self.assertIn(find_glyph(font,ord(ch)),rep['clipped'],ch)
    def test_exact_placement_draws_every_glyph_fully(self):
        from kwce.photoprints_font import append_hangul_rfna,glyph_ink_report
        font,rec=append_hangul_rfna(self.rodan,self.REPORTED+'가힣각닭',exact=True)
        rep=glyph_ink_report(font,range(rec['first_appended_glyph'],rec['first_appended_glyph']+rec['added_glyphs']))
        self.assertTrue(rep['ok'],{k:v for k,v in rep.items() if isinstance(v,list) and v})
        self.assertEqual(rep['checked'],len(set(self.REPORTED+'가힣각닭')))
    def test_every_appended_glyph_in_the_v10_build(self):
        from kwce.photoprints_font import glyph_ink_report,check_rfna
        p=ROOT/'workspace/channels/photoprints/build-v10/photoprints-ko-local-test.wad'
        if not p.exists():self.skipTest('build-v10 not present')
        t=load_library().title.Title();t.load_wad(p.read_bytes())
        font=ChannelArchive(t.get_content_by_index(2)).get('font_rodan_28.brfna');check_rfna(font)
        m=json.loads(p.with_name('build-manifest.json').read_text(encoding='utf-8'))['font']
        first=m['first_appended_glyph'];rep=glyph_ink_report(font,range(first,first+m['added_glyphs']))
        self.assertEqual(rep['checked'],2350);self.assertTrue(rep['ok'],{k:len(v) for k,v in rep.items() if isinstance(v,list) and v})


class PriceFormat(unittest.TestCase):
    def test_v10_price_drops_server_unit(self):
        v10=json.loads((ROOT/'configs/photoprints-messages-v10-ko.json').read_text(encoding='utf-8'))['messages']
        v8=json.loads((ROOT/'configs/photoprints-messages-v8-ko.json').read_text(encoding='utf-8'))['messages']
        self.assertEqual(v10['%ls円%ls'],'%ls엔')
        self.assertEqual({k for k in v8 if v8[k]!=v10[k]},{'%ls円%ls'})
        self.assertIn('priceUnit',fx.get_item_information().decode())   # the feed mirrors WiiLink's '$'
    def test_format_arguments_are_a_prefix(self):
        import re
        pat=r'%[-+ #0-9.*]*(?:ls|l?[dsuxXf])'
        v10=json.loads((ROOT/'configs/photoprints-messages-v10-ko.json').read_text(encoding='utf-8'))['messages']
        for jp,ko in v10.items():
            a,b=re.findall(pat,jp),re.findall(pat,ko);self.assertEqual(b,a[:len(b)],ko)


class Banner(unittest.TestCase):
    def test_imet_name_and_md5(self):
        import hashlib
        b,rec=korean_banner_name(_title().get_content_by_index(0))
        self.assertEqual(b[0x80:0x84],b'IMET')
        self.assertEqual(b[0x40+0x5c:0x40+0x5c+len(DISPLAY_NAME.encode('utf-16-be'))],DISPLAY_NAME.encode('utf-16-be'))
        chk=bytearray(b);chk[0x630:0x640]=bytes(16)
        self.assertEqual(b[0x630:0x640],hashlib.md5(bytes(chk[0x40:0x640])).digest())


class Fixtures(unittest.TestCase):
    def test_read_only_only(self):
        m=fx.manifest()
        self.assertTrue(m['read_only'] and m['local_only'] and m['synthetic'])
        self.assertFalse(m['accepts_uploads'] or m['accepts_orders'])
        self.assertEqual({o['operation'] for o in m['operations']},set(fx.READ_ONLY_OPERATIONS))
        for bad in ('getOrderID','getImageID','fixOrderInformation','noticeOrderFinish'):
            self.assertIn(bad,m['refused_operations'])
        body=fx.get_item_information()
        self.assertTrue(body.startswith(b'statusCode=1000\n') and b'itemName_1=' in body)


class Configs(unittest.TestCase):
    def test_messages_and_exec_present(self):
        msg=json.loads((ROOT/'configs/photoprints-messages-v1-ko.json').read_text(encoding='utf-8'))
        self.assertGreater(msg['count'],300)
        exe=json.loads((ROOT/'configs/photoprints-executable-v1-ko.json').read_text(encoding='utf-8'))
        self.assertTrue(all(r['fits'] for r in exe['rows']))
    def test_brlyt_keys_match_wad(self):
        msg=json.loads((ROOT/'configs/photoprints-messages-v1-ko.json').read_text(encoding='utf-8'))['messages']
        c2=ChannelArchive(_title().get_content_by_index(2))
        from libWiiPy.archive import decompress_lz77
        present=set()
        for n in ['layout.arc.LZ','cursor.arc.LZ']:
            a=ChannelArchive(decompress_lz77(c2.get(n)))
            for f in a.files:
                if f.endswith('.brlyt'):
                    for s in layout_sections(a.get(f)):
                        tb=textbox(s)
                        if tb:present.add(tb[1])
        matched=[k for k in msg if k in present]
        self.assertGreater(len(matched),350)


class BuildArtifact(unittest.TestCase):
    def test_manifest_invariants(self):
        any_found=False
        for rev in (1,2,3,6,7,8,9,10):
            p=ROOT/f'workspace/channels/photoprints/build-v{rev}/build-manifest.json'
            if not p.exists():continue
            any_found=True;m=json.loads(p.read_text(encoding='utf-8'))
            self.assertEqual(m['changed_contents'],[0,1,2,3])
            self.assertTrue(m['local_only']);self.assertFalse(m['full_localization_complete']);self.assertFalse(m['hardware_success_verified'])
            if rev>=6:
                self.assertTrue(m['font']['glgr_preserved']);self.assertEqual(len(m['executable']['kept_japanese_error_font']),5)
            if rev>=8:
                self.assertIn(m['text_fit']['table'],('photoprints-messages-v8-ko.json','photoprints-messages-v10-ko.json'));self.assertGreaterEqual(m['text_fit']['min_scale'],0.8)
            if rev>=10:
                self.assertEqual(m['font']['ink_check']['clipped'],0);self.assertEqual(m['font']['ink_check']['glyphs'],2350)
        if not any_found:self.skipTest('no build present')


if __name__=='__main__':unittest.main()

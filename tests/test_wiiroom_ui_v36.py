"""Korean visual geometry/provenance regression checks without console IO."""
import json,struct,unittest
from pathlib import Path
from kwce.channels import load_library,ChannelArchive,layout_sections
from kwce.wiiroom_formats import decompress_lz11
from kwce import tpl

BASE=Path('workspace/channels/wiiroom')
@unittest.skipUnless((BASE/'build-v36/build-manifest.json').exists(),'local Room v36 required')
class RoomVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib=load_library();cls.titles=[]
        for v in (34,36,37):
            t=lib.title.Title();t.load_wad((BASE/f'build-v{v}/wiiroom-ko-local-test.wad').read_bytes());cls.titles.append(t)
        cls.before=ChannelArchive(cls.titles[0].get_content_by_index(2));cls.after=ChannelArchive(cls.titles[1].get_content_by_index(2))
    def test_native_korean_mario_kart_ui_is_used_for_both_frames_in_every_language(self):
        from PIL import Image
        cfg=json.loads(Path('configs/wiiroom-strap-kart-v1.lock.json').read_text());a=ChannelArchive(self.titles[1].get_content_by_index(13));old=ChannelArchive(self.titles[0].get_content_by_index(13))
        reference=decompress_lz11(a.get('strapImage_En_LZ.bin'))
        for i,row in enumerate(cfg['files']):
            im=tpl.decode(Path(row['path']).read_bytes(),0).resize((640,480),Image.Resampling.LANCZOS)
            encoded=tpl.encode(reference,i,im)
            self.assertEqual(encoded,reference) # exact native resample, no retyped words
        for p in a.files:
            if p.startswith('strapImage_'):self.assertEqual(decompress_lz11(a.get(p)),reference)
            else:self.assertEqual(old.get(p),a.get(p))
    def test_setting_captions_share_the_same_centre_baseline_and_font(self):
        seen=[]
        for n in ['Family_Btn','Video_Btn','Area_Btn','Agree_Btn']:
            ar=ChannelArchive(decompress_lz11(self.after.get(f'layout/Option/{n}.lex')))
            data=ar.get(next(p for p in ar.files if p.endswith('.brlyt')))
            s=next(s for s in layout_sections(data)if s[:4]==b'txt1'and s[12:28].split(b'\0')[0]==b'Text_Btn')
            seen.append((s[36:44],s[68:76],s[84:86],s[100:108]));self.assertEqual(s[84:86],bytes([4,1]))
        self.assertEqual(len(set(seen)),1)
    def test_notices_have_stable_left_anchoring_and_preserve_runtime_capacity(self):
        path='layout/Message_Inbox/Message_Update_Text.lex';old,new=(ChannelArchive(decompress_lz11(a.get(path)))for a in (self.before,self.after))
        p=next(p for p in new.files if p.endswith('.brlyt'))
        pairs=zip(layout_sections(old.get(p)),layout_sections(new.get(p)));count=0
        for a,b in pairs:
            if a[:4]!=b'txt1':continue
            self.assertEqual(a[76:84],b[76:84]);self.assertEqual(b[84:86],bytes(2));count+=1
        self.assertEqual(count,2)
    def test_title_hangul_uses_square_equal_quads_and_native_wii_texels(self):
        path='layout/Title/Title_Scene.lex';old,new=(ChannelArchive(decompress_lz11(a.get(path)))for a in (self.before,self.after))
        for p in old.files:
            if p.endswith(('Title_Logo_W.tpl','Title_Logo_I.tpl','Title_Logo_Mark.tpl')):self.assertEqual(old.get(p),new.get(p))
        data=new.get(next(p for p in new.files if p.endswith('.brlyt')));panes={s[12:28].split(b'\0')[0]:s for s in layout_sections(data)if s[:4]==b'pic1'}
        for name in [b'Pic_Logo_No',b'Pic_Logo_Ma']:
            s=panes[name];self.assertEqual(struct.unpack_from('>ff',s,68),(64.,64.));self.assertEqual(struct.unpack_from('>f',s,40)[0],-2.)
    def test_hardware_pair_preserves_the_same_ui_and_boot_code(self):
        emu,hw=self.titles[1:]
        for i in range(16):
            if i!=1:self.assertEqual(emu.get_content_by_index(i),hw.get_content_by_index(i))
        a,b=(decompress_lz11(t.get_content_by_index(1))for t in (emu,hw))
        old=b'http://prod.wiilink24.com/conf/first.bin';new=b'http://127.0.0.2/conf/first.bin'
        self.assertNotIn(new,b);self.assertEqual(a,b.replace(old,new+bytes(len(old)-len(new))))
    def test_visual_update_keeps_boot_home_fonts_and_other_content_identical(self):
        before,after=self.titles[:2]
        changed={i for i in range(16)if before.get_content_by_index(i)!=after.get_content_by_index(i)}
        self.assertEqual(changed,{0,2,13}) # banner, UI archive, original Korean strap

class KoreanSuffixTests(unittest.TestCase):
    def test_both_letters_keep_a_common_ink_height_without_touching_texture_edges(self):
        from kwce.wiiroom_wordmark_v36 import letter_mask
        boxes=[letter_mask(c,(256,256)).getbbox()for c in ('의','방')]
        for x0,y0,x1,y1 in boxes:self.assertTrue(2<x0<x1<254 and 2<y0<y1<254)
        self.assertLess(abs((boxes[0][3]-boxes[0][1])-(boxes[1][3]-boxes[1][1])),10)
if __name__=='__main__':unittest.main()

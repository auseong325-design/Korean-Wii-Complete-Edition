"""Wii Room v58/v59: geometric Hangul wordmark, weather board and RC6 labels (no console IO)."""
import json,struct,unittest
from pathlib import Path
from kwce.channels import load_library,ChannelArchive,layout_sections
from kwce.wiiroom_formats import decompress_lz11
from kwce import tpl

BASE=Path('workspace/channels/wiiroom')

class GeometricGlyphTests(unittest.TestCase):
    def test_both_syllables_fill_the_requested_height_and_are_deterministic(self):
        from kwce.wiiroom_wordmark_v58 import glyph_mask,WIDTH
        for c in ('의','방'):
            h=200;w=WIDTH[c]*h;m=glyph_mask(c,(w+40,h+40),(20,20,20+w,20+h),(round(w)+40,h+40))
            x0,y0,x1,y1=m.point(lambda v:255 if v>=128 else 0).getbbox()
            self.assertLessEqual(abs(y0-20),2);self.assertLessEqual(abs(y1-(20+h)),2)
            self.assertLessEqual(abs(x0-20),2);self.assertLessEqual(abs(x1-(20+w)),3)
            self.assertEqual(m.tobytes(),glyph_mask(c,(w+40,h+40),(20,20,20+w,20+h),(round(w)+40,h+40)).tobytes())

@unittest.skipUnless((BASE/'build-v58/build-manifest.json').exists()and(BASE/'build-v59/build-manifest.json').exists(),'local Room v58/v59 required')
class RoomV58Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib=load_library();cls.t={}
        for v in (56,57,58,59):
            t=lib.title.Title();t.load_wad((BASE/f'build-v{v}/wiiroom-ko-local-test.wad').read_bytes());cls.t[v]=t
    def arc(self,v,name):
        from libWiiPy.archive import decompress_lz77
        return ChannelArchive(decompress_lz77(ChannelArchive(self.t[v].get_content_by_index(0)[0x640:]).get(name)[32:]))
    def test_boot_code_is_unchanged_from_the_previous_pair(self):
        self.assertEqual(self.t[58].get_content_by_index(1),self.t[57].get_content_by_index(1))
        self.assertEqual(self.t[59].get_content_by_index(1),self.t[56].get_content_by_index(1))
        for i in range(16):
            if i!=1:self.assertEqual(self.t[58].get_content_by_index(i),self.t[59].get_content_by_index(i))
        self.assertEqual({i for i in range(16)if self.t[58].get_content_by_index(i)!=self.t[57].get_content_by_index(i)},{0,2})
    def test_hangul_shares_the_w_height_letter_gap_and_the_run_is_centred(self):
        from kwce.wiiroom_wordmark_v58 import _pane,_ink,INK,PANES,MARGIN,GAP
        for kind,name in (('banner','meta/banner.bin'),('icon','meta/icon.bin')):
            ar=self.arc(58,name);n=PANES[kind];m=MARGIN[kind]
            W=_ink(_pane(ar,n[0]),INK[kind]['W']);i1,i2=(_ink(_pane(ar,p),INK[kind]['i'])for p in n[1:3])
            no,ma=(_pane(ar,p)for p in n[3:]);gap=GAP*(i2[0]-i1[1])
            self.assertAlmostEqual(no[0]+m-i2[1],gap,places=3);self.assertAlmostEqual(ma[0]-(no[0]+no[2]),gap-2*m,places=3)
            self.assertAlmostEqual(no[3]-2*m,1.016*(W[3]-W[2]),places=3);self.assertAlmostEqual(no[1]+no[3]/2,(W[2]+W[3])/2,places=3)
            self.assertAlmostEqual(W[0]+(ma[0]+ma[2]-m),0.,places=2)
    def test_native_wii_textures_are_untouched(self):
        for name,keep in (('meta/banner.bin',('W.tpl','Rect.tpl','Dot.tpl','TM.tpl')),('meta/icon.bin',('Icon_Logo_W.tpl','Icon_Logo_I.tpl'))):
            a,b=self.arc(57,name),self.arc(58,name)
            for p in a.files:
                if p.rsplit('/',1)[-1]in keep:self.assertEqual(a.get(p),b.get(p))
        a,b=(ChannelArchive(decompress_lz11(ChannelArchive(self.t[v].get_content_by_index(2)).get('layout/Title/Title_Scene.lex')))for v in (57,58))
        for p in a.files:
            if p.endswith(('Title_Logo_W.tpl','Title_Logo_I.tpl','Title_Logo_Mark.tpl')):self.assertEqual(a.get(p),b.get(p))
    def test_title_table_and_wordmark_are_centred_on_screen(self):
        from kwce.wiiroom_wordmark_v58 import _pane,_pan_x,_anim_last,TITLE_MARK
        ar=ChannelArchive(decompress_lz11(ChannelArchive(self.t[58].get_content_by_index(2)).get('layout/Title/Title_Scene.lex')))
        mark_x=_anim_last(ar,TITLE_MARK[0],0);left=mark_x-_pane(ar,TITLE_MARK[0])[2]/2
        ma=_pane(ar,'Pic_Logo_Ma');right=ma[0]+ma[2]-2.
        self.assertAlmostEqual(_pan_x(ar,'Loc_Logo')+(left+right)/2,0.,places=2)
    def test_weather_board_is_korean_in_every_mip_and_keeps_its_colours(self):
        from libWiiPy.archive import decompress_lz77
        from kwce.wiiroom_weather_v58 import PATH,_tex0,_fake,BAND,BODY
        old,new=(decompress_lz77(ChannelArchive(self.t[v].get_content_by_index(2)).get(PATH))for v in (57,58))
        self.assertEqual(len(old),len(new));at,w,h,fmt,levels,size=_tex0(new);off=at+64
        n=sum(tpl.data_size(fmt,max(1,w>>k),max(1,h>>k))for k in range(levels))
        self.assertEqual(old[:off],new[:off]);self.assertEqual(old[off+n:],new[off+n:])
        pos=off
        for k in range(levels):
            lw,lh=max(1,w>>k),max(1,h>>k);size_k=tpl.data_size(fmt,lw,lh)
            self.assertNotEqual(old[pos:pos+size_k],new[pos:pos+size_k]);pos+=size_k
        image=tpl.decode(_fake(w,h,fmt,new[off:off+tpl.data_size(fmt,w,h)]),0)
        self.assertEqual(image.getpixel((2,2)),BAND);self.assertEqual(image.getpixel((2,77)),BODY)
    def test_only_the_three_reviewed_labels_change(self):
        from libWiiPy.archive import decompress_lz77
        from kwce.votes_resources import bmg_sections,bmg_message
        def msgs(v):
            b=decompress_lz77(ChannelArchive(self.t[v].get_content_by_index(2)).get('msg/message.lex'));s=bmg_sections(b)
            inf=next(x for x in s if x[:4]==b'INF1');dat=next(x for x in s if x[:4]==b'DAT1');st=int.from_bytes(inf[10:12],'big')
            return [bmg_message(dat,8+int.from_bytes(inf[16+i*st:20+i*st],'big')).decode('utf-16-be')for i in range(int.from_bytes(inf[8:10],'big'))]
        old,new=msgs(57),msgs(58);cfg=json.loads(Path('configs/wiiroom-messages-v58-ko.json').read_text(encoding='utf-8'))['messages']
        self.assertEqual({str(i)for i in range(len(old))if old[i]!=new[i]},set(cfg))
        for k,v in cfg.items():self.assertEqual(new[int(k)],v)

if __name__=='__main__':unittest.main()

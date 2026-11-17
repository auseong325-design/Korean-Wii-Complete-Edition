"""Regression coverage for the guide's lost grayscale edges and separate prompt."""
import io,re,unittest
from pathlib import Path
from kwce.channels import ChannelArchive,load_library,layout_sections
from kwce.wiiroom_manual_v40 import localized_network_csv,PROMPT,smooth_mask
from kwce import tpl

class CoverageTests(unittest.TestCase):
    def test_intensity_texture_keeps_gray_edges_instead_of_only_alpha(self):
        load_library();from PIL import Image
        mask=smooth_mask((430,40),'Wii 리모컨 사용 방법',(1,1,429,39))
        # This is the failing conversion: straight RGB is white even where
        # the alpha contains partial coverage, so I8 encodes a hard edge.
        old=Image.new('RGBA',mask.size);old.paste((255,255,255,255),(0,0),mask)
        self.assertEqual(sum(old.getchannel('R').histogram()[1:255]),0)
        self.assertGreater(sum(mask.histogram()[1:255]),1000)
    def test_prompt_rejects_another_csv_instead_of_silently_changing_its_abi(self):
        with self.assertRaises(ValueError):localized_network_csv(b'\xfe\xff'+('"sample"\n'*7).encode('utf-16-be'))

@unittest.skipUnless(Path('workspace/channels/wiiroom/build-v40/build-manifest.json').exists(),'local Room guide build required')
class GuideBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib=load_library();cls.titles=[]
        for v in [36,40,41]:
            t=lib.title.Title();t.load_wad(Path(f'workspace/channels/wiiroom/build-v{v}/wiiroom-ko-local-test.wad').read_bytes());cls.titles.append(t)
    def test_all_seven_language_prompts_are_korean_and_preserve_columns(self):
        a=ChannelArchive(self.titles[1].get_content_by_index(2));b=a.get('hbm/HomeButton3/network.csv')
        self.assertTrue(b.startswith(b'\xfe\xff'));cells=re.findall(r'"([^"]*)"',b[2:].decode('utf-16-be'))
        self.assertEqual(cells,[PROMPT]*7)
    def test_chrome_keeps_geometry_and_true_gray_edges_in_all_twenty_one_textures(self):
        from libWiiPy.archive import decompress_lz77
        from kwce.wiiroom_manual_v40 import CHROME
        old,new=(ChannelArchive(t.get_content_by_index(4))for t in self.titles[:2]);count=0
        self.assertEqual(set(old.files),set(new.files))
        for name in old.files:
            a,b=(ChannelArchive(decompress_lz77(ar.get(name)))for ar in (old,new))
            for p in a.files:
                if p.rsplit('/',1)[-1]not in CHROME:self.assertEqual(a.get(p),b.get(p));continue
                raw=b.get(p);r=tpl.texture_records(raw)[0];self.assertEqual(tpl.texture_records(a.get(p)),[r]);count+=1
                h=tpl.decode(raw,0).getchannel('R').histogram();self.assertGreater(sum(n>0 for n in h[1:255]),32)
                self.assertEqual(a.get(p)[:r['offset']],raw[:r['offset']])
        self.assertEqual(count,21)
    def test_page_stays_the_original_size_and_hardware_uses_identical_manual_assets(self):
        from PIL import Image
        a,b=self.titles[1:]
        for i in range(16):
            if i!=1:self.assertEqual(a.get_content_by_index(i),b.get_content_by_index(i))
        page=ChannelArchive(a.get_content_by_index(2)).get('hbm/manual.jpg')
        with Image.open(io.BytesIO(page))as im:self.assertEqual(im.size,(554,256));self.assertFalse(im.info.get('progressive'))
    def test_guide_update_preserves_boot_home_fonts_banner_and_safety_art(self):
        a,b=self.titles[:2];changed={i for i in range(16)if a.get_content_by_index(i)!=b.get_content_by_index(i)}
        self.assertEqual(changed,{2,4})
        old,new=(ChannelArchive(t.get_content_by_index(2))for t in (a,b))
        self.assertEqual({p for p in old.files if old.get(p)!=new.get(p)},{'hbm/manual.jpg','hbm/HomeButton3/network.csv'})
if __name__=='__main__':unittest.main()

"""The details prompt must be renderable by the actual HOME subset font."""
import struct,unittest
from pathlib import Path
from kwce.channels import ChannelArchive,load_library
from kwce.channel_font import font_data
from kwce.wiiroom_manual_v40 import PROMPT

BASE=Path('workspace/channels/wiiroom')
@unittest.skipUnless((BASE/'build-v42/build-manifest.json').exists(),'local Room v42 required')
class PromptFontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib=load_library();cls.titles=[]
        for v in (40,42,43):
            t=lib.title.Title();t.load_wad((BASE/f'build-v{v}/wiiroom-ko-local-test.wad').read_bytes());cls.titles.append(t)
    def pairs(self):
        from libWiiPy.archive import decompress_lz77
        a,b=(ChannelArchive(t.get_content_by_index(3))for t in self.titles[:2])
        for name in a.files:
            if 'LZ77_homeBtn' in name:yield ChannelArchive(decompress_lz77(a.get(name))),ChannelArchive(decompress_lz77(b.get(name)))
            else:self.assertEqual(a.get(name),b.get(name))
    def test_font_covers_every_prompt_character_in_all_fourteen_archives(self):
        count=0
        for a,b in self.pairs():
            p=next(p for p in b.files if p.endswith('.brfnt'));_,old,_=font_data(a.get(p));_,new,_=font_data(b.get(p))
            needed={ord(c)for c in PROMPT if ord(c)>=32}
            self.assertFalse(needed<=old.keys());self.assertTrue(needed<=new.keys());self.assertEqual(len(new)-len(old),12);count+=1
        self.assertEqual(count,14)
    def test_existing_glyphs_and_all_nonfont_resources_are_byte_identical(self):
        for a,b in self.pairs():
            for p in a.files:
                if not p.endswith('.brfnt'):self.assertEqual(a.get(p),b.get(p));continue
                x,y=a.get(p),b.get(p);bl1,m1,w1=font_data(x);bl2,m2,w2=font_data(y)
                for c,g in m1.items():self.assertEqual(m2[c],g);self.assertEqual(w2[g],w1[g])
                tg1,tg2=bl1[b'TGLP'][1],bl2[b'TGLP'][1];self.assertEqual(tg1[8:16],tg2[8:16]);self.assertEqual(bl1[b'FINF'][1][8:16],bl2[b'FINF'][1][8:16])
                n=struct.unpack_from('>I',tg1,12)[0]*struct.unpack_from('>H',tg1,16)[0];off1=struct.unpack_from('>I',tg1,28)[0];off2=struct.unpack_from('>I',tg2,28)[0]
                self.assertEqual(x[off1:off1+n],y[off2:off2+n])
    def test_added_glyph_pixels_are_copied_from_native_wbf2_without_resampling(self):
        from kwce.channel_korean_font import korean_shared_fonts
        from kwce.wbf_text import WiiFontRenderer
        from kwce.korean_font_narrow import _untile_i4
        from PIL import Image
        native,_=korean_shared_fonts();renderer=WiiFontRenderer(ChannelArchive(native).get('wbf2.brfna'))
        a,b=next(self.pairs());p=next(p for p in b.files if p.endswith('.brfnt'));_,old,_=font_data(a.get(p));raw=b.get(p);blocks,mapping,widths=font_data(raw);tg=blocks[b'TGLP'][1]
        cw,ch=tg[8:10];sheet_size=struct.unpack_from('>I',tg,12)[0];_,_,cols,rows,sw,sh=struct.unpack_from('>6H',tg,16);pointer=struct.unpack_from('>I',tg,28)[0]
        for c in set(mapping)-set(old):
            g=mapping[c];page,item=divmod(g,cols*rows);off=pointer+page*sheet_size
            image=Image.frombytes('L',(sw,sh),bytes(_untile_i4(raw[off:off+sheet_size],sw,sh)))
            cell,left,gw,advance=renderer.glyph(c);x=(item%cols)*(cw+1);y=(item//cols)*(ch+1)
            self.assertEqual(image.crop((x,y,x+gw,y+cell.height)).tobytes(),cell.tobytes());self.assertEqual(widths[g],bytes([left&255,gw,advance]))
    def test_font_fix_changes_only_home_content_and_hardware_has_the_same_resources(self):
        old,new,hw=self.titles
        self.assertEqual({i for i in range(16)if old.get_content_by_index(i)!=new.get_content_by_index(i)},{3})
        for i in range(16):
            if i!=1:self.assertEqual(new.get_content_by_index(i),hw.get_content_by_index(i))

if __name__=='__main__':unittest.main()

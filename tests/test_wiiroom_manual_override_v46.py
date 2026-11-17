"""NWM's higher-priority font must cover the prompt, including its Japanese slot."""
import re,unittest
from pathlib import Path
from kwce.channels import load_library,ChannelArchive
from kwce.channel_font import font_data
from kwce.wiiroom_manual_v40 import PROMPT

BASE=Path('workspace/channels/wiiroom')
@unittest.skipUnless((BASE/'build-v46/build-manifest.json').exists(),'local Room v46 required')
class NetworkOverrideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib=load_library();cls.titles=[]
        for v in (42,46,47):
            t=lib.title.Title();t.load_wad((BASE/f'build-v{v}/wiiroom-ko-local-test.wad').read_bytes());cls.titles.append(t)
    def test_effective_font_covers_the_prompt_after_all_language_overrides(self):
        from libWiiPy.archive import decompress_lz77
        home=ChannelArchive(self.titles[1].get_content_by_index(3));home=ChannelArchive(decompress_lz77(home.get('HomeButton3/LZ77_homeBtn.arc')))
        path='arc/font/RevoIpl_UtrilloProGrecoStd_M_32_I4.brfnt';fallback=home.get(path);needed={ord(c)for c in PROMPT if ord(c)>=32};a=ChannelArchive(self.titles[1].get_content_by_index(4));overrides=0
        for name in a.files:
            language=ChannelArchive(decompress_lz77(a.get(name)));font=language.get(path)if path in language.files else fallback
            _,mapping,_=font_data(font);self.assertTrue(needed<=mapping.keys())
            if path in language.files:self.assertEqual(font,fallback);overrides+=1
        self.assertEqual(overrides,4)
    def test_only_the_four_shadow_fonts_change_and_original_network_csv_abi_is_restored(self):
        from libWiiPy.archive import decompress_lz77
        old,new=self.titles[:2];self.assertEqual({i for i in range(16)if old.get_content_by_index(i)!=new.get_content_by_index(i)},{4})
        a,b=(ChannelArchive(t.get_content_by_index(4))for t in (old,new));changed=0
        for name in a.files:
            x,y=(ChannelArchive(decompress_lz77(ar.get(name)))for ar in (a,b));delta={p for p in x.files if x.get(p)!=y.get(p)}
            if delta:self.assertTrue(all(p.endswith('.brfnt')for p in delta));changed+=1
        self.assertEqual(changed,4)
        csv=ChannelArchive(new.get_content_by_index(2)).get('hbm/HomeButton3/network.csv')
        self.assertEqual(re.findall(r'"([^"]*)"',csv[2:].decode('utf-16-be')),[PROMPT]*7)
    def test_hardware_pair_and_non_ui_content_are_preserved(self):
        new,hw=self.titles[1:]
        for i in range(16):
            if i!=1:self.assertEqual(new.get_content_by_index(i),hw.get_content_by_index(i))
        lib=load_library();baseline=lib.title.Title();baseline.load_wad((BASE/'build-v36/wiiroom-ko-local-test.wad').read_bytes())
        self.assertEqual({i for i in range(16)if baseline.get_content_by_index(i)!=new.get_content_by_index(i)},{2,3,4})

if __name__=='__main__':unittest.main()

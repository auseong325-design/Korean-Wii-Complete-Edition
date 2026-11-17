"""Korean HOME indexes the network confirmation using the ten-language table."""
import re,unittest
from pathlib import Path
from kwce.channels import load_library,ChannelArchive
from kwce.wiiroom_manual_v40 import PROMPT

BASE=Path('workspace/channels/wiiroom')
@unittest.skipUnless((BASE/'build-v44/build-manifest.json').exists(),'local Room v44 required')
class NetworkSlotsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib=load_library();cls.titles=[]
        for v in (42,44,45):
            t=lib.title.Title();t.load_wad((BASE/f'build-v{v}/wiiroom-ko-local-test.wad').read_bytes());cls.titles.append(t)
    def test_network_prompt_has_the_korean_slot_and_the_same_language_count_as_home(self):
        a=ChannelArchive(self.titles[1].get_content_by_index(2));cells=lambda p:re.findall(r'"([^"]*)"',a.get(p)[2:].decode('utf-16-be'))
        network=cells('hbm/HomeButton3/network.csv');self.assertEqual(network,[PROMPT]*10)
        self.assertEqual(len(cells('hbm/HomeButton3/home.csv')),4*len(network));self.assertEqual(network[9],PROMPT)
    def test_language_slot_fix_changes_only_network_csv_and_hardware_has_the_same_assets(self):
        old,new,hw=self.titles;self.assertEqual({i for i in range(16)if old.get_content_by_index(i)!=new.get_content_by_index(i)},{2})
        a,b=(ChannelArchive(t.get_content_by_index(2))for t in (old,new));self.assertEqual({p for p in a.files if a.get(p)!=b.get(p)},{'hbm/HomeButton3/network.csv'})
        for i in range(16):
            if i!=1:self.assertEqual(new.get_content_by_index(i),hw.get_content_by_index(i))

if __name__=='__main__':unittest.main()

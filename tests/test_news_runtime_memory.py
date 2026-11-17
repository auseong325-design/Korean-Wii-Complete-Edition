import unittest
from pathlib import Path
from kwce.channels import load_library,ChannelArchive
from kwce.channel_font import font_data

@unittest.skipUnless(Path('workspace/channels/news/build-v15/news-ko-personal.wad').exists(),'local News candidate required')
class NewsRuntimeMemoryTests(unittest.TestCase):
    def test_runtime_fonts_keep_required_korean_and_reduce_resident_size(self):
        lib=load_library()
        from libWiiPy.archive import decompress_lz77
        titles=[];totals=[]
        for revision in [14,15]:
            title=lib.title.Title();title.load_wad(Path(f'workspace/channels/news/build-v{revision}/news-ko-personal.wad').read_bytes());titles.append(title)
            archive=ChannelArchive(title.get_content_by_index(9));total=0
            for name in archive.files:
                if not name.endswith('.brfnt.LZ'):continue
                font=decompress_lz77(archive.get(name));total+=len(font)
                if revision==15:
                    _,mapping,_=font_data(font)
                    required='서울부산' if 'city' in name else '년월일요일오전후' if 'date' in name else '오전후'
                    self.assertTrue(all(ord(c)in mapping for c in required),name)
            totals.append(total)
        self.assertGreater(totals[0]-totals[1],600000)
        self.assertEqual([i for i in range(12)if titles[0].get_content_by_index(i)!=titles[1].get_content_by_index(i)],[9])

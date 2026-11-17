import importlib.util,json,struct,unittest
from pathlib import Path
from kwce.channels import ChannelArchive,load_library
from kwce.wiiroom_schema import problems

class RoomServiceTests(unittest.TestCase):
    @unittest.skipUnless(Path('workspace/channels/wiiroom/originals/wiiroom-english-wiilink-archive.wad').exists(),'private Room source required')
    def test_banner_masks_match_material_polarity_and_keep_native_wii(self):
        from kwce.wiiroom_banner import korean_banner
        from kwce.tpl import decode
        lib=load_library();from libWiiPy.archive import decompress_lz77
        title=lib.title.Title();title.load_wad(Path('workspace/channels/wiiroom/originals/wiiroom-english-wiilink-archive.wad').read_bytes())
        source=title.get_content_by_index(0);changed,_=korean_banner(source,native_wordmark=True)
        before=ChannelArchive(source[0x640:]);after=ChannelArchive(changed[0x640:])
        for archive_name,inverted in [('meta/banner.bin',True),('meta/icon.bin',False)]:
            old=ChannelArchive(decompress_lz77(before.get(archive_name)[32:]));new=ChannelArchive(decompress_lz77(after.get(archive_name)[32:]))
            for name in old.files:
                if name.endswith(('/No.tpl','/Ma.tpl','/Icon_Logo_No.tpl','/Icon_Logo_Ma.tpl')):
                    image=decode(new.get(name),0)
                    self.assertEqual(image.getpixel((0,0))[0],255 if inverted else 0)
                    low,high=image.getchannel('R').getextrema();self.assertEqual((low,high),(0,255))
                else:self.assertEqual(old.get(name),new.get(name),name)

    @unittest.skipUnless(Path('workspace/channels/wiiroom/build-v16/build-manifest.json').exists(),'private Room base required')
    def test_controller_translation_preserves_raw_lz10_envelope(self):
        from kwce.wiiroom_manual import korean_manual
        lib=load_library();title=lib.title.Title();title.load_wad(Path('workspace/channels/wiiroom/build-v16/wiiroom-ko-local-test.wad').read_bytes())
        old=ChannelArchive(title.get_content_by_index(4));_,changed,_=korean_manual(title.get_content_by_index(2),title.get_content_by_index(4));changed=ChannelArchive(changed)
        for name in old.files:self.assertEqual(old.get(name)[:1],changed.get(name)[:1],name)
    @unittest.skipUnless(Path('workspace/channels/wiiroom/build-v16/build-manifest.json').exists(),'private Room build required')
    def test_runtime_home_preserves_ten_column_abi_and_has_korean_confirmation(self):
        import re
        lib=load_library();title=lib.title.Title();title.load_wad(Path('workspace/channels/wiiroom/build-v16/wiiroom-ko-local-test.wad').read_bytes())
        archive=ChannelArchive(title.get_content_by_index(2))
        for name in ['home.csv','home_nosave.csv']:
            text=archive.get('hbm/HomeButton3/'+name)[2:].decode('utf-16-be');cells=re.findall(r'"([^"]*)"',text)
            self.assertEqual(len(cells),40)
            self.assertTrue(all('Wii 메뉴로 돌아가시겠습니까?'in cell for cell in cells[20:30]))
            self.assertTrue(all('리셋하시겠습니까?'in cell for cell in cells[30:40]))
            self.assertEqual('저장하지 않은'in cells[21],name=='home.csv')

    def test_signed_popularity_bounds(self):
        schema=dict(children=[dict(name='pop',type=3,required=True,min=0x80000000,max=0x7fffffff)])
        for value in [0,-1,-2147483648,2147483647]:self.assertEqual(problems(f'<X><pop>{value}</pop></X>',schema),[])
        for value in [-2147483649,2147483648,'--1']:
            self.assertTrue(problems(f'<X><pop>{value}</pop></X>',schema))

    def test_fixture_routes_resolve_with_no_commerce_submission(self):
        base=Path('workspace/sandbox/wiiroom-test-v1/local-feed')
        if not base.exists():self.skipTest('local synthetic feed required')
        routes={}
        for line in(base/'routes.tsv').read_text().splitlines():
            route,file=line.split('\t');self.assertNotIn(route,routes);routes[route]=file
            self.assertTrue((base/file).is_file(),route)
        self.assertIn('* /url1/list/category/search/10001',routes)
        self.assertIn('* /url1/movie/c4/1.img',routes)
        self.assertFalse(any(word in route for route in routes for word in ['purchase','checkout','order','upload','evaluate']))

    def test_first_run_fst_transform_changes_only_room_data_children(self):
        spec=importlib.util.spec_from_file_location('prepare_room_first',Path('scripts/prepare_wiiroom_first_run.py'))
        import sys;sys.path.insert(0,str(Path('scripts').resolve()))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        def node(name,children=0,file=False):
            data=bytearray(32);data[:len(name)]=name.encode();data[18]=int(file);struct.pack_into('>I',data,28,children);return bytes(data)
        keep=node('other',file=True)
        raw=node('/',2)+node('title',1)+node('00010001',1)+node('4843494a',1)+node('data',1)+node('save.dat',file=True)+keep
        revised,count=module.empty_title_data_fst(raw)
        self.assertEqual(count,1);self.assertTrue(revised.endswith(keep));self.assertEqual(len(raw)-len(revised),32)

    @unittest.skipUnless(Path('workspace/channels/wiiroom/build-v23/build-manifest.json').exists(),'private build required')
    def test_hardware_candidate_keeps_original_nand_implementation(self):
        from kwce.wiiroom_formats import decompress_lz11
        from kwce.wiiroom_compat import patch_resource_language
        lib=load_library();title=lib.title.Title()
        title.load_wad(Path('workspace/channels/wiiroom/originals/wiiroom-english-wiilink-archive.wad').read_bytes());original=decompress_lz11(title.get_content_by_index(1))
        title.load_wad(Path('workspace/channels/wiiroom/build-v23/wiiroom-ko-local-test.wad').read_bytes());candidate=decompress_lz11(title.get_content_by_index(1))
        self.assertEqual(candidate,patch_resource_language(original)[0])
        self.assertNotIn(b'http://127.0.0.2/conf/first.bin',candidate)

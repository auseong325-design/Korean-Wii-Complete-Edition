"""Safety boundaries and original DVD animation/branding regression checks."""
import hashlib,json,struct,unittest
from pathlib import Path
from kwce.ppc_patch import to_file

ROOT=Path(__file__).resolve().parents[1]
MENU=ROOT/'workspace/console-baseline/menu-original-43K.dol'
RESOURCE=ROOT/'workspace/experiments/gc-native-v6/menu-resource.app'

@unittest.skipUnless(MENU.exists(),'local original menu missing')
class NativeDvdMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kwce.dvd_disc_banner_hook_v11 import patch_dvd_banner_hook
        cls.original=MENU.read_bytes();cls.patched,cls.record=patch_dvd_banner_hook(cls.original)

    def test_priiloader_alone_and_gc_combined(self):
        from kwce.priiloader_hacks import hacks,apply,DVD_GROUP,DVD_MAX_WORDS
        from kwce.dvd_disc_banner_hook_v11 import patch_dvd_banner_hook
        from kwce.gc_native import patch_gc_native
        entries=hacks(self.original,dvd=True,dvd_banner=11)
        dvd=[e for e in entries if e['name']==DVD_GROUP]
        self.assertEqual(apply(self.original,dvd),self.patched)
        gc=patch_gc_native(self.original,japanese_cards=True,japanese_comments=True)[0]
        self.assertEqual(apply(self.original,entries),patch_dvd_banner_hook(gc)[0])
        self.assertTrue(all(len(p)<=DVD_MAX_WORDS for _,p in dvd[0]['pairs']))
        with self.assertRaises(ValueError):hacks(self.original,dvd=True,dvd_banner=999)

    def test_guards_cover_whole_cave_and_each_native_call(self):
        from kwce.dvd_disc_banner_hook_v11 import patch_dvd_banner_hook,CAVE,END,SITES
        for address in [CAVE,END-4,*SITES]:
            with self.subTest(address=address):
                bad=bytearray(self.original);bad[to_file(bad,address)]^=1
                with self.assertRaises(ValueError):patch_dvd_banner_hook(bytes(bad))

    def test_original_function_entries_and_matrix_calculation_untouched(self):
        # R25 detoured updateDiskState's prologue and the post-layout matrix pass.
        for address in [0x813B7A00,0x813B415C,0x81369A98,0x813B78B0]:
            at=to_file(self.original,address)
            self.assertEqual(self.patched[at:at+16],self.original[at:at+16])
        self.assertLessEqual(self.record['native_code_bytes'],self.record['native_cave_capacity'])
        self.assertFalse(self.record['pane_transform_copy'])

    def test_frozen_source_reproduces_installed_candidate(self):
        from kwce.dvd_disc_banner_hook_v11 import patch_dvd_banner_hook,SOURCE
        from kwce.gc_native import patch_gc_native
        again,record=patch_dvd_banner_hook(self.original)
        self.assertEqual(again,self.patched)
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(),record['native_source_sha256'])
        candidate=ROOT/'workspace/experiments/dvd-menu-hook-v11/menu.dol'
        self.assertEqual(candidate.read_bytes(),patch_dvd_banner_hook(patch_gc_native(self.original,japanese_cards=True,japanese_comments=True)[0])[0])

@unittest.skipUnless(RESOURCE.exists(),'local native resources missing')
class OriginalDvdArtTests(unittest.TestCase):
    def test_dvd_has_original_spin_seam_and_floor_insertion_tracks(self):
        from kwce.formats import U8,ash_decompress
        from kwce.disk_dvd_anim import _contents,_value,ASH_PATH,ANIM
        disk=U8(ash_decompress(U8(RESOURCE.read_bytes()).get(ASH_PATH)))
        data=disk.get(ANIM.format('DiskIn'));tracks={}
        for name,material,tags in _contents(data):
            for _,magic,items in tags:
                for _,target,curve,keys in items:tracks[name,magic,target]=(curve,keys)
        def value(name,tag,target,frame):
            curve,keys=tracks[name,tag,target];return _value(data,curve,keys,frame)
        self.assertEqual(value('N_DVD0',b'RLPA',1,0),74)
        self.assertEqual(value('N_DVD0',b'RLPA',1,40),-126)
        self.assertGreater(value('W_DVD',b'RLPA',6,8),0)
        self.assertEqual(value('W_DVD',b'RLPA',6,50),0)
        self.assertNotEqual(value('DVDDisk',b'RLPA',5,0),value('DVDDisk',b'RLPA',5,25))

    def test_full_left_d_survives_logo_extraction_and_r25_is_frozen(self):
        from kwce.channels import load_library,ChannelArchive
        load_library()
        from libWiiPy.archive import decompress_lz77
        from kwce.formats import U8
        from kwce import tpl
        from kwce.dvd_banner import dvd_player_content0
        lib=load_library();template=lib.title.Title()
        template.load_wad((ROOT/'workspace/channels/mii-contest/originals/mii-contest-usa-wiilink-archive.wad').read_bytes())
        for revision in [25,26]:
            data,_=dvd_player_content0(RESOURCE.read_bytes(),template.get_content_by_index(0),revision)
            installed=lib.title.Title();installed.load_wad((ROOT/f'workspace/channels/dvd-player/wad-v{revision}/dvd-player.wad').read_bytes())
            self.assertEqual(data,installed.get_content_by_index(0))
            if revision==26:
                banner=ChannelArchive(decompress_lz77(U8(data[0x640:]).get('meta/banner.bin')[32:]))
                im=tpl.decode(banner.get('arc/timg/kwce_dvd_logo.tpl'),0)
                # Original D starts at source x21, now local x13 (old mask began at24).
                self.assertTrue(any(im.getpixel((x,y))[3]>32 for x in range(13,16)for y in range(8,33)))
                self.assertFalse(any(im.getpixel((0,y))[3]for y in range(64)))

if __name__=='__main__':unittest.main()

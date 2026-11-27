import hashlib,json,shutil,struct,tempfile,unittest
from pathlib import Path
from kwce.emulator_shortcuts import plans
from kwce.u8_build import build_u8
from kwce.formats import U8

ROOT=Path(__file__).resolve().parents[1]
MENU=ROOT/'workspace/console-baseline/menu-original-43K.dol'
WIIMC=ROOT/'external/other-tools/wiimc'


class DvdLauncherTests(unittest.TestCase):
    def settings(self,**extra):return dict(schema=1,system_menu_profile='gc-native-v7-user',include_installer_emulator=False,**extra)

    def test_dvd_launchers_optional_and_hook_profile_only(self):
        catalog=dict(schema=2,channels=[])
        self.assertNotIn('04_DVD_Player_Test',plans(catalog,self.settings()))
        entries=plans(catalog,self.settings(include_dvd_test=True,dvd_menu_profile='gc-native-v8-user'))
        self.assertEqual(entries['04_DVD_Player_Test']['argv'],['scripts/launch_dvd_test.py'])
        self.assertEqual(entries['05_DVD_Disc_Channel']['argv'],['scripts/launch_dolphin.py','--profile','gc-native-v8-user','--menu'])
        integrated=plans(catalog,self.settings(include_dvd_test=True,dvd_test_profile='dvd-test-v2',dvd_menu_profile='dvd-test-v2'))
        self.assertEqual(integrated['05_DVD_Disc_Channel']['argv'],['scripts/launch_dvd_test.py','--menu'])
        forwarder=plans(catalog,self.settings(include_dvd_test=True,dvd_test_profile='dvd-test-v4',dvd_menu_profile='dvd-test-v4'))
        self.assertEqual(forwarder['04_DVD_Player_Test']['profile'],'dvd-test-v4')
        self.assertEqual(forwarder['05_DVD_Disc_Channel']['argv'],['scripts/launch_dvd_test.py','--menu'])
        with self.assertRaises(ValueError):plans(catalog,self.settings(include_dvd_test=True,dvd_test_profile='unreviewed'))
        for profile in ['gc-native-v7-user','Dolphin.exe','gc-native-v8-user --user x']:
            with self.subTest(profile=profile),self.assertRaises(ValueError):
                plans(catalog,self.settings(dvd_menu_profile=profile))


class U8BuildTests(unittest.TestCase):
    def test_roundtrip_without_dot_root(self):
        files={'arc/blyt/a.brlyt':b'RLYT','arc/timg/b.tpl':bytes(range(40)),'arc/anim/c.brlan':b'x'}
        data=build_u8(files,dot=False)
        archive=U8(data)
        for name,body in files.items():self.assertEqual(archive.get(name),body)
        # payloads are 32-byte aligned (GX reads textures in place)
        self.assertTrue(all(data.find(body)%32==0 for body in files.values() if len(body)>4))


@unittest.skipUnless(MENU.exists(),'local 43K menu DOL not present')
class DvdHackTests(unittest.TestCase):
    def test_silver_banner_hack_simulates_with_and_without_gc(self):
        from kwce.priiloader_hacks import hacks,apply,DVD_GROUP,DVD_MAX_WORDS
        from kwce.dvd_disc_banner_hook_v10 import patch_dvd_banner_hook
        from kwce.gc_native import patch_gc_native
        menu=MENU.read_bytes();entries=hacks(menu,dvd=True,dvd_banner=True)
        dvd=[e for e in entries if e['name']==DVD_GROUP]
        patched,record=patch_dvd_banner_hook(menu)
        self.assertEqual(apply(menu,dvd),patched)
        self.assertEqual(apply(menu,entries),patch_dvd_banner_hook(patch_gc_native(menu,japanese_cards=True,japanese_comments=True)[0])[0])
        self.assertLessEqual(record['cave_bytes'],0x740)
        self.assertTrue(all(len(p)<=DVD_MAX_WORDS for _,p in dvd[0]['pairs']))
        from kwce.ppc_patch import to_file
        corrupt=bytearray(menu);corrupt[to_file(menu,0x813B415C)]^=1
        with self.assertRaises(ValueError):patch_dvd_banner_hook(bytes(corrupt))

    def test_dvd_hack_matches_hook_alone_and_with_gc(self):
        from kwce.priiloader_hacks import hacks,apply,DVD_GROUP,DVD_MAX_WORDS
        from kwce.gc_native import patch_gc_native
        from kwce.dvd_disc_hook import patch_dvd_hook
        menu=MENU.read_bytes();entries=hacks(menu,dvd=True)
        dvd=[e for e in entries if e['name']==DVD_GROUP]
        self.assertEqual(len(dvd),1)
        self.assertEqual(apply(menu,dvd),patch_dvd_hook(menu)[0])
        self.assertEqual(apply(menu,entries),patch_dvd_hook(patch_gc_native(menu,japanese_cards=True,japanese_comments=True)[0])[0])
        self.assertTrue(all(len(p)<=DVD_MAX_WORDS for _,p in dvd[0]['pairs']))
        self.assertEqual(hacks(menu),entries[:-1])  # GC groups unchanged by the DVD option


@unittest.skipUnless((WIIMC/'Makefile').exists(),'WiiMC source not present')
class ForkPatchTests(unittest.TestCase):
    def test_every_revision_applies_once(self):
        from kwce import dvd_player_fork as fork
        for revision in range(1,28):
            with self.subTest(revision=revision),tempfile.TemporaryDirectory() as tmp:
                tree=Path(tmp)
                for path in {p for p,_,_ in fork.patches(revision)}|{'source/mplayer/libdvdcss/css.c'}:
                    (tree/path).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(WIIMC/path,tree/path)
                self.assertEqual(fork.apply(tree,ROOT,revision),len(fork.patches(revision)))
                text=(tree/'Makefile').read_text(encoding='utf-8',errors='replace')
                self.assertEqual('source/kwce/lyt' in text,revision>=2)
                self.assertEqual((tree/'source/kwce/kwce_home.cpp').exists(),revision>=2)


@unittest.skipUnless((ROOT/'workspace/experiments/gc-native-v7/menu-resource.app').exists(),'local menu resources missing')
class DvdResourceTests(unittest.TestCase):
    def test_native_channel_icon_limits_flags_and_group_container(self):
        from kwce.dvd_banner import dvd_player_content0
        from kwce.channels import load_library,layout_sections,ChannelArchive
        from kwce.formats import ash_decompress
        lib=load_library();t=lib.title.Title();t.load_wad((ROOT/'workspace/channels/mii-contest/originals/mii-contest-usa-wiilink-archive.wad').read_bytes())
        data,record=dvd_player_content0((ROOT/'workspace/experiments/gc-native-v6/menu-resource.app').read_bytes(),t.get_content_by_index(0),9)
        self.assertLessEqual(record['icon_bytes'],0x19000)
        self.assertLessEqual(record['banner_bytes'],0x80000)
        self.assertEqual(struct.unpack_from('>I',data,0x98)[0],0)
        from libWiiPy.archive import decompress_lz77
        compressed=U8(data[0x640:]).get('meta/icon.bin')[32:]
        icon=ChannelArchive(decompress_lz77(compressed))
        self.assertTrue(any(s[:4]==b'grp1' for s in layout_sections(icon.get('arc/blyt/icon.brlyt'))))
    def test_original_home_build_is_preserved(self):
        from kwce.dvd_home_ui import dvd_home_archive
        data,_=dvd_home_archive((ROOT/'workspace/experiments/gc-native-v6/menu-resource.app').read_bytes(),1)
        expected=json.loads((ROOT/'configs/dvd-home-ui-v1-ko.json').read_text())['archive_sha256']
        self.assertEqual(hashlib.sha256(data).hexdigest(),expected)
    def test_disc_preview_preserves_every_other_resource(self):
        from kwce.dvd_menu_preview import patch_preview
        from kwce.formats import ash_decompress
        from kwce.disk_dvd_anim import ASH_PATH,LAYOUT
        original=(ROOT/'workspace/experiments/gc-native-v7/menu-resource.app').read_bytes();before=hashlib.sha256(original).hexdigest()
        changed,record=patch_preview(original);a,b=U8(original),U8(changed)
        self.assertTrue(record['emulator_only']);self.assertFalse(record['hardware_detection'])
        self.assertEqual(before,hashlib.sha256(original).hexdigest())
        for name in a.files:
            if name!=ASH_PATH:self.assertEqual(a.get(name),b.get(name))
        ia,ib=U8(ash_decompress(a.get(ASH_PATH))),U8(ash_decompress(b.get(ASH_PATH)))
        allowed={LAYOUT,'arc/anim/my_DiskCh_a_R_Unknown.brlan','arc/anim/my_DiskCh_a_R_UnknownLoop.brlan'}
        self.assertEqual({n for n in ia.files if ia.get(n)!=ib.get(n)},allowed)

class DvdChannelEntryTests(unittest.TestCase):
    def test_entry_adapter_preserves_original_sections(self):
        from kwce.dvd_channel_boot import channel_boot,ENTRY
        source=bytearray(0x180);struct.pack_into('>I',source,0,0x100);struct.pack_into('>I',source,0x48,0x80003f00);struct.pack_into('>I',source,0x90,0x80);struct.pack_into('>I',source,0xe0,0x80003f00)
        original=bytes(source);out,record=channel_boot(original)
        self.assertEqual(original,bytes(source));self.assertEqual(out[0x100:0x180],original[0x100:])
        self.assertEqual(struct.unpack_from('>I',out,0xe0)[0],ENTRY)
        at=struct.unpack_from('>I',out,4)[0];instruction=struct.unpack_from('>I',out,at)[0]
        self.assertEqual(ENTRY+(instruction&0x03fffffc),0x80003f00)
        self.assertTrue(record['required']);self.assertEqual(channel_boot(out)[0],out)
        struct.pack_into('>I',source,0x48,ENTRY+16)
        with self.assertRaises(ValueError):channel_boot(source)

if __name__=='__main__':unittest.main()

"""Unit tests for the Photo Prints Korean Wii Menu icon/banner (build-v11, hardware-v7).

About 20 s: rebuilds content 0 from build-v10 and regenerates build-v11 and
hardware-v7 in memory. No Dolphin, no NAND/SD writes. Output checks skip when
the numbered outputs are not present.
"""
import hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from kwce.channels import load_library,ChannelArchive
from kwce.channel_texture import texture_records
from kwce.hardware import local_reference_counts
from kwce import photoprints_menu_art as art
from kwce import tpl
import build_photoprints_menu_v11 as menu_build

BASE=ROOT/'workspace/channels/photoprints'
TITLE='000100014843444a';IOS56='0000000100000038'
ORIGINAL=BASE/'originals/digicam-japan-v1024.wad'
V10=BASE/'build-v10/photoprints-ko-local-test.wad';V11=BASE/'build-v11/photoprints-ko-local-test.wad'
HW5=BASE/'hardware-v5/photoprints-ko-hardware-test.wad';HW7=BASE/'hardware-v7/photoprints-ko-hardware-test.wad'
KOREAN_NAME='디지털 카메라 프린트 채널'


def _title(path):
    t=load_library().title.Title();t.load_wad(path.read_bytes());return t


def _contents(t):
    return [t.get_content_by_index(i) for i in range(len(t.tmd.content_records))]


def _within(a,b,*ranges):
    """True when two equal-length dumps differ only inside the given byte ranges."""
    return len(a)==len(b) and all(any(lo<=i<hi for lo,hi in ranges) for i,(x,y) in enumerate(zip(a,b)) if x!=y)


def _ink(image):
    return image.getchannel('A').point(lambda v:255 if v>=128 else 0)


class MenuArt(unittest.TestCase):
    """kwce.photoprints_menu_art applied to the build-v10 banner content."""
    @classmethod
    def setUpClass(cls):
        if not V10.exists():raise unittest.SkipTest('build-v10 not present')
        cls.before=_title(V10).get_content_by_index(0)
        cls.after,cls.record=art.korean_menu_art(cls.before)

    def test_only_the_five_title_textures_change(self):
        for name,paths in (('meta/banner.bin',art.BANNER_TEXTURES),('meta/icon.bin',art.ICON_TEXTURES)):
            a,b=art.nested(self.before,name),art.nested(self.after,name)
            self.assertEqual(set(a.files),set(b.files));self.assertEqual(len(a.data),len(b.data))
            self.assertEqual({p for p in a.files if a.get(p)!=b.get(p)},set(paths))
            for p in paths:
                ra,rb=texture_records(a.get(p))[0],texture_records(b.get(p))[0]
                self.assertEqual(ra,rb)                                   # format, size, offset, palette
                self.assertEqual(len(a.get(p)),len(b.get(p)))
                self.assertEqual(a.get(p)[:ra['offset']],b.get(p)[:ra['offset']])

    def test_layouts_animations_sound_and_imet_preserved(self):
        oa,ob=ChannelArchive(self.before[0x640:]),ChannelArchive(self.after[0x640:])
        self.assertEqual(oa.get('meta/sound.bin'),ob.get('meta/sound.bin'))
        self.assertEqual(self.before[:0x640],self.after[:0x640])        # IMET sizes, Korean names and MD5
        for name in ('meta/banner.bin','meta/icon.bin'):
            wrapped=ob.get(name)
            self.assertEqual(wrapped[:4],b'IMD5');self.assertEqual(hashlib.md5(wrapped[32:]).digest(),wrapped[16:32])
            a,b=art.nested(self.before,name),art.nested(self.after,name)
            for p in a.files:
                if p.endswith(('.brlyt','.brlan')) or 'Fujifilm' in p:self.assertEqual(a.get(p),b.get(p),p)
        names={self.after[0x9c+84*i:0x9c+84*i+84].decode('utf-16-be').rstrip('\0') for i in range(10)}
        self.assertEqual(names,{KOREAN_NAME})
        check=bytearray(self.after);check[0x630:0x640]=bytes(16)
        self.assertEqual(hashlib.md5(bytes(check[0x40:0x640])).digest(),self.after[0x630:0x640])

    def test_korean_title_ink(self):
        banner,icon=art.nested(self.after,'meta/banner.bin'),art.nested(self.after,'meta/icon.bin')
        old_banner,old_icon=art.nested(self.before,'meta/banner.bin'),art.nested(self.before,'meta/icon.bin')
        for archive,old,path in ((banner,old_banner,art.BANNER_TEXTURES[1]),(banner,old_banner,art.BANNER_TEXTURES[2]),
                                 (icon,old_icon,art.ICON_TEXTURES[0]),(icon,old_icon,art.ICON_TEXTURES[1])):
            image=tpl.decode(archive.get(path),0);w,h=image.size;ink=_ink(image);box=ink.getbbox()
            share=sum(1 for v in ink.getdata() if v)/(w*h)
            self.assertIsNotNone(box,path);self.assertGreaterEqual(box[2]-box[0],0.8*w,path)
            self.assertTrue(0.25<=share<=0.6,(path,share))
            changed=sum(abs(x-y) for x,y in zip(tpl.decode(old.get(path),0).getchannel('A').getdata(),image.getchannel('A').getdata()))/(w*h)
            self.assertGreater(changed,50,path)                            # redrawn, not the Japanese mask
        # two-line icon: one line above, one below a clear gap
        alpha=tpl.decode(icon.get(art.ICON_TEXTURES[1]),0).getchannel('A')
        rows=[sum(1 for x in range(alpha.width) if alpha.getpixel((x,y))>=128) for y in range(alpha.height)]
        self.assertGreater(max(rows[:18]),40);self.assertGreater(max(rows[21:]),40);self.assertLessEqual(max(rows[18:21]),2)
        # flat banner map: one opaque colour, the original's measured blue
        flat=tpl.decode(banner.get(art.BANNER_TEXTURES[2]),0)
        self.assertEqual({p[:3] for p in flat.getdata() if p[3]==255},{tuple(self.record['archives']['meta/banner.bin']['title']['flat_colour'])})
        # gloss map: light fill under the mask, the measured background elsewhere
        gloss=tpl.decode(banner.get(art.BANNER_TEXTURES[0]),0).convert('RGB')
        mask=tpl.decode(banner.get(art.BANNER_TEXTURES[1]),0).getchannel('A')
        background=self.record['archives']['meta/banner.bin']['title']['gloss_background']
        inside=[gloss.getpixel((x,y)) for y in range(gloss.height) for x in range(gloss.width) if mask.getpixel((x,y))>=240]
        outside=[gloss.getpixel((x,y)) for y in range(gloss.height) for x in range(gloss.width) if mask.getpixel((x,y))==0]
        self.assertGreater(sum(c[0] for c in inside)/len(inside),60)
        self.assertLessEqual(max(max(abs(c[i]-background[i]) for i in range(3)) for c in outside),8)

    def test_deterministic_and_independent_of_input_names(self):
        self.assertEqual(art.korean_menu_art(self.before)[0],self.after)
        if not ORIGINAL.exists():self.skipTest('original WAD not present')
        self.assertEqual(art.korean_menu_art(_title(ORIGINAL).get_content_by_index(0))[0],self.after)


class Outputs(unittest.TestCase):
    """build-v11 / hardware-v7: identity, scope and byte-identical regeneration."""
    @classmethod
    def setUpClass(cls):
        if not all(p.exists() for p in (V10,V11,HW5,HW7)):raise unittest.SkipTest('build-v11/hardware-v7 not present')
        cls.v10,cls.v11,cls.h5,cls.h7=map(_title,(V10,V11,HW5,HW7))
        cls.meta11=json.loads((V11.parent/'build-manifest.json').read_text(encoding='utf-8'))
        cls.meta7=json.loads((HW7.parent/'build-manifest.json').read_text(encoding='utf-8'))

    def test_hardware_v7_is_hcdj_region_4_ios56(self):
        t=self.h7
        self.assertEqual(t.tmd.title_id.lower(),TITLE);self.assertEqual(bytes.fromhex(TITLE[8:]),b'HCDJ')
        self.assertEqual(t.tmd.region,4);self.assertEqual(t.tmd.ios_tid.lower(),IOS56)
        self.assertEqual(t.tmd.title_version,self.h5.tmd.title_version);self.assertEqual(len(t.tmd.content_records),13)
        self.assertTrue(t.get_is_fakesigned())
        self.assertEqual(self.meta7['region_after'],4);self.assertFalse(self.meta7['local_only'])
        self.assertFalse(self.meta7['hardware_success_verified']);self.assertFalse(self.meta7['full_localization_complete'])

    def test_hardware_v7_differs_from_v5_only_in_content0_and_region(self):
        c5,c7=_contents(self.h5),_contents(self.h7)
        self.assertEqual([i for i in range(len(c5)) if c5[i]!=c7[i]],[0])
        self.assertEqual(c7[0],self.v11.get_content_by_index(0))
        self.assertEqual(self.h5.ticket.dump(),self.h7.ticket.dump())
        self.assertTrue(_within(self.h5.tmd.dump(),self.h7.tmd.dump(),menu_build.TMD_REGION,menu_build.TMD_FAKESIGN,menu_build.TMD_CONTENT0))
        self.assertEqual(local_reference_counts(self.h7),local_reference_counts(self.h5))
        self.assertEqual(local_reference_counts(self.h7),{'127.0.0':0,'localhost':0})

    def test_build_v11_differs_from_v10_only_in_content0(self):
        c10,c11=_contents(self.v10),_contents(self.v11)
        self.assertEqual([i for i in range(len(c10)) if c10[i]!=c11[i]],[0])
        self.assertEqual(self.v10.ticket.dump(),self.v11.ticket.dump())
        self.assertTrue(_within(self.v10.tmd.dump(),self.v11.tmd.dump(),menu_build.TMD_CONTENT0))
        self.assertEqual(self.v11.tmd.title_id.lower(),TITLE);self.assertEqual(self.v11.tmd.region,self.v10.tmd.region)
        self.assertEqual(self.meta11['revision'],11);self.assertTrue(self.meta11['local_only'])
        self.assertEqual(self.meta11['changed_contents_vs_source'],[0]);self.assertFalse(self.meta11['full_localization_complete'])

    def test_manifests_match_files(self):
        self.assertEqual(hashlib.sha256(V11.read_bytes()).hexdigest(),self.meta11['wad_sha256'])
        self.assertEqual(hashlib.sha256(HW7.read_bytes()).hexdigest(),self.meta7['wad_sha256'])
        self.assertEqual(self.meta7['local_source_wad_sha256'],self.meta11['wad_sha256'])
        self.assertEqual(self.meta7['source_wad_sha256'],hashlib.sha256(HW5.read_bytes()).hexdigest())

    def test_byte_identical_regeneration(self):
        (local,local_meta),(hardware,hardware_meta),_=menu_build.build()
        self.assertEqual(local,V11.read_bytes());self.assertEqual(hardware,HW7.read_bytes())
        self.assertEqual(json.loads(json.dumps(local_meta,ensure_ascii=False)),self.meta11)
        self.assertEqual(json.loads(json.dumps(hardware_meta,ensure_ascii=False)),self.meta7)


class HardwareRegion(unittest.TestCase):
    def test_new_hardware_candidates_have_region_3_or_4(self):
        """The Korean System Menu refuses TMD regions other than 3/4 (lead, 2026-10-28): hardware-v6 and later."""
        found=False
        for folder in sorted(BASE.glob('hardware-v*')):
            wad=folder/'photoprints-ko-hardware-test.wad'
            if int(folder.name.rsplit('-v',1)[1])<6 or not wad.exists():continue
            found=True;self.assertIn(_title(wad).tmd.region,(3,4),folder.name)
        if not found:self.skipTest('no hardware-v6+ candidate present')


class MenuLauncher(unittest.TestCase):
    def test_menu_option_uses_the_pinned_runner_menu_mode(self):
        source=(ROOT/'scripts/launch_photoprints.py').read_text(encoding='utf-8')
        self.assertIn("ap.add_argument('--menu'",source)
        self.assertIn("(['--menu'] if args.menu else [])",source)
        self.assertIn("'menu' if args.menu else 'channel',TITLE",source)
        runner=ROOT/'tools/photoprints-sandbox/v1/bin/PhotoPrintsRunner.cs'
        if not runner.exists():self.skipTest('Photo Prints helper not built')
        self.assertIn('args[1]=="menu"?" --nand_title 0000000100000002"',runner.read_text(encoding='utf-8'))
        lock=ROOT/'configs/photoprints-runtime.lock.json'
        if lock.exists():
            pinned={row['path'] for row in json.loads(lock.read_text())['files']}
            self.assertIn('tools/photoprints-sandbox/v1/bin/PhotoPrintsRunner.exe',pinned)


if __name__=='__main__':unittest.main()

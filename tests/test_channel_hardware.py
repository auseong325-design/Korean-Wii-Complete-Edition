import contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
from kwce.channel_hardware import APP,DATA,README,IDS,installer_source,sd_files,sha
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import deploy_channel_package as deployment
from unittest.mock import patch

def fixture(root):
    rows=[dict(id=ch,title_id=f'00010001414141{i:02x}')for i,ch in enumerate(sorted(IDS))]
    files={f'{APP}/{n}':n.encode()for n in ['boot.dol','meta.xml','icon.png']}
    files.update({f'{DATA}/packages.txt':b'list',README:b'guide'})
    for row in rows:
        for name in ['korean','original']:files[f'{DATA}/{row["id"]}/{name}.wad']=name.encode()
    for name,body in files.items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
    record=dict(kind='channel-only-v1',channels=rows,menu_writer_linked=False,priiloader_update=False,iso_included=False,
        sd_files=[dict(path=n,bytes=len(b),sha256=sha(b))for n,b in files.items()])
    p=root/'package-manifest.json';p.write_text(json.dumps(record));(root/'package-manifest.sha256').write_text(sha(p.read_bytes()))

class ChannelHardwareTests(unittest.TestCase):
    def test_copy_accepts_existing_fat_directory_case(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp);package=root/'package';package.mkdir();card=root/'card';card.mkdir()
            source=package/'sample.wad';source.write_bytes(b'channel')
            before=deployment.PRIVATE;deployment.PRIVATE=root/'evidence'
            try:
                verifier=lambda _: ({}, [(source,'wad/new/sample.wad')])
                states=[({},[]),({'WAD/new/sample.wad':[7,1]},[])]
                with patch.object(deployment,'inventory',side_effect=states):
                    deployment.deploy(package,card,verifier=verifier)
                self.assertEqual((card/'wad/new/sample.wad').read_bytes(),b'channel')
            finally:deployment.PRIVATE=before

    def test_installer_system_titles_duplicates_and_menu_writer_excluded(self):
        original=(ROOT/'homebrew/kwce-installer/source/main.c').read_text(encoding='utf-8')
        rows=json.loads((ROOT/'configs/hardware-channels-v1.json').read_text())['channels']
        code=installer_source(original,rows)
        self.assertNotIn('menu_install(',code);self.assertNotIn('menu_available(',code)
        self.assertNotIn('allow-current-ios.txt',code);self.assertIn('#define BASE "sd:/kwce"',code)
        for bad in [[dict(title_id='0000000100000002')],[rows[0],rows[0]]]:
            with self.assertRaises(ValueError):installer_source(original,bad)

    def test_payload_hash_and_scope_refuse_corruption(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);fixture(root);_,plan=sd_files(root)
            self.assertEqual(len(plan),16)
            (root/APP/'boot.dol').write_bytes(b'changed')
            with self.assertRaises(ValueError):sd_files(root)

    def test_copy_backs_up_and_preserves_dvd_priiloader_state_and_logs(self):
        with tempfile.TemporaryDirectory()as tmp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp);package=root/'package';package.mkdir();fixture(package);card=root/'card';card.mkdir()
            protected={'apps/Priiloader/hacks_hash.ini':b'original hacks','kwce/state/news.txt':b'first state',
                'kwce/log.txt':b'old log','apps/kwce-dvd-installer/boot.dol':b'dvd app','kwce-dvd-test/packages.txt':b'dvd list'}
            for name,body in {**protected,f'{APP}/boot.dol':b'old app'}.items():
                p=card/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
            before=deployment.PRIVATE;deployment.PRIVATE=root/'evidence'
            try:
                deployment.deploy(package,card,True);self.assertEqual((card/APP/'boot.dol').read_bytes(),b'old app')
                deployment.deploy(package,card)
                for name,body in protected.items():self.assertEqual((card/name).read_bytes(),body)
                backups=list((card/'kwce-deploy-backups').iterdir());self.assertEqual((backups[0]/APP/'boot.dol').read_bytes(),b'old app')
                result=json.loads(next(deployment.PRIVATE.glob('*/result.json')).read_text())
                self.assertEqual(result['unplanned_changes'],0);self.assertEqual(result['verified_files'],16)
                with self.assertRaises(ValueError):deployment.guarded(card,'../escape')
            finally:deployment.PRIVATE=before

@unittest.skipUnless((ROOT/'workspace/channels/tvguide/build-v8/build-manifest.json').exists(),'TV hardware candidate missing')
class TvHardwareTests(unittest.TestCase):
    def test_v7_resources_retained_original_urls_and_registration_restored(self):
        from kwce.channels import load_library
        from kwce.hardware import local_reference_counts
        import re
        lib=load_library();base=ROOT/'workspace/channels/tvguide';titles=[]
        for name in ['originals/tvguide-japan-original.wad','build-v7/tvguide-ko-local-test.wad','build-v8/tvguide-ko-hardware-test.wad']:
            title=lib.title.Title();title.load_wad((base/name).read_bytes());titles.append(title)
        original,local,hardware=titles
        for i in range(14):
            if i!=1:self.assertEqual(local.get_content_by_index(i),hardware.get_content_by_index(i))
        raw=original.get_content_by_index(1);actual=hardware.get_content_by_index(1)
        self.assertEqual(actual[0x14adf4:0x14ae04],raw[0x14adf4:0x14ae04])
        count=0
        for match in re.finditer(rb'https?://[^\0\s<>"\x80-\xff]{3,250}',raw):
            if b'.wapp.wii.com'in match.group():
                self.assertEqual(actual[match.start():match.end()],match.group());count+=1
        self.assertEqual(count,48);self.assertEqual(local_reference_counts(hardware),local_reference_counts(original))

if __name__=='__main__':unittest.main()

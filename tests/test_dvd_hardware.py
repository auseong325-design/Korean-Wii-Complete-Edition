import contextlib,io,json,shutil,sys,tempfile,unittest
from pathlib import Path
from kwce.dvd_hardware import installer_source,merge_hacks,sd_files,APP,DATA
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import deploy_dvd_package as deployment

OTHER=b'[Existing]\r\nmaxversion=518\r\nminversion=518\r\namount=1\r\nhash=0x12345678,0xabcdef00\r\npatch=0x60000000\r\n'
DVD=b'[KWCE DVD: disc channel DVD player]\nmaxversion=518\nminversion=518\namount=1\nhash=0x12345678,0xabcdef00\npatch=0x60000000\n'
PACKAGE=ROOT/'workspace/hardware/kwce-dvd-r21-v1'

class DvdHardwareTests(unittest.TestCase):
    def setUp(self):
        capture=contextlib.redirect_stdout(io.StringIO());capture.__enter__()
        self.addCleanup(capture.__exit__,None,None,None)
    def test_installer_only_allows_dvd_without_menu_writer_or_test_override(self):
        for revision in (19,20,21):
            source=installer_source((ROOT/'homebrew/kwce-installer/source/main.c').read_text(encoding='utf-8'),revision)
            self.assertIn('#define BASE "sd:/kwce-dvd-test"',source)
            self.assertIn('tid != 0x000100014b445644ULL',source)
            self.assertIn(f'0.3-dvd-r{revision}',source)
            self.assertNotIn('menu_install(',source);self.assertNotIn('menu_available(',source)
            self.assertNotIn('allow-current-ios.txt',source)
        with self.assertRaises(ValueError):installer_source('unreviewed installer')

    def test_hack_merge_preserves_existing_and_is_idempotent(self):
        first=merge_hacks(OTHER,DVD)
        self.assertTrue(first.startswith(OTHER));self.assertEqual(first.count(b'[KWCE DVD:'),1)
        self.assertEqual(merge_hacks(first,DVD),first)
        with self.assertRaises(ValueError):merge_hacks(b'[New]\nminversion=518\nmaster=1\n',DVD)

    @unittest.skipUnless(PACKAGE.exists(),'local personal DVD package unavailable')
    def test_package_integrity_and_tampering(self):
        record,plan=sd_files(PACKAGE)
        self.assertEqual(record['player_build'],21);self.assertEqual(record['wad_revision'],18)
        self.assertFalse(record['menu_writer_linked']);self.assertFalse(record['emulator_preview_included'])
        self.assertFalse(any(p.endswith('.iso')for _,p in plan))
        with tempfile.TemporaryDirectory(dir=ROOT/'workspace/private')as tmp:
            copy=Path(tmp)/'package';shutil.copytree(PACKAGE,copy)
            (copy/DATA/'dvd-player/korean.wad').write_bytes(b'tampered')
            with self.assertRaises(ValueError):sd_files(copy)

    @unittest.skipUnless(PACKAGE.exists(),'local personal DVD package unavailable')
    def test_sd_copy_backs_up_overwrites_and_preserves_unrelated_state(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'workspace/private')as tmp:
            root=Path(tmp).resolve();self.assertTrue(root.is_relative_to(ROOT/'workspace/private'))
            card=root/'card';(card/'apps/Priiloader').mkdir(parents=True)
            (card/'apps/Priiloader/hacks_hash.ini').write_bytes(OTHER)
            (card/APP).mkdir();(card/APP/'boot.dol').write_bytes(b'previous-app')
            (card/'kwce/state').mkdir(parents=True);state=card/'kwce/state/existing.txt';state.write_bytes(b'keep-state')
            before=state.stat().st_mtime_ns
            old_private=deployment.PRIVATE;deployment.PRIVATE=root/'records';deployment.PRIVATE.mkdir()
            try:
                deployment.deploy(PACKAGE,card,True)
                self.assertFalse((card/'KWCE-DVD-README-ko.txt').exists())
                deployment.deploy(PACKAGE,card)
                self.assertEqual(state.read_bytes(),b'keep-state');self.assertEqual(state.stat().st_mtime_ns,before)
                backups=list((card/'kwce-deploy-backups').iterdir());self.assertEqual(len(backups),1)
                self.assertEqual((backups[0]/APP/'boot.dol').read_bytes(),b'previous-app')
                self.assertEqual((backups[0]/'apps/Priiloader/hacks_hash.ini').read_bytes(),OTHER)
                result=json.loads(next(deployment.PRIVATE.glob('*/result.json')).read_text())
                self.assertEqual(result['original_files_missing'],0);self.assertEqual(result['unplanned_changes'],0)
                with self.assertRaises(ValueError):deployment.guarded(card,'../outside')
            finally:deployment.PRIVATE=old_private

if __name__=='__main__':unittest.main()

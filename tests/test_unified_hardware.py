import sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from kwce.unified_hardware import ROWS,allowed,source
from deploy_channel_package import deploy

class UnifiedHardwareTest(unittest.TestCase):
    def test_installer_fixed_channel_scope_and_remote(self):
        text=source((ROOT/'homebrew/kwce-installer/source/main.c').read_text(encoding='utf-8'))
        for channel,tid,_,_ in ROWS:
            self.assertIn(f'!strcmp(p->id,"{channel}") && p->tid == 0x{tid}ULL',text)
        self.assertIn('WPAD_ButtonsDown(i)',text)
        self.assertIn('sd:/kwce-dvd-test/state/dvd-player.txt',text)
        self.assertNotIn('menu_install(',text)
        self.assertNotIn('allow-current-ios.txt',text)

    def test_package_refuses_saves_and_system_files(self):
        for p in ('apps/Priiloader/hacks_hash.ini','vbagx/saves/user.sav','apps/vbagx/settings.xml','apps/usbloader_gx/wiitdb.xml','../boot.dol'):
            self.assertFalse(allowed(p),p)
        self.assertTrue(allowed('apps/not64/data.iso'))

    def test_verified_package_and_settings_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);package=work/'package';package.mkdir();payload=package/'boot.dol';payload.write_bytes(b'new executable')
            card=work/'card';card.mkdir();(card/'apps/vbagx').mkdir(parents=True)
            setting=card/'apps/vbagx/settings.xml';setting.write_bytes(b'user settings')
            existing=card/'apps/vbagx/boot.dol';existing.write_bytes(b'old executable')
            untouched=card/'keep.txt';untouched.write_bytes(b'keep')
            verifier=lambda root: ({},[(root/'boot.dol','apps/vbagx/boot.dol')])
            deploy(package,card,verifier=verifier,extra_backup=('apps/vbagx/settings.xml',))
            backups=list((card/'kwce-deploy-backups').iterdir());self.assertEqual(len(backups),1)
            self.assertEqual((backups[0]/'apps/vbagx/settings.xml').read_bytes(),b'user settings')
            self.assertEqual((backups[0]/'apps/vbagx/boot.dol').read_bytes(),b'old executable')
            self.assertEqual(setting.read_bytes(),b'user settings');self.assertEqual(untouched.read_bytes(),b'keep')

if __name__=='__main__':unittest.main()

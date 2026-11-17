"""Verify update scope and both SD Room paths without touching a real card."""
import json,sys,unittest,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import export_loading_update as update

class LoadingPackageTests(unittest.TestCase):
    def test_old_or_external_packages_are_rejected(self):
        for p in (update.OUT.with_name('kwce-loading-news19-room49-v1'),Path(tempfile.gettempdir())/update.OUT.name):
            with self.assertRaises(ValueError):update.sd_files(p)
    @unittest.skipUnless(update.ZIP.exists(),'local private loading package required')
    def test_exact_scope_and_shared_room_identity(self):
        m,files=update.sd_files(update.OUT)
        self.assertEqual(m['revisions'],{'news':20,'wiiroom':51})
        self.assertEqual({rel for _,rel in files},update.ALLOWED);self.assertEqual(len(files),10)
        self.assertFalse(m['system_writer_linked']);self.assertFalse(m['hardware_success_verified'])
        self.assertFalse(any('Priiloader'in p or '/state/'in p or p.endswith('log.txt')for _,p in files))
        self.assertEqual((update.OUT/'kwce/wiiroom/korean.wad').read_bytes(),(update.OUT/'kwce-wiiroom/wiiroom/korean.wad').read_bytes())
        listing=(update.OUT/'kwce/packages.txt').read_text(encoding='ascii')
        self.assertEqual(listing.count('News r20'),1);self.assertEqual(listing.count('Wii Room r51'),1)

if __name__=='__main__':unittest.main()

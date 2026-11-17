"""Room deployment uses only its reviewed payload and the backup-first copier."""
import contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import export_wiiroom_update as room
import deploy_channel_package as copier

class RoomSourceTests(unittest.TestCase):
    def test_old_or_external_packages_are_rejected_before_reading(self):
        for p in [room.OUT.with_name('kwce-wiiroom-r43-v1'),Path(tempfile.gettempdir())/room.OUT.name]:
            with self.assertRaises(ValueError):room.sd_files(p)

    @unittest.skipUnless(room.ZIP.exists(),'local reviewed Room package required')
    def test_only_the_eight_verified_payload_files_are_returned(self):
        m,files=room.sd_files(room.OUT)
        self.assertEqual(m['revision'],47);self.assertEqual({p for _,p in files},room.ALLOWED);self.assertEqual(len(files),8)
        self.assertFalse(any('Priiloader' in p or '/state/' in p or p.endswith(('.iso','.c','.elf'))for _,p in files))

class BackupFirstTests(unittest.TestCase):
    def test_update_backs_up_previous_payload_and_preserves_other_files(self):
        with tempfile.TemporaryDirectory()as td:
            root=Path(td);package=root/'room';card=root/'card';private=root/'private';package.mkdir();card.mkdir();private.mkdir()
            payload=package/'boot.dol';payload.write_bytes(b'new reviewed payload');target=card/'apps/kwce-wiiroom-installer/boot.dol';target.parent.mkdir(parents=True);target.write_bytes(b'old payload')
            protected=card/'apps/Priiloader/hacks_hash.ini';protected.parent.mkdir();protected.write_bytes(b'preserved hacks')
            state=card/'kwce-wiiroom/state/example.txt';state.parent.mkdir(parents=True);state.write_bytes(b'preserved state')
            verifier=lambda _ : ({},[(payload,'apps/kwce-wiiroom-installer/boot.dol')])
            with patch.object(copier,'PRIVATE',private),contextlib.redirect_stdout(io.StringIO()):copier.deploy(package,card,verifier=verifier)
            result=json.loads(next(private.glob('*/result.json')).read_text())
            self.assertEqual(target.read_bytes(),payload.read_bytes());self.assertEqual(result['backed_up_files'],1)
            self.assertEqual((card/result['backup']/'apps/kwce-wiiroom-installer/boot.dol').read_bytes(),b'old payload')
            self.assertEqual(protected.read_bytes(),b'preserved hacks');self.assertEqual(state.read_bytes(),b'preserved state');self.assertEqual(result['unplanned_changes'],0)

if __name__=='__main__':unittest.main()

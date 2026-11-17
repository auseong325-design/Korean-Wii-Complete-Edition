"""Replacement failure must preserve the preexisting SD target (local fixture)."""
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from deploy_channel_package import replace_verified

class AtomicDeploymentTests(unittest.TestCase):
    def test_success_replaces_only_after_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'boot.dol';target.write_bytes(b'old')
            replace_verified(target,b'new payload')
            self.assertEqual(target.read_bytes(),b'new payload')
            self.assertFalse(target.with_name('boot.dol.kwce-new').exists())

    def test_failed_replace_preserves_original_and_staged_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'boot.dol';target.write_bytes(b'old')
            with patch('deploy_channel_package.os.replace',side_effect=OSError('fixture')):
                with self.assertRaises(OSError):replace_verified(target,b'new payload')
            self.assertEqual(target.read_bytes(),b'old')
            self.assertEqual(target.with_name('boot.dol.kwce-new').read_bytes(),b'new payload')

    def test_existing_stage_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'boot.dol';target.write_bytes(b'old')
            staged=target.with_name('boot.dol.kwce-new');staged.write_bytes(b'previous')
            with self.assertRaises(FileExistsError):replace_verified(target,b'new payload')
            self.assertEqual(target.read_bytes(),b'old')
            self.assertEqual(staged.read_bytes(),b'previous')

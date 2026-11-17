"""Online Linux Dolphin profiles: only the network namespace differs from the offline sandbox."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'linux', 'Linux launcher')
class OnlineSandboxTests(unittest.TestCase):
    def setUp(self):
        import shutil
        if not shutil.which('bwrap'): self.skipTest('bubblewrap not installed')
        from kwce import linux_online, linux_runtime
        self.online, self.offline = linux_online, linux_runtime
        self.dest = ROOT / 'workspace/online/unit-test-v1'

    def test_only_network_is_shared(self):
        on = self.online.online_sandbox(self.dest, '/usr/bin/true', [], gui=False)
        off = self.offline.sandbox(self.dest, '/usr/bin/true', [], gui=False)
        self.assertEqual(on[on.index('--unshare-all') + 1], '--share-net')
        self.assertNotIn('--share-net', off)
        extra = [x for x in on if x not in off]
        self.assertTrue(all(x == '--share-net' or x.startswith('/etc/') or x.startswith('/run/') for x in extra), extra)
        for must in ('--cap-drop', 'ALL', '--clearenv', '--new-session'):
            self.assertIn(must, on)
        binds = [on[i + 1] for i, x in enumerate(on) if x in ('--bind', '--ro-bind', '--dev-bind')]
        self.assertFalse([b for b in binds if b.startswith('/home') or b == str(ROOT) or b.startswith(str(ROOT / 'sd'))])

    def test_profiles_are_kept_apart_from_offline_ones(self):
        self.assertEqual(self.online.BASE, ROOT / 'workspace/online')
        self.assertNotEqual(self.online.BASE, self.offline.BASE)
        with self.assertRaises(ValueError): self.online.runtime('../linux/menu-v1')
        with self.assertRaises(ValueError): self.online.uninstall.__wrapped__ if hasattr(self.online.uninstall, '__wrapped__') else self.online.runtime('Bad Name')

    def test_new_profiles_keep_korean_for_pal_titles(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.online.write_config(Path(tmp), wiilink=False)
            self.assertIn('OverrideRegionSettings = True', (Path(tmp) / 'Config/Dolphin.ini').read_text())

    def test_source_nand_is_not_a_profile(self):
        self.assertFalse(str(self.online.SOURCE).startswith(str(self.online.BASE)))


if __name__ == '__main__':
    unittest.main()

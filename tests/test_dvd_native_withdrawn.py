"""Failed hardware candidates must be rejected before inspecting or writing SD."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WithdrawnCandidateTests(unittest.TestCase):
    def reject(self, package, revision):
        with tempfile.TemporaryDirectory() as folder:
            card = Path(folder)
            marker = card / 'preserve.txt'
            marker.write_bytes(b'original')
            before = marker.stat()
            for extra in ([], ['--dry-run']):
                result = subprocess.run(
                    [sys.executable, str(ROOT / 'scripts/deploy_to_sd.py'),
                     package, '--drive', str(card), *extra],
                    cwd=ROOT, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Withdrawn DVD candidate: ' + revision, result.stderr)
                self.assertEqual(list(card.iterdir()), [marker])
                self.assertEqual(marker.read_bytes(), b'original')
                self.assertEqual(marker.stat().st_mtime_ns, before.st_mtime_ns)

    def test_native58_rejected_without_card_access(self):
        self.reject('kwce-dvd-deferred-prefetch-v1', 'native58')

    def test_native60_rejected_without_card_access(self):
        self.reject('kwce-dvd-icon-cache-v1', 'native60')

    def test_read_control_ownership_violation_is_blocked(self):
        self.reject('kwce-dvd-read-control-v1', 'native61')


if __name__ == '__main__':
    unittest.main()

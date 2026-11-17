"""sntp SD package: unmodified upstream payload, Korea offset preset, strict paths."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'workspace/hardware/kwce-sntp-sd-v1'


@unittest.skipUnless(PKG.is_dir(), 'sntp package not built')
class SntpPackageTests(unittest.TestCase):
    def test_payload_matches_pins(self):
        from kwce.sntp_package import sd_files, ALLOWED
        record, files = sd_files(PKG)
        self.assertEqual({r for _, r in files}, ALLOWED)
        self.assertFalse(record['modified_upstream_binary'])

    def test_config_is_korea_offset_only(self):
        cfg = (PKG / 'apps/sntp/sntp.cfg').read_text()
        lines = [l for l in cfg.splitlines() if l and not l.startswith('#')]
        self.assertEqual(lines, ['offset=32400'])


if __name__ == '__main__':
    unittest.main()

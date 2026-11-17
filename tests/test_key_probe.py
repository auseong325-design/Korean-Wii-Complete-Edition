"""Key probe package boundary (public patch design v2, stage 2)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from kwce.key_probe import PATHS, sd_files

ROOT = Path(__file__).resolve().parents[1]
_PKGS = sorted((ROOT / 'workspace/hardware').glob('kwce-key-probe-sd-v*'), key=lambda p: int(p.name.rsplit('v', 1)[1]))
PKG = next((p for p in reversed(_PKGS) if (p / 'package-manifest.json').exists()), ROOT / 'missing')


@unittest.skipUnless(PKG.is_dir(), 'key probe package not built')
class KeyProbePackage(unittest.TestCase):
    def test_scope_and_payload(self):
        meta, rows = sd_files(PKG)
        self.assertFalse(meta['nand_write'] or meta['network'] or meta['key_output'] or meta['ios_reload'])
        self.assertEqual({dest for _, dest in rows} - {'KWCE-KEY-PROBE-manifest.json'}, PATHS)
        xml = (PKG / 'apps/kwce-key-probe/meta.xml').read_text()
        self.assertIn('<ahb_access/>', xml)
        self.assertIn('<no_ios_reload/>', xml)

    def test_tampered_payload_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / PKG.name
            shutil.copytree(PKG, copy)
            dol = copy / 'apps/kwce-key-probe/boot.dol'
            dol.write_bytes(dol.read_bytes() + b'\0')
            with self.assertRaises(ValueError):
                sd_files(copy)

    def test_scope_flag_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / PKG.name
            shutil.copytree(PKG, copy)
            meta = json.loads((copy / 'package-manifest.json').read_text())
            meta['nand_write'] = True
            raw = (json.dumps(meta) + '\n').encode()
            (copy / 'package-manifest.json').write_bytes(raw)
            import hashlib
            (copy / 'package-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest() + '\n')
            with self.assertRaises(ValueError):
                sd_files(copy)


if __name__ == '__main__':
    unittest.main()

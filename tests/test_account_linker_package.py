"""Scope and immutable upstream checks for the SD Account Linker package."""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from kwce.account_linker_package import sd_files

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'workspace/hardware/kwce-account-linker-sd-v1'


class AccountLinkerPackageTests(unittest.TestCase):
    def test_pinned_official_package(self):
        meta, files = sd_files(PACKAGE)
        self.assertEqual(meta['version'], '2.1.0')
        self.assertEqual(len(files), 8)
        self.assertFalse(meta['hardware_verified'])

    def test_rehashed_modified_binary_is_still_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'workspace/private') as directory:
            tmp = Path(directory) / 'package';shutil.copytree(PACKAGE, tmp)
            path = tmp / 'apps/wiilink-account-linker/boot.dol'
            data = bytearray(path.read_bytes());data[-1] ^= 1;path.write_bytes(data)
            manifest = tmp / 'package-manifest.json';meta = json.loads(manifest.read_text(encoding='utf-8'))
            for row in meta['sd_files']:
                if row['path'] == 'apps/wiilink-account-linker/boot.dol':
                    row['sha256'] = hashlib.sha256(data).hexdigest()
            raw = (json.dumps(meta, indent=2) + '\n').encode();manifest.write_bytes(raw)
            (tmp / 'package-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest() + '\n', encoding='ascii')
            with self.assertRaisesRegex(ValueError, 'upstream binary differs'):
                sd_files(tmp)


PACKAGE_V2 = ROOT / 'workspace/hardware/kwce-account-linker-sd-v2'
REPO = ROOT / 'external/other-tools/AccountLinker'


@unittest.skipUnless(PACKAGE_V2.exists(), 'Account Linker sd-v2 not exported')
class AccountLinkerV2Tests(unittest.TestCase):
    def test_pinned_2_2_0_package(self):
        meta, files = sd_files(PACKAGE_V2)
        self.assertEqual((meta['kind'], meta['version']), ('official-account-linker-v2', '2.2.0'))
        self.assertEqual(len(files), 8)
        self.assertFalse(meta['hardware_verified'])
        dol = (PACKAGE_V2 / 'apps/wiilink-account-linker/boot.dol').read_bytes()
        self.assertIn(b'v2.2.0', dol)

    def test_source_and_licence_regenerate_from_the_tag(self):
        import subprocess
        commit = json.loads((ROOT / 'configs/account-linker-v2.lock.json').read_text())['source_commit']
        git = lambda *a: subprocess.run(['git', '-C', str(REPO), *a], capture_output=True, check=True).stdout
        app = PACKAGE_V2 / 'apps/wiilink-account-linker'
        self.assertEqual((app / 'source.zip').read_bytes(), git('archive', '--format=zip', commit))
        self.assertEqual((app / 'LICENSE').read_bytes(), git('show', f'{commit}:LICENCE'))

    def test_v1_manifest_cannot_claim_the_v2_pin(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'workspace/private') as directory:
            tmp = Path(directory) / 'package';shutil.copytree(PACKAGE, tmp)
            manifest = tmp / 'package-manifest.json';meta = json.loads(manifest.read_text(encoding='utf-8'))
            meta['kind'] = 'official-account-linker-v2'
            raw = (json.dumps(meta, indent=2) + '\n').encode();manifest.write_bytes(raw)
            (tmp / 'package-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest() + '\n', encoding='ascii')
            with self.assertRaisesRegex(ValueError, 'scope differs'):
                sd_files(tmp)

if __name__ == '__main__': unittest.main()

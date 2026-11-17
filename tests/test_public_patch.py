"""Public patch bundle (design v3): delta/WAD round trips and the public-terms audit."""
import hashlib
import json
import os
import struct
import unittest
from pathlib import Path

from kwce import public_patch as pp

ROOT = Path(__file__).resolve().parents[1]
_B = sorted((ROOT / 'workspace/public').glob('kwce-public-v*'), key=lambda p: int(p.name.rsplit('v', 1)[1]))
BUNDLE = next((p for p in reversed(_B) if (p / 'manifest.sha256').exists()), None)


def fake_wad(contents, footer=b''):
    tmd = bytearray(0x1E4 + 36 * len(contents))
    struct.pack_into('>H', tmd, 0x1DE, len(contents))
    enc = []
    for i, c in enumerate(contents):
        struct.pack_into('>IHHQ', tmd, 0x1E4 + 36 * i, i, i, 1, len(c))
        tmd[0x1E4 + 36 * i + 16:0x1E4 + 36 * i + 36] = hashlib.sha1(c).digest()
        enc.append(c + bytes(pp.al(len(c), 16) - len(c)))          # layout test only: not encrypted
    cert, tik = os.urandom(0xA00), os.urandom(0x2A4)
    data = sum(pp.al(len(e), 0x40) for e in enc)
    header = struct.pack('>I4s6I', 0x20, b'Is\0\0', len(cert), 0, len(tik), len(tmd), data, len(footer))
    length = 0x40 + pp.al(len(cert), 0x40) + pp.al(len(tik), 0x40) + pp.al(len(tmd), 0x40) + data + pp.al(len(footer), 0x40)
    return pp.build_wad(header, cert, b'', tik, bytes(tmd), enc, footer, length)


class Delta(unittest.TestCase):
    def test_round_trip_with_and_without_dictionary(self):
        base = os.urandom(300000)
        target = base[:120000] + b'KWCE' * 500 + base[150000:]
        patch = pp.make_delta(base, target)
        self.assertLess(len(patch), 6000)
        self.assertEqual(pp.apply_delta(base, patch, len(target)), target)
        self.assertEqual(pp.apply_delta(b'', pp.make_delta(b'', target), len(target)), target)

    def test_wrong_size_refused(self):
        patch = pp.make_delta(b'', b'abc' * 100)
        with self.assertRaises(Exception):
            pp.apply_delta(b'', patch, 299)


class WadLayout(unittest.TestCase):
    def test_parse_and_rebuild_is_identical(self):
        for footer in (b'', os.urandom(777)):
            raw = fake_wad([os.urandom(1000), os.urandom(64), os.urandom(70001)], footer)
            w = pp.Wad(raw)
            self.assertEqual([r['size'] for r in w.records], [1000, 64, 70001])
            again = pp.build_wad(w.header, w.cert, w.crl, w.ticket, w.tmd, w.enc, w.footer, w.length)
            self.assertEqual(again, raw)

    def test_non_wad_refused(self):
        with self.assertRaises(ValueError):
            pp.Wad(bytes(0x100))


@unittest.skipUnless(BUNDLE, 'public bundle not built')
class Bundle(unittest.TestCase):
    def test_manifest_and_terms(self):
        raw = (BUNDLE / 'manifest.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), (BUNDLE / 'manifest.sha256').read_text().strip())
        m = json.loads(raw)
        self.assertEqual(pp.audit_bundle(BUNDLE), [])
        for rel, rec in m['files'].items():
            self.assertIn(rec['mode'], ('wad', 'copy', 'delta', 'verbatim'))
            self.assertEqual(len(rec['sha256']), 64)
            if rel.endswith('.wad'):
                self.assertEqual(rec['mode'], 'wad', rel)          # never a finished WAD in the bundle
        self.assertFalse(list((BUNDLE / 'files').rglob('*.wad')))

    def test_tampered_manifest_refused(self):
        import shutil, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / 'b'; copy.mkdir()
            shutil.copyfile(BUNDLE / 'manifest.sha256', copy / 'manifest.sha256')
            (copy / 'manifest.json').write_bytes((BUNDLE / 'manifest.json').read_bytes() + b' ')
            with self.assertRaises(ValueError):
                pp.apply_bundle(copy, Path(tmp) / 'out', Path(tmp) / 'cache', log=lambda *_: None)


if __name__ == '__main__':
    unittest.main()

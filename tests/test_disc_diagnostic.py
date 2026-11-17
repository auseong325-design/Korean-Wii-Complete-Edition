"""Protect the SD boundary of the read-only Priiloader diagnostic."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from kwce.disc_diagnostic import ALLOWED,sd_files

class DiscDiagnosticPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        rows=[]
        for name in sorted(ALLOWED):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(name.encode())
            rows.append(dict(path=name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        self.meta=dict(kind='disc-diagnostic-v1',nand_write=False,console_identifiers=False,wad_included=False,sd_files=rows)
        self.write_manifest()
    def tearDown(self):self.tmp.cleanup()
    def write_manifest(self):
        data=json.dumps(self.meta).encode();(self.root/'package-manifest.json').write_bytes(data)
        (self.root/'package-manifest.sha256').write_text(hashlib.sha256(data).hexdigest())
    def test_expected_files_and_manifest_only(self):
        _,files=sd_files(self.root)
        self.assertEqual({p for _,p in files},ALLOWED|{'KWCE-DISC-DIAGNOSTIC-manifest.json'})
    def test_changed_payload_refused(self):
        (self.root/'apps/kwce-disc-diagnostic/boot.dol').write_bytes(b'changed')
        with self.assertRaises(ValueError):sd_files(self.root)
    def test_system_writer_or_unexpected_target_refused(self):
        self.meta['nand_write']=True;self.write_manifest()
        with self.assertRaises(ValueError):sd_files(self.root)
        self.meta['nand_write']=False;self.meta['sd_files'][0]['path']='apps/Priiloader/hacks_hash.ini';self.write_manifest()
        with self.assertRaises(ValueError):sd_files(self.root)

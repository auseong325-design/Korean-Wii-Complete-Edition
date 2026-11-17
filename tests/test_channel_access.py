import hashlib,json,tempfile,unittest
from pathlib import Path
from kwce.channel_access import validate_fixtures

class ChannelAccessGuards(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.payload=b'synthetic channel fixture'
        (self.root/'fixture.bin').write_bytes(self.payload)
        (self.root/'routes.tsv').write_text('* /first_data.bin\tfixture.bin\n',encoding='ascii')
        self.meta=dict(channel='votes',synthetic=True,routes_sha256=self.digest((self.root/'routes.tsv').read_bytes()),files=[dict(path='fixture.bin',size=len(self.payload),sha256=self.digest(self.payload))])
        self.save()
    def digest(self,data):return hashlib.sha256(data).hexdigest()
    def save(self):(self.root/'fixture-manifest.json').write_text(json.dumps(self.meta))
    def test_valid_synthetic_fixture(self):self.assertEqual((1,1),validate_fixtures(self.root,'votes'))
    def test_wrong_channel(self):
        with self.assertRaises(ValueError):validate_fixtures(self.root,'nintendo')
    def test_requires_synthetic_identity(self):
        self.meta['synthetic']=False;self.save()
        with self.assertRaises(ValueError):validate_fixtures(self.root,'votes')
    def test_changed_payload(self):
        (self.root/'fixture.bin').write_bytes(b'changed')
        with self.assertRaises(ValueError):validate_fixtures(self.root,'votes')
    def test_changed_routes(self):
        (self.root/'routes.tsv').write_text('* /other\tfixture.bin\n')
        with self.assertRaises(ValueError):validate_fixtures(self.root,'votes')
    def test_parent_traversal(self):
        self.meta['files'][0]['path']='../fixture.bin';self.save()
        with self.assertRaises(ValueError):validate_fixtures(self.root,'votes')
    def test_unlisted_route_payload(self):
        data=b'* /first_data.bin\tother.bin\n';(self.root/'routes.tsv').write_bytes(data);self.meta['routes_sha256']=self.digest(data);self.save()
        with self.assertRaises(ValueError):validate_fixtures(self.root,'votes')
    def test_duplicate_route_refused(self):
        data=(self.root/'routes.tsv').read_bytes()*2;(self.root/'routes.tsv').write_bytes(data);self.meta['routes_sha256']=self.digest(data);self.save()
        with self.assertRaises(ValueError):validate_fixtures(self.root,'votes')

if __name__=='__main__':unittest.main()

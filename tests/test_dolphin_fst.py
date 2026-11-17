import struct,unittest
from kwce.dolphin_fst import inspect_fst

def record(name,children=0,file=False):
    b=bytearray(32);b[:len(name)]=name;b[18]=int(file);b[19:22]=bytes([3,1,1]);struct.pack_into('>I',b,28,children);return bytes(b)

class FstTests(unittest.TestCase):
    def test_preorder_tree(self):
        result=inspect_fst(record(b'/',2)+record(b'tmp',1)+record(b'data',file=True)+record(b'sys'))
        self.assertEqual((result['records'],result['files'],result['directories'],result['max_depth']),(4,1,3,2))
        self.assertNotIn('name',result)

    def test_truncated_or_orphaned_records(self):
        for b in [b'',bytes(31),record(b'/',1),record(b'/')+record(b'orphan'),record(b'/',1)+record(b'f',1,True)]:
            with self.subTest(size=len(b)),self.assertRaises(ValueError):inspect_fst(b)

    def test_bad_components_depth_metadata(self):
        for name in [b'',b'..',b'a/b',b'a\\b']:
            with self.assertRaises(ValueError):inspect_fst(record(b'/',1)+record(name))
        with self.assertRaises(ValueError):inspect_fst(record(b'/',1)+record(b'd',1)*8+record(b'end'))
        b=bytearray(record(b'/'));b[18]=2
        with self.assertRaises(ValueError):inspect_fst(b)

import random,unittest
from kwce import cx_huffman

class CxHuffman(unittest.TestCase):
    def roundtrip(self,data):
        packed=cx_huffman.compress(data)
        self.assertEqual(packed[0],0x28);self.assertEqual(data,cx_huffman.decompress(packed))
    def test_skewed_sheet_like_data(self):
        rng=random.Random(5);self.roundtrip(bytes(rng.choice([0,0,0,0,0x11,0xff,0xf0,0x0f,rng.randrange(48)])for _ in range(65536)))
    def test_wide_tree_fails_cleanly(self):
        try:packed=cx_huffman.compress(bytes(range(256))*16)
        except ValueError:return
        self.assertEqual(bytes(range(256))*16,cx_huffman.decompress(packed))
    def test_single_symbol(self):self.roundtrip(bytes(4096))
    def test_rejects_other_type(self):
        with self.assertRaises(ValueError):cx_huffman.decompress(b'\x10\x00\x01\x00')

if __name__=='__main__':unittest.main()

import unittest
from kwce.wiiroom_formats import decompress_lz11,reencode_lz11_same_size,compress_lz10_optimal


class LZ11Tests(unittest.TestCase):
    def test_all_reference_lengths_and_overlap(self):
        for count,reference in [(3,b'\x20\0'),(17,b'\0\0\0'),(273,b'\x10\0\0\0')]:
            with self.subTest(count=count):
                packed=b'\x11'+(count+1).to_bytes(3,'little')+b'\x40A'+reference
                self.assertEqual(decompress_lz11(packed),b'A'*(count+1))

    def test_rejects_truncation_bad_distance_and_allocation(self):
        for packed in [b'\x11\x01\0\0',b'\x11\x03\0\0\x80\x20\0',b'\x11\xff\xff\xff']:
            with self.subTest(packed=packed),self.assertRaises(ValueError):decompress_lz11(packed,limit=100)

    def test_edited_literals_and_matches_cannot_copy_old_bytes(self):
        packed=b'\x11\x07\0\0\x40A\x50\0'
        self.assertEqual(decompress_lz11(packed),b'A'*7)
        self.assertEqual(reencode_lz11_same_size(packed,b'A'*7),packed)
        for edited in [b'BAAAAAA',b'ABAAAAA',b'BBBBBBB']:
            with self.subTest(edited=edited):self.assertEqual(decompress_lz11(reencode_lz11_same_size(packed,edited)),edited)
        with self.assertRaises(ValueError):reencode_lz11_same_size(packed,b'short')

    def test_lz10_flag_boundaries_and_overlap_roundtrip(self):
        from kwce.channels import load_library,compress_lz10
        load_library()
        from libWiiPy.archive import decompress_lz77
        import random
        rng=random.Random(117)
        for raw in[b'A'*1000,bytes(range(256))*20,bytes(rng.randrange(12)for _ in range(4097)),b'abcabcXabcabcabcabcY'*70]:
            encoded=compress_lz10_optimal(raw)
            self.assertEqual(decompress_lz77(encoded),raw)
            self.assertLessEqual(len(encoded),len(compress_lz10(raw)))
        with self.assertRaises(ValueError):compress_lz10_optimal(bytes(1024*1024+1))

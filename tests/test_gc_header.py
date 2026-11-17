import unittest
from pathlib import Path
from kwce.gc_header import patch_gc_header,MESSAGE
from kwce.formats import U8

ROOT=Path(__file__).resolve().parents[1]

class GCHeaderTests(unittest.TestCase):
    def test_wrong_resource_refused(self):
        with self.assertRaises(ValueError):patch_gc_header(bytes(256))

    @unittest.skipUnless((ROOT/'workspace/experiments/gc-native-v4/menu-resource.app').exists(),'local resources required')
    def test_explicit_linebreak_preserves_every_other_byte(self):
        before=(ROOT/'workspace/experiments/gc-native-v4/menu-resource.app').read_bytes()
        after,record=patch_gc_header(before)
        self.assertEqual(len(before),len(after))
        self.assertEqual(sum(a!=b for a,b in zip(before,after)),1)
        self.assertIn('닌텐도 \n게임큐브'.encode('utf-16-be'),U8(after).get(MESSAGE))
        for name in U8(before).files:
            if name!=MESSAGE:self.assertEqual(U8(before).get(name),U8(after).get(name))
        with self.assertRaises(ValueError):patch_gc_header(after)

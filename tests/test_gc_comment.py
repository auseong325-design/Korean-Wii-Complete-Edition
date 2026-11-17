"""Patch containment tests. PPC behavior/fonts require the separate UI check."""
import hashlib,json,struct,unittest
from pathlib import Path
from kwce.gc_native import patch_gc_native,dol_offset
from kwce.gc_comment import build_decoder,ADDRESS

ROOT=Path(__file__).resolve().parents[1]

class GCCommentTests(unittest.TestCase):
    def test_comment_mode_requires_japanese_cards(self):
        with self.assertRaises(ValueError):patch_gc_native(bytes(256),japanese_comments=True)

    @unittest.skipUnless((ROOT/'workspace/console-baseline/menu-original-43K.dol').exists(),'local original required')
    def test_adapter_preserves_disabled_map_error_and_unrelated_bytes(self):
        original=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
        old,_=patch_gc_native(original,japanese_cards=True)
        new,detail=patch_gc_native(original,japanese_cards=True,japanese_comments=True)
        blob,record=build_decoder(ROOT)
        start=dol_offset(original,ADDRESS);call=dol_offset(original,0x813cd634)
        self.assertLessEqual(len(blob),0x200)
        self.assertEqual(new[start:start+len(blob)],blob)
        for i,(a,b) in enumerate(zip(old,new)):
            if a!=b:self.assertTrue(start<=i<start+len(blob) or call<=i<call+4)
        self.assertEqual(new[dol_offset(new,0x81545860):dol_offset(new,0x81545874)],old[dol_offset(old,0x81545860):dol_offset(old,0x81545874)])
        self.assertEqual(new[dol_offset(new,0x81545adc):dol_offset(new,0x81545b34)],old[dol_offset(old,0x81545adc):dol_offset(old,0x81545b34)])
        self.assertEqual(detail['instructions_changed'],9)
        self.assertEqual(len(new),len(old))

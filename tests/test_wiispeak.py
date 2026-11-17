import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
BASE = ROOT / 'workspace/channels/wiispeak'


def available():
    return (BASE / 'originals/wiispeak-korea-v512.wad').exists() and (BASE / 'hardware-v1/build-manifest.json').exists()


@unittest.skipUnless(available(), 'ignored Wii Speak originals/build not present')
class WiiSpeakWiimmfiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kwce.channels import load_library
        from kwce import bspatch
        from kwce.wiiroom_formats import decompress_lz11
        from kwce.wiispeak_wiimmfi import port
        lib = load_library()

        def content1(name):
            t = lib.title.Title()
            t.load_wad((BASE / 'originals' / name).read_bytes())
            return t.get_content_by_index(1)
        kr_c, jp_c = content1('wiispeak-korea-v512.wad'), content1('wiispeak-japan-v512.wad')
        cls.kr = decompress_lz11(kr_c)
        jp_new = decompress_lz11(bspatch.apply(jp_c, (BASE / 'references/wiilink-patcher/bsdiff__ws__WiiSpeak_1_Japan.bsdiff').read_bytes()))
        cls.out, cls.record = port(cls.kr, decompress_lz11(jp_c), jp_new)

    def test_no_nintendo_wfc_hosts_or_https_left(self):
        self.assertEqual(self.out.count(b'nintendowifi.net'), 0)
        self.assertEqual(self.out.count(b'https://'), 0)
        self.assertEqual(self.kr.count(b'nintendowifi.net'), self.out.count(b'wiimmfi.de'))
        self.assertIn(b'J-3-1\0', self.out)
        self.assertEqual(self.record['reference_strings_absent_in_korean'], ['%s.peerchat.gs.nintendowifi.net'])

    def test_dwc_length_check_words(self):
        words = [w['new'] for w in self.record['dwc_words']]
        self.assertEqual(words, ['88a10011', '28050080', '4181006c', '3ca05a00', '7c050000', '54e0400e', '60000000', '60000000',
                                 '38e00004', '7d033c2c', '9101000c', '89010011', '28080080', '60000000', '4181001c'])

    def test_changes_limited_to_strings_and_routine(self):
        from kwce.ppc_patch import to_file
        from kwce.wiispeak_wiimmfi import KR_FUNCTION, FUNCTION_SIZE
        lo = to_file(self.kr, KR_FUNCTION, FUNCTION_SIZE)
        for i, (a, b) in enumerate(zip(self.kr, self.out)):
            if a != b and not lo <= i < lo + FUNCTION_SIZE:
                # every other change is inside a printable network string slot
                start = i
                while start > 0 and self.kr[start - 1] != 0:
                    start -= 1
                self.assertTrue(any(k in self.kr[start:self.kr.index(b'\0', start)] for k in (b'nintendowifi', b'https://', b'RVL SDK')), hex(i))

    def test_hardware_build_reproduces(self):
        import build_wiispeak
        wad, manifest = build_wiispeak.build()
        stored = json.loads((BASE / 'hardware-v1/build-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(hashlib.sha256(wad).hexdigest(), stored['wad_sha256'])
        self.assertEqual(stored['changed_contents'], [1])
        self.assertFalse(stored['hardware_success_verified'])


if __name__ == '__main__':
    unittest.main()

"""Public beta edition README (scripts/export_rc_hardware.public_readme): personal wording must all be swapped."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import export_rc_hardware as rc  # noqa: E402

V51 = ROOT / 'workspace/hardware/kwce-rc-sd-v51/KWCE-RC-README-ko.txt'


@unittest.skipUnless(V51.is_file(), 'personal 1.0.9 package not present')
class PublicReadmeTest(unittest.TestCase):
    def test_personal_109_becomes_public(self):
        text = rc.public_readme(V51.read_text(encoding='utf-8').replace('\r\n', '\n'), {'version': '1.0.9'})
        self.assertTrue(text.startswith('KWCE 채널 설치 도구 (1.0.9 공개판, 베타)\n'))
        self.assertNotIn('개인', text)
        self.assertIn('"Japan (vote as Japan)" 판', text)

    def test_missing_sentence_stops_build(self):
        with self.assertRaises(SystemExit):
            rc.public_readme('KWCE 채널 설치 도구 (1.0.9, 개인용)\n', {'version': '1.0.9'})


if __name__ == '__main__':
    unittest.main()

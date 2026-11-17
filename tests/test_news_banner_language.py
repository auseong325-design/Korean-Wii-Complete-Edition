"""News v31: the Wii Menu banner/icon scripts always use the saved news language."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V30 = ROOT / 'workspace/channels/news/build-v30/news-ko-personal.wad'
V31 = ROOT / 'workspace/channels/news/build-v31/news-ko-personal.wad'


def contents(path):
    from kwce.channels import load_library
    t = load_library().title.Title(); t.load_wad(path.read_bytes())
    return [t.get_content_by_index(i) for i in range(len(t.tmd.content_records))]


@unittest.skipUnless(V30.is_file() and V31.is_file(), 'News v30/v31 builds not present')
class NewsBannerLanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old, cls.new = contents(V30), contents(V31)

    def test_only_script_contents_change(self):
        self.assertEqual([i for i in range(len(self.old)) if self.old[i] != self.new[i]], [4, 5])

    def test_each_script_differs_only_in_the_branch(self):
        from kwce.channels import ChannelArchive
        from kwce.news_banner_language import EDITS, CODE_BASE, _decompress_lz10
        for index, path, pc, old in EDITS:
            with self.subTest(path=path):
                a = _decompress_lz10(ChannelArchive(self.old[index]).get(path))
                b = _decompress_lz10(ChannelArchive(self.new[index]).get(path))
                diff = [i for i in range(len(a)) if a[i] != b[i]]
                self.assertEqual(len(a), len(b))
                self.assertEqual(diff, [CODE_BASE + pc, CODE_BASE + pc + 1])
                self.assertEqual(a[CODE_BASE + pc:CODE_BASE + pc + 2], old)
                self.assertEqual(b[CODE_BASE + pc:CODE_BASE + pc + 2], b'\x2b\x2b')
                self.assertEqual(a[CODE_BASE + pc - 1], 0x10)   # EQ of saved vs console language

    def test_other_archive_files_are_unchanged(self):
        from kwce.channels import ChannelArchive
        for index in (4, 5):
            a, b = ChannelArchive(self.old[index]), ChannelArchive(self.new[index])
            self.assertEqual(set(a.files), set(b.files))
            for name in a.files:
                if not name.endswith('.cs.lz7'):
                    self.assertEqual(a.get(name), b.get(name))


if __name__ == '__main__':
    unittest.main()

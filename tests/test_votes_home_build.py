"""Votes HOME-dialog fix (build-v21): in-place U8 replacement and the stored build against its parent."""
import json
import re
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from kwce.channels import ChannelArchive, load_library
from build_votes_home import replace_shrinking, build, VOTES, NAME


def u8(files):
    """Tiny U8: root, directory 'Channel', then the given (name, bytes) files inside it."""
    names = b'\0Channel\0' + b''.join(n.encode() + b'\0' for n, _ in files)
    count = 2 + len(files)
    header = count * 12 + len(names)
    start = (0x20 + header + 31) & ~31
    out = bytearray(start)
    struct.pack_into('>4I', out, 0, 0x55aa382d, 0x20, header, start)
    struct.pack_into('>III', out, 0x20, 0x01000000, 0, count)
    struct.pack_into('>III', out, 0x2c, 0x01000001, 0, count)
    name_at, data_at = 9, start
    for i, (name, payload) in enumerate(files):
        struct.pack_into('>III', out, 0x38 + 12 * i, name_at, data_at, len(payload))
        name_at += len(name) + 1
        out.extend(bytes(data_at - len(out)))
        out.extend(payload)
        data_at = (len(out) + 31) & ~31
    out[0x20 + count * 12:0x20 + header] = names
    return bytes(out)


class InPlaceReplacementTests(unittest.TestCase):
    def archive(self):
        return ChannelArchive(u8([('a.csv', b'A' * 40), ('b.bin', b'B' * 33)]))

    def test_shorter_file_keeps_offsets_length_and_neighbours(self):
        before = self.archive()
        after = ChannelArchive(replace_shrinking(before, 'Channel/a.csv', b'xy' * 5))
        self.assertEqual(after.get('Channel/a.csv'), b'xy' * 5)
        self.assertEqual(after.get('Channel/b.bin'), b'B' * 33)
        self.assertEqual(len(after.data), len(before.data))
        self.assertEqual({n: o for n, (o, s) in after.files.items()}, {n: o for n, (o, s) in before.files.items()})

    def test_freed_bytes_are_zeroed(self):
        before = self.archive()
        offset, size = before.files['Channel/a.csv']
        data = replace_shrinking(before, 'Channel/a.csv', b'Z' * 10)
        self.assertEqual(data[offset + 10:offset + size], bytes(size - 10))

    def test_same_size_is_allowed_and_growth_is_refused(self):
        before = self.archive()
        self.assertEqual(ChannelArchive(replace_shrinking(before, 'Channel/a.csv', b'C' * 40)).get('Channel/a.csv'), b'C' * 40)
        with self.assertRaises(ValueError):
            replace_shrinking(before, 'Channel/a.csv', b'D' * 41)


@unittest.skipUnless((VOTES / 'build-v20' / NAME).is_file() and (VOTES / 'build-v21' / NAME).is_file(), 'votes build-v20/v21 not present')
class StoredBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib = load_library()
        cls.titles = []
        for revision in (20, 21):
            title = lib.title.Title()
            title.load_wad((VOTES / f'build-v{revision}' / NAME).read_bytes())
            cls.titles.append(title)

    def contents(self, title):
        return [title.get_content_by_index(i) for i in range(14)]

    def test_only_content_10_differs_and_keeps_its_length(self):
        old, new = (self.contents(t) for t in self.titles)
        self.assertEqual([i for i in range(14) if old[i] != new[i]], [10])
        self.assertEqual(len(old[10]), len(new[10]))
        self.assertEqual(old[1], new[1])    # the executable with the country disguise

    def test_only_the_two_message_tables_changed_and_are_korean(self):
        old, new = (ChannelArchive(self.contents(t)[10]) for t in self.titles)
        self.assertEqual([n for n in old.files if old.get(n) != new.get(n)], ['Channel/home.csv', 'Channel/home_nosave.csv'])
        self.assertTrue(all(old.files[n][0] == new.files[n][0] for n in old.files))
        cells = re.findall(r'"([^"]*)"', new.get('Channel/home_nosave.csv')[2:].decode('utf-16-be'))
        self.assertEqual(len(cells), 28)
        self.assertEqual(cells[2 * 7:3 * 7], ['Wii 메뉴로 돌아가시겠습니까?'] * 7)
        self.assertEqual(cells[3 * 7:4 * 7], ['리셋하시겠습니까?'] * 7)

    def test_generalised_builder_still_reproduces_the_stored_build(self):
        """build_votes_home.py serves votes and mii-contest now; its votes output must stay byte-identical."""
        wad, meta, _ = build('votes')
        self.assertEqual(wad, (VOTES / 'build-v21' / NAME).read_bytes())
        self.assertEqual(json.dumps(meta, ensure_ascii=False, indent=2).encode('utf-8') + b'\n',
                         (VOTES / 'build-v21' / 'build-manifest.json').read_bytes())


if __name__ == '__main__':
    unittest.main()

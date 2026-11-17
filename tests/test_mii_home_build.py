"""Mii Contest HOME-dialog fix (build-v31): the stored build against its parent build-v30."""
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from kwce.channels import ChannelArchive, load_library
from kwce.hardware import hardware_wad
from kwce.home_menu import home_font_mapping, missing_glyphs
import build_votes_home

MII = ROOT / 'workspace/channels/mii-contest'
SPEC = build_votes_home.CHANNELS['mii-contest']
NAME = SPEC['name']
HOME = SPEC['home_content']
TABLES = [name for name, _ in SPEC['csv_files']]


def cells(raw):
    return re.findall(r'"([^"]*)"', raw[2:].decode('utf-16-be'))


class SpecTests(unittest.TestCase):
    def test_channel_table_names_the_parent_and_the_new_revision(self):
        self.assertEqual((SPEC['dir'], SPEC['base'], SPEC['revision'], HOME), ('mii-contest', 30, 31, 4))
        self.assertEqual(TABLES, ['content4/Basic/HBM/home_nosave.csv', 'content4/Basic/HBM/home.csv'])
        self.assertEqual(SPEC['unchanged_contents'], (1,))

    def test_votes_entry_is_the_one_that_produced_build_v21(self):
        votes = build_votes_home.CHANNELS['votes']
        self.assertEqual((votes['base'], votes['revision'], votes['home_content'], votes['unchanged_contents']), (20, 21, 10, (1, 4)))

    def test_unknown_channel_is_refused(self):
        with self.assertRaises(KeyError):
            build_votes_home.build('nintendo')


@unittest.skipUnless((MII / 'build-v30' / NAME).is_file() and (MII / 'build-v31' / NAME).is_file(), 'mii-contest build-v30/v31 not present')
class StoredBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib = load_library()
        cls.titles, cls.contents, cls.wads = [], [], []
        for revision in (30, 31):
            wad = (MII / f'build-v{revision}' / NAME).read_bytes()
            title = lib.title.Title()
            title.load_wad(wad)
            cls.wads.append(wad)
            cls.titles.append(title)
            cls.contents.append([title.get_content_by_index(i) for i in range(8)])
        cls.manifest = json.loads((MII / 'build-v31' / 'build-manifest.json').read_text(encoding='utf-8'))
        cls.parent_manifest = json.loads((MII / 'build-v30' / 'build-manifest.json').read_text(encoding='utf-8'))

    def test_only_content_4_differs_and_keeps_its_length(self):
        old, new = self.contents
        self.assertEqual([i for i in range(8) if old[i] != new[i]], [4])
        self.assertEqual(len(old[4]), len(new[4]))
        self.assertEqual(old[1], new[1])    # the executable
        self.assertEqual(len(self.wads[0]), len(self.wads[1]))

    def test_title_identity_is_unchanged(self):
        ident = lambda t: (t.tmd.region, t.tmd.title_id, t.tmd.title_version, t.tmd.ios_tid, len(t.tmd.content_records))
        self.assertEqual(ident(self.titles[0]), ident(self.titles[1]))

    def test_only_the_two_message_tables_changed_in_place(self):
        old, new = (ChannelArchive(c[4]) for c in self.contents)
        self.assertEqual(sorted(n for n in old.files if old.get(n) != new.get(n)), sorted(TABLES))
        self.assertTrue(all(old.files[n][0] == new.files[n][0] for n in old.files))
        for name in TABLES:
            offset, size = new.files[name]
            self.assertLess(size, old.files[name][1])
            freed = self.contents[1][4][offset + size:offset + old.files[name][1]]
            self.assertEqual(freed, bytes(len(freed)))      # freed bytes are zero

    def test_tables_are_korean_in_all_seven_columns(self):
        new = ChannelArchive(self.contents[1][4])
        for name, warning in zip(TABLES, (False, True)):
            c = cells(new.get(name))
            self.assertEqual(len(c), 28)
            for row in range(4):
                self.assertEqual(len(set(c[row * 7:(row + 1) * 7])), 1, name)     # same text in every language slot
            self.assertTrue(c[2 * 7].startswith('Wii 메뉴로 돌아가시겠습니까?'))
            self.assertTrue(c[3 * 7].startswith('리셋하시겠습니까?'))
            self.assertEqual('사라집니다' in c[2 * 7], warning)

    def test_every_korean_glyph_is_in_the_font_of_the_archive_the_executable_loads(self):
        new = ChannelArchive(self.contents[1][4])
        mapping = home_font_mapping(new.get(SPEC['font_archive']))
        self.assertGreater(len(mapping), 50)
        for name in TABLES:
            self.assertEqual(missing_glyphs(cells(new.get(name)), mapping), [])
        # the other five language slots share that very archive (U8 aliases), so every slot is covered
        for lang in ('FRA', 'GER', 'ITA', 'NED', 'SPA'):
            self.assertEqual(new.get(f'content4/Basic/HBM/homeBtn_{lang}.szs'), new.get(SPEC['font_archive']))

    def test_manifest_describes_the_build(self):
        m = self.manifest
        self.assertEqual((m['revision'], m['parent_revision'], m['changed_from_parent']), (31, 30, [4]))
        self.assertEqual(m['wad_sha256'], hashlib.sha256(self.wads[1]).hexdigest())
        self.assertEqual(self.parent_manifest['wad_sha256'], hashlib.sha256(self.wads[0]).hexdigest())
        fix = m['home_dialog_fix']
        self.assertEqual([f['file'] for f in fix['files']], TABLES)
        self.assertTrue(all(f['font_coverage_verified'] and f['translated_columns'] == list(range(7)) for f in fix['files']))
        self.assertTrue(fix['content_1_unchanged'] and not fix['hardware_verified'])
        self.assertFalse(m['runtime_verified'])
        self.assertEqual(fix['content_4_length'], len(self.contents[1][4]))

    def test_rebuild_reproduces_the_stored_wad_and_manifest(self):
        wad, meta, _ = build_votes_home.build('mii-contest')
        self.assertEqual(wad, self.wads[1])
        self.assertEqual(json.dumps(meta, ensure_ascii=False, indent=2).encode('utf-8') + b'\n',
                         (MII / 'build-v31' / 'build-manifest.json').read_bytes())

    def test_hardware_check_passes_with_the_parents_local_reference_counts(self):
        original = (MII / 'originals/mii-contest-usa-wiilink-archive.wad').read_bytes()
        _, record = hardware_wad(self.wads[1], original)
        _, parent = hardware_wad(self.wads[0], original)
        self.assertEqual(record['local_reference_counts'], parent['local_reference_counts'])
        self.assertEqual(record['title_id'], '0001000148415045')


if __name__ == '__main__':
    unittest.main()

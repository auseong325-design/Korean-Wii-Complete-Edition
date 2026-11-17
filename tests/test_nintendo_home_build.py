"""Nintendo Channel HOME Menu fixes: build-v16 (default language slot, content 6) and build-v17 (content 5 table),
each stored build against its parent."""
import argparse
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from kwce.channels import ChannelArchive, load_library
from kwce.hardware import hardware_wad
from kwce.home_menu import (KOREAN_SHARED, KOREAN_SHARED_SHA256, SOURCES, home_font_mapping, korean_default_home,
                            korean_dialog_messages, korean_official_table_home, missing_glyphs)
import build_nintendo

NINTENDO = ROOT / 'workspace/channels/nintendo'
NAME = build_nintendo.OUTPUT
ARCHIVES = ['HomeButton2/LZ77_homeBtn.arc', 'HomeButton3/LZ77_homeBtn.arc']
TABLES = ['HomeButton2/home.csv', 'HomeButton2/home_nosave.csv', 'HomeButton3/home.csv', 'HomeButton3/home_nosave.csv']


def cells(raw):
    return re.findall(r'"([^"]*)"', raw[2:].decode('utf-16-be'))


class RevisionGateTests(unittest.TestCase):
    def test_revisions_16_and_17_are_derived_from_their_predecessors_and_nothing_else_is(self):
        self.assertEqual(build_nintendo.DERIVED, {16: 15, 17: 16})
        self.assertEqual((build_nintendo.HOME_CONTENT, build_nintendo.TABLE_CONTENT), (6, 5))

    def test_other_new_revisions_have_no_builder(self):
        with self.assertRaises(SystemExit):
            build_nintendo.derived_main(argparse.Namespace(revision=18, reproduce=False))

    def test_reproduce_flag_is_refused_below_16(self):
        with mock.patch.object(sys, 'argv', ['build_nintendo.py', '--revision', '15', '--reproduce']):
            with self.assertRaises(SystemExit) as stop:
                build_nintendo.main()
        self.assertIn('build_nintendo_banner_v9.py', str(stop.exception))

    def test_pinned_korean_source_is_the_one_the_stored_builds_used(self):
        self.assertEqual(hashlib.sha256(KOREAN_SHARED.read_bytes()).hexdigest(), KOREAN_SHARED_SHA256)


@unittest.skipUnless((NINTENDO / 'build-v15' / NAME).is_file() and (NINTENDO / 'build-v16' / NAME).is_file(), 'nintendo build-v15/v16 not present')
class StoredBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib = load_library()
        cls.titles, cls.contents, cls.wads = [], [], []
        for revision in (15, 16):
            wad = (NINTENDO / f'build-v{revision}' / NAME).read_bytes()
            title = lib.title.Title()
            title.load_wad(wad)
            cls.wads.append(wad)
            cls.titles.append(title)
            cls.contents.append([title.get_content_by_index(i) for i in range(12)])
        cls.manifest = json.loads((NINTENDO / 'build-v16' / 'build-manifest.json').read_text(encoding='utf-8'))
        cls.parent_manifest = json.loads((NINTENDO / 'build-v15' / 'build-manifest.json').read_text(encoding='utf-8'))

    def test_only_content_6_differs_and_keeps_its_length(self):
        old, new = self.contents
        self.assertEqual([i for i in range(12) if old[i] != new[i]], [6])
        self.assertEqual(len(old[6]), len(new[6]))
        self.assertEqual(old[1], new[1])    # executable
        self.assertEqual(len(self.wads[0]), len(self.wads[1]))

    def test_title_identity_is_unchanged(self):
        ident = lambda t: (t.tmd.region, t.tmd.title_id, t.tmd.title_version, t.tmd.ios_tid, len(t.tmd.content_records))
        self.assertEqual(ident(self.titles[0]), ident(self.titles[1]))

    def test_exactly_the_two_default_archives_and_four_tables_changed_in_place(self):
        old, new = (ChannelArchive(c[6]) for c in self.contents)
        self.assertEqual(sorted(n for n in old.files if old.get(n) != new.get(n)), sorted(ARCHIVES + TABLES))
        self.assertTrue(all(old.files[n][0] == new.files[n][0] for n in old.files))
        for name in ARCHIVES + TABLES:
            offset, size = new.files[name]
            self.assertLess(size, old.files[name][1])
            freed = self.contents[1][6][offset + size:offset + old.files[name][1]]
            self.assertEqual(freed, bytes(len(freed)))      # freed bytes are zero

    def test_default_archives_are_the_consoles_own_korean_archives(self):
        new = ChannelArchive(self.contents[1][6])
        korean = ChannelArchive(KOREAN_SHARED.read_bytes())
        for folder, source in SOURCES.items():
            self.assertEqual(new.get(f'{folder}/LZ77_homeBtn.arc'), korean.get(source))
            # and the six language slots that build-v15 already filled hold the same archive
            for lang in ('ENG', 'FRA', 'GER', 'ITA', 'NED', 'SPA'):
                self.assertEqual(new.get(f'{folder}/LZ77_homeBtn_{lang}.arc'), korean.get(source))

    def test_tables_are_korean_in_all_seven_columns(self):
        new = ChannelArchive(self.contents[1][6])
        messages = korean_dialog_messages()
        for name in TABLES:
            c = cells(new.get(name))
            self.assertEqual(len(c), 28)
            for row in range(4):
                self.assertEqual(len(set(c[row * 7:(row + 1) * 7])), 1, name)
                self.assertTrue(c[row * 7].startswith(messages[row]), name)
            self.assertEqual('사라집니다' in c[2 * 7], not name.endswith('_nosave.csv'))

    def test_every_korean_glyph_is_in_the_font_of_its_default_archive(self):
        new = ChannelArchive(self.contents[1][6])
        for name in TABLES:
            mapping = home_font_mapping(new.get(f"{name.split('/')[0]}/LZ77_homeBtn.arc"))
            self.assertGreater(len(mapping), 50)
            self.assertEqual(missing_glyphs(cells(new.get(name)), mapping), [], name)

    def test_the_fix_cannot_be_applied_twice(self):
        with self.assertRaises(ValueError):
            korean_default_home(self.contents[1][6])

    def test_manifest_describes_the_build(self):
        m, p = self.manifest, self.parent_manifest
        self.assertEqual((m['revision'], m['parent_revision'], m['source_build'], m['changed_from_parent']), (16, 15, 'build-v15', [6]))
        self.assertEqual(m['wad_sha256'], hashlib.sha256(self.wads[1]).hexdigest())
        self.assertEqual(p['wad_sha256'], hashlib.sha256(self.wads[0]).hexdigest())
        self.assertEqual(m['menu_art'], p['menu_art'])        # banner, icon and opening are v15's
        self.assertEqual(m['home_menu'], p['home_menu'])
        fix = m['home_default_fix']
        self.assertEqual([a['file'] for a in fix['default_archives']], ARCHIVES)
        self.assertEqual(sorted(t['file'] for t in fix['dialog_csv']), sorted(TABLES))
        self.assertTrue(all(t['font_coverage_verified'] and t['translated_columns'] == list(range(7)) for t in fix['dialog_csv']))
        self.assertTrue(fix['content_1_unchanged'] and fix['in_place'] and not fix['hardware_verified'])
        self.assertEqual(fix['content_length'], len(self.contents[1][6]))
        self.assertFalse(m['runtime_verified'])

    def test_rebuild_reproduces_the_stored_wad_and_manifest(self):
        wad, meta = build_nintendo.derived_build(16)
        self.assertEqual(wad, self.wads[1])
        self.assertEqual(json.dumps(meta, ensure_ascii=False, indent=2).encode('utf-8') + b'\n',
                         (NINTENDO / 'build-v16' / 'build-manifest.json').read_bytes())

    def test_hardware_check_passes_with_the_parents_local_reference_counts(self):
        original = (NINTENDO / 'originals/nintendo-usa-wiilink-archive.wad').read_bytes()
        _, record = hardware_wad(self.wads[1], original)
        _, parent = hardware_wad(self.wads[0], original)
        self.assertEqual(record['local_reference_counts'], parent['local_reference_counts'])
        self.assertEqual(record['title_id'], '0001000148415445')


@unittest.skipUnless((NINTENDO / 'build-v16' / NAME).is_file() and (NINTENDO / 'build-v17' / NAME).is_file(), 'nintendo build-v16/v17 not present')
class StoredTableBuildTests(unittest.TestCase):
    """build-v17 = build-v16 + the ten-column table in content 5 that the executable really loads (group 3)."""

    @classmethod
    def setUpClass(cls):
        lib = load_library()
        cls.titles, cls.contents, cls.wads = [], [], []
        for revision in (16, 17):
            wad = (NINTENDO / f'build-v{revision}' / NAME).read_bytes()
            title = lib.title.Title()
            title.load_wad(wad)
            cls.wads.append(wad)
            cls.titles.append(title)
            cls.contents.append([title.get_content_by_index(i) for i in range(12)])
        cls.manifest = json.loads((NINTENDO / 'build-v17' / 'build-manifest.json').read_text(encoding='utf-8'))

    def test_only_content_5_differs_and_keeps_its_length(self):
        old, new = self.contents
        self.assertEqual([i for i in range(12) if old[i] != new[i]], [5])
        self.assertEqual(len(old[5]), len(new[5]))
        self.assertEqual(old[1], new[1])    # executable
        self.assertEqual(old[6], new[6])    # the Korean default archives and tables of build-v16
        self.assertEqual(len(self.wads[0]), len(self.wads[1]))

    def test_only_home_csv_changed_in_place(self):
        old, new = (ChannelArchive(c[5]) for c in self.contents)
        self.assertEqual([n for n in old.files if old.get(n) != new.get(n)], ['HomeButton3/home.csv'])
        self.assertTrue(all(old.files[n][0] == new.files[n][0] for n in old.files))
        offset, size = new.files['HomeButton3/home.csv']
        freed = self.contents[1][5][offset + size:offset + old.files['HomeButton3/home.csv'][1]]
        self.assertEqual(freed, bytes(len(freed)))

    def test_slots_0_to_6_are_the_official_korean_text_and_the_other_columns_stay(self):
        old, new = (cells(ChannelArchive(c[5]).get('HomeButton3/home.csv')) for c in self.contents)
        self.assertEqual((len(old), len(new)), (40, 40))
        for row in range(4):
            for col in range(7):
                self.assertEqual(new[row * 10 + col], old[row * 10 + 9])
            for col in (7, 8, 9):
                self.assertEqual(new[row * 10 + col], old[row * 10 + col])
        self.assertEqual(new[2 * 10], 'Wii 메뉴로 돌아가시겠습니까?')

    def test_every_korean_glyph_is_in_the_font_of_the_default_archive(self):
        mapping = home_font_mapping(ChannelArchive(self.contents[1][6]).get('HomeButton3/LZ77_homeBtn.arc'))
        new = cells(ChannelArchive(self.contents[1][5]).get('HomeButton3/home.csv'))
        self.assertEqual(missing_glyphs([new[r * 10 + c] for r in range(4) for c in range(7)], mapping), [])

    def test_manifest_describes_the_build(self):
        m = self.manifest
        self.assertEqual((m['revision'], m['parent_revision'], m['source_build'], m['changed_from_parent']), (17, 16, 'build-v16', [5]))
        self.assertEqual(m['wad_sha256'], hashlib.sha256(self.wads[1]).hexdigest())
        fix = m['home_table_fix']
        self.assertEqual((fix['file'], fix['translated_columns'], fix['source_column']), ('HomeButton3/home.csv', list(range(7)), 9))
        self.assertTrue(fix['content_1_unchanged'] and fix['in_place'] and not fix['hardware_verified'])
        self.assertIn('home_default_fix', m)      # v16's record is inherited
        self.assertFalse(m['runtime_verified'])

    def test_the_fix_cannot_be_applied_twice(self):
        with self.assertRaises(ValueError):
            korean_official_table_home(self.contents[1][5])

    def test_rebuild_reproduces_the_stored_wad_and_manifest(self):
        wad, meta = build_nintendo.derived_build(17)
        self.assertEqual(wad, self.wads[1])
        self.assertEqual(json.dumps(meta, ensure_ascii=False, indent=2).encode('utf-8') + b'\n',
                         (NINTENDO / 'build-v17' / 'build-manifest.json').read_bytes())

    def test_hardware_check_passes_with_the_parents_local_reference_counts(self):
        original = (NINTENDO / 'originals/nintendo-usa-wiilink-archive.wad').read_bytes()
        _, record = hardware_wad(self.wads[1], original)
        _, parent = hardware_wad(self.wads[0], original)
        self.assertEqual(record['local_reference_counts'], parent['local_reference_counts'])


if __name__ == '__main__':
    unittest.main()

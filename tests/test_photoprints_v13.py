"""Photo Prints revision 13: Korean HOME dialogs, operations-guide chrome and exit prompt.

Synthetic tests always run. Tests marked 'local data' use the project's own
ignored builds and are skipped when those files are absent.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import photoprints_home_guide as hg  # noqa: E402

BASE = ROOT / 'workspace/channels/photoprints'
PAIRS = ((BASE / 'build-v12/photoprints-ko-local-test.wad', BASE / 'build-v13/photoprints-ko-local-test.wad'),
         (BASE / 'hardware-v8/photoprints-ko-hardware-test.wad', BASE / 'hardware-v9/photoprints-ko-hardware-test.wad'))


def _csv(rows):
    return b'\xfe\xff' + ''.join('\t'.join(f'"{c}"' for c in row) + '\r\n' for row in rows).encode('utf-16-be')


def _cells(data):
    return re.findall(r'"([^"]*)"', data[2:].decode('utf-16-be'))


class Csv(unittest.TestCase):
    def test_home_csv_fills_selectable_columns(self):
        rows = [[f'r{r}c{c}' for c in range(10)] for r in range(4)]
        for r in range(4):
            rows[r][9] = f'한국어 {r}\r\n둘째 줄'
        out, rec = hg.korean_home_csv(_csv(rows))
        cells = _cells(out)
        for r in range(4):
            self.assertEqual(cells[r * 10:r * 10 + 7], [rows[r][9]] * 7)       # languages 0-6 -> Korean
            self.assertEqual(cells[r * 10 + 7:r * 10 + 10], rows[r][7:10])      # SC/TC/KO untouched
        self.assertEqual(hg._skeleton(out), hg._skeleton(_csv(rows)))
        self.assertEqual(rec['filled_columns'], list(range(7)))

    def test_home_csv_rejects(self):
        rows = [[f'r{r}c{c}' for c in range(10)] for r in range(4)]
        with self.assertRaises(ValueError):          # no Korean column
            hg.korean_home_csv(_csv(rows))
        with self.assertRaises(ValueError):          # not 4 x 10
            hg.korean_home_csv(_csv(rows[:3]))

    def test_network_csv(self):
        original = _csv([['ゲームを終了します。\r\nよろしいですか？', 'This will quit the game. Proceed?', 'DE', 'FR', 'ES', 'IT', 'NL']])
        out, rec = hg.korean_network_csv(original)
        self.assertEqual(_cells(out), [hg.PROMPT] * 7)
        self.assertEqual(rec['columns'], 7)
        with self.assertRaises(ValueError):
            hg.korean_network_csv(_csv([['x'] * 7]))
        with self.assertRaises(ValueError):          # build-v12's ten-column variant is not a valid source
            hg.korean_network_csv(_csv([['ゲームを終了します。', 'This will quit the game.'] + ['x'] * 8]))

    def test_prompt(self):
        self.assertEqual(hg.PROMPT.count('\r\n'), 2)  # three lines, like the original Japanese prompt
        self.assertNotIn('"', hg.PROMPT)


@unittest.skipUnless(all(p.exists() for pair in PAIRS for p in pair), 'local data')
class Revision13(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kwce.channels import load_library
        cls.lib = load_library()

    def load(self, path):
        t = self.lib.title.Title()
        t.load_wad(path.read_bytes())
        return t

    def test_reproduces(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import build_photoprints_v13 as b13
        (local, local_meta), (hardware, hardware_meta), _ = b13.build()
        self.assertEqual(local, PAIRS[0][1].read_bytes())
        self.assertEqual(hardware, PAIRS[1][1].read_bytes())
        stored = json.loads((BASE / 'build-v13/build-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(stored['wad_sha256'], local_meta['wad_sha256'])
        self.assertFalse(stored['full_localization_complete'] or stored['hardware_success_verified'] or stored['home_guide_runtime_verified'])

    def test_dol_language_facts(self):
        from kwce.wiiroom_formats import decompress_lz11
        for _, path in PAIRS:
            facts = hg.home_language_facts(decompress_lz11(self.load(path).get_content_by_index(1)))
            self.assertEqual(facts['korean_console_home_language'], 1)

    def test_scope_and_text(self):
        from kwce.channels import ChannelArchive
        from kwce.channel_font import font_data
        from kwce.hardware import local_reference_counts
        from libWiiPy.archive import decompress_lz77
        shared = []
        for old_path, new_path in PAIRS:
            old, new = self.load(old_path), self.load(new_path)
            n = old.tmd.num_contents
            self.assertEqual([i for i in range(n) if old.get_content_by_index(i) != new.get_content_by_index(i)], [2, 3, 7])
            self.assertEqual(local_reference_counts(new), local_reference_counts(old))
            self.assertEqual(new.tmd.region, old.tmd.region)
            a2, b2 = ChannelArchive(old.get_content_by_index(2)), ChannelArchive(new.get_content_by_index(2))
            self.assertEqual(sorted(f for f in a2.files if a2.get(f) != b2.get(f)), [hg.HOME_CSV, hg.NETWORK])
            home = _cells(b2.get(hg.HOME_CSV))
            for r in range(4):
                self.assertEqual(set(home[r * 10:r * 10 + 7]), {home[r * 10 + 9]})
            self.assertEqual(_cells(b2.get(hg.NETWORK)), [hg.PROMPT] * 7)
            needed = {ord(c) for c in hg.PROMPT + ''.join(home[r * 10 + 9] for r in range(4)) if ord(c) >= 32}
            # content 3: only the font inside each of the 14 HOME archives changed, and it covers every HOME text
            a3, b3 = ChannelArchive(old.get_content_by_index(3)), ChannelArchive(new.get_content_by_index(3))
            changed3 = [f for f in a3.files if a3.get(f) != b3.get(f)]
            self.assertEqual(len(changed3), 14)
            for name in changed3:
                x, y = ChannelArchive(decompress_lz77(a3.get(name))), ChannelArchive(decompress_lz77(b3.get(name)))
                self.assertEqual([p for p in x.files if x.get(p) != y.get(p)], [p for p in x.files if p.endswith('.brfnt')])
                font = [p for p in y.files if p.endswith('.brfnt')][0]
                self.assertTrue(needed <= set(font_data(y.get(font))[1]), name)
            # content 7: chrome textures in all seven guide archives, own fonts in four, nothing else
            a7, b7 = ChannelArchive(old.get_content_by_index(7)), ChannelArchive(new.get_content_by_index(7))
            fonts = 0
            for name in a7.files:
                x, y = ChannelArchive(decompress_lz77(a7.get(name))), ChannelArchive(decompress_lz77(b7.get(name)))
                diff = sorted(p.rsplit('/', 1)[-1] for p in x.files if x.get(p) != y.get(p))
                own = [p for p in y.files if p.endswith('.brfnt')]
                expected = sorted(['it_btn_01.tpl', 'it_net_wrd.tpl', 'it_ttl_wrd_a.tpl'] + [p.rsplit('/', 1)[-1] for p in own])
                self.assertEqual(diff, expected, name)
                for p in own:
                    fonts += 1
                    self.assertTrue(needed <= set(font_data(y.get(p))[1]), name)
                if name.endswith('_eng.arc'):
                    self.assertEqual(own, [])  # the archive a Korean console loads inherits the HOME font
            self.assertEqual(fonts, 4)
            shared.append([new.get_content_by_index(i) for i in (2, 3, 7)])
        self.assertEqual(shared[0], shared[1])  # local and hardware share the three contents
        self.assertTrue(self.load(PAIRS[1][1]).get_is_fakesigned())


if __name__ == '__main__':
    unittest.main()

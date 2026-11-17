"""Locks the RC6 finding for the Nintendo Channel Wii Menu icon (W-Nintendo): the channel script of
content 2 shows P_logoJ_00 for SC_LANG_KOREAN, so revisions 9-13 showed the Japanese logo on a Korean
console, and revision 14+ (P_logoJ_00 <-> P_logoE_00 swap) shows the Korean wordmark. Also checks the
revision 15 lettering stays clean (no closed counters, even weight). Read-only; skips without the
ignored workspace WADs.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'workspace/channels/nintendo'
RC6 = BASE / 'rc6'
sys.path.insert(0, str(RC6))
WADS = {n: BASE / f'build-v{n}/nintendo-ko-ui-test.wad' for n in (13, 14, 15)}
ORIGINAL = BASE / 'originals/nintendo-usa-wiilink-archive.wad'

try:
    from icon_language import icon_state, region_table
    from menu_rso_probe import imet, lz_unpack
    from kwce.channels import ChannelArchive, load_library
    from kwce import nintendo_menu_art_v9 as art
    from banner_sheet import unpack_meta
    HAVE = all(p.exists() for p in [*WADS.values(), ORIGINAL])
except Exception:  # pragma: no cover - workspace tools or WADs missing
    HAVE = False

LOGOS = {f'P_logo{k}_{n}' for k in ('J', 'E', 'F', 'Sp', 'G', 'I', 'N') for n in ('00', '01')}


@unittest.skipUnless(HAVE, 'Nintendo Channel WADs / rc6 tools not available')
class NintendoIconLanguageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib = load_library()
        cls.data = {n: p.read_bytes() for n, p in WADS.items()}
        original = lib.title.Title()
        original.load_wad(ORIGINAL.read_bytes())
        cls.original_icon = unpack_meta(original.get_content_by_index(0))['meta/icon.bin']
        head = imet(original.get_content_by_index(0))
        cls.script = lz_unpack(ChannelArchive(original.get_content_by_index(head['icon_cs'])).get('arc/icon.cs.lz7'))

    def test_channel_script_shows_the_j_pane_for_korean(self):
        hidden, table = region_table(self.script)
        self.assertTrue(LOGOS <= set(hidden))           # every logo pane is hidden first
        self.assertEqual(table[9], 'P_logoJ_00')        # SC_LANG_KOREAN
        self.assertEqual(table[0], 'P_logoJ_00')        # Japanese
        self.assertEqual(table[1], 'P_logoE_00')        # English

    def test_rc5_build_v13_shows_the_japanese_logo(self):
        state = icon_state(self.data[13], 9)
        self.assertEqual(state['visible_logo_panes'], {'P_logoJ_00': 'oh_proLogo_J_00.tpl'})
        self.assertEqual(state['archive'].get('arc/timg/oh_proLogo_J_00.tpl'),
                         self.original_icon.get('arc/timg/oh_proLogo_J_00.tpl'))

    def test_revision_14_and_15_show_the_korean_wordmark(self):
        originals = {self.original_icon.get('arc/timg/' + n) for n in ('oh_proLogo_J_00.tpl', 'oh_proLogo_E_00.tpl')}
        for n in (14, 15):
            state = icon_state(self.data[n], 9)
            self.assertEqual(state['visible_logo_panes'], {'P_logoJ_00': 'oh_proLogo_E_00.tpl'}, n)
            self.assertNotIn(state['archive'].get('arc/timg/oh_proLogo_E_00.tpl'), originals, n)
            self.assertTrue(state['has_lang_group'])    # KOR group (static icon) kept

    def test_only_revisions_14_plus_swap_the_icon_pane(self):
        for revision in range(9, 14):
            self.assertFalse(art.STYLES[revision].get('icon_script_pane', False))
        self.assertTrue(art.STYLES[14]['icon_script_pane'] and art.STYLES[15]['icon_script_pane'])

    def test_revision_15_lettering_is_clean_and_even(self):
        from logo_candidates import open_counters, stroke_px
        strokes = {}
        for syllable, (rgba, _, (left, right)) in art.glyphs(15).items():
            alpha = rgba.split()[3]
            self.assertEqual(open_counters(alpha), 0, syllable)          # e.g. ㅊ must not touch ㅏ in 채
            self.assertTrue(0 < left < right < art.TILE, syllable)
            strokes[syllable] = stroke_px(alpha)
        weights = [s for s, _ in strokes.values()]
        self.assertLess(max(weights) / min(weights), 1.15)              # the ㄹ of 널 stays open
        self.assertGreater(min(s / h for s, h in strokes.values()), 0.115)  # v13 was 0.10


if __name__ == '__main__':
    unittest.main()

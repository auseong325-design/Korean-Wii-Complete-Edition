"""Static guarantees for the Mii Contest long-sentence wrap audit (build-v25 narrowed fonts).

Proves, without Dolphin, that every localized message renders with no missing glyph (no tofu) and
that no explicit line is too wide for every message pane (no forced mid-line soft-wrap).  The live
layout of the paginated help/welcome screens is confirmed by the lead in Dolphin.
"""
import unittest
from pathlib import Path

from kwce import mii_contest_textfit as mt

ROOT = Path(__file__).resolve().parents[1]


class MiiWrapAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = mt.audit(ROOT)
        cls.coverage = mt.glyph_coverage(ROOT)

    def test_v25_font_is_narrowed(self):
        # build-v25 narrowed this channel's wbf1 Hangul to 0.9 (advance 가 22 -> 20).
        self.assertIn('가=20', self.report['font'])

    def test_three_message_panes_found(self):
        self.assertEqual(len(self.report['message_panes']), 3)

    def test_no_missing_glyphs(self):
        self.assertEqual(self.report['missing_glyphs'], '')
        for font, gap in self.coverage.items():
            self.assertEqual(gap, [], f'{font} missing {gap!r}')

    def test_no_line_overflows_every_pane(self):
        # A line too wide for even the widest pane would always soft-wrap mid-sentence.
        self.assertEqual(self.report['line_overflow_every_pane'], [])

    def test_message_count_matches_build(self):
        self.assertEqual(self.report['message_count'], 1260)

    def test_audit_is_deterministic(self):
        again = mt.audit(ROOT)
        self.assertEqual(again['line_overflow_every_pane'], self.report['line_overflow_every_pane'])
        self.assertEqual(again['missing_glyphs'], self.report['missing_glyphs'])


if __name__ == '__main__':
    unittest.main()

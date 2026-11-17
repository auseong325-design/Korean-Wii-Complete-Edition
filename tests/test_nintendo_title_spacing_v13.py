import unittest

from kwce import nintendo_menu_art_v9 as art


class NintendoTitleSpacingV13Test(unittest.TestCase):
    def test_ink_positions_give_exact_gaps_and_centre(self):
        inks = [(6.0, 49.0), (6.0, 49.0), (2.0, 53.0), (3.0, 48.0), (6.0, 49.0)]
        unit, centre = 0.825, -0.25
        xs = art.ink_positions(inks, unit, centre, 14.5, 32.0)
        left = [x + (l - art.TILE / 2) * unit for x, (l, r) in zip(xs, inks)]
        right = [x + (r - art.TILE / 2) * unit for x, (l, r) in zip(xs, inks)]
        gaps = [round((b - a) / unit, 6) for a, b in zip(right, left[1:])]
        self.assertEqual(gaps, [14.5, 14.5, 32.0, 14.5])
        self.assertAlmostEqual((left[0] + right[-1]) / 2, centre, places=6)

    def test_revision_13_keeps_v12_glyph_pixels(self):
        v12, v13 = art.glyphs(12), art.glyphs(13)
        for syllable, _, _, _ in art.TITLE:
            self.assertEqual(v12[syllable][0].tobytes(), v13[syllable][0].tobytes())
            left, right = v13[syllable][2]
            self.assertTrue(0 < left < right < art.TILE)
            # the box width revisions 9-12 spaced by is the advance box, wider than the ink
            self.assertGreater(v13[syllable][1], right - left)

    def test_older_revisions_do_not_use_ink_spacing(self):
        for revision in (9, 10, 11, 12):
            self.assertFalse(art.STYLES[revision].get('ink_spacing', False))
        self.assertTrue(art.STYLES[13]['ink_spacing'])


if __name__ == '__main__':
    unittest.main()

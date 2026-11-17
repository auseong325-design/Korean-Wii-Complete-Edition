"""R65 HOME frame: the console's own HOME geometry (43K NTSC) over DVD playback.

The patched source is rebuilt from the frozen r35 file with every kwce_home.cpp
replacement in order (R64 must give the pinned R64 source byte-for-byte). The
geometry itself is checked against the 43K numbers: EFB 640x456 on 456 lines,
projection +-304/+-416 by +-228, VI width 670/686 of 720.
"""
import hashlib
import json
import unittest
from pathlib import Path

from kwce.dvd_player_fork import patches

ROOT = Path(__file__).resolve().parents[1]


def home_source(revision):
    text = (ROOT/'homebrew/kwce-dvd/r35/source/kwce/kwce_home.cpp').read_bytes().decode('utf-8')
    for path, old, new in patches(revision):
        if path.endswith('kwce/kwce_home.cpp'):
            if text.count(old) == 0:
                old, new = old.replace('\n', '\r\n'), new.replace('\n', '\r\n')
            assert text.count(old) == 1, old[:60]
            text = text.replace(old, new)
    return text.encode('utf-8')


def player_frame(wide, vi_width, screen_w, screen_h=480, fb_w=640, efb_h=480):
    """Python mirror of R65 scale()/kx()/home_frame()."""
    scale = screen_h / 480.0
    kx = (686 / 832 if wide else 670 / 608) * screen_w / (vi_width * scale)
    x0 = round((screen_w * 0.5 - (416 if wide else 304) * scale * kx) * fb_w / screen_w)
    y0 = round((screen_h * 0.5 - 228 * scale) * efb_h / screen_h)
    return scale, kx, x0, y0


class HomeFrameTests(unittest.TestCase):
    def test_r64_source_is_unchanged(self):
        pinned = json.loads((ROOT/'workspace/channels/dvd-player/build-v64/build-manifest.json').read_text())
        self.assertEqual(hashlib.sha256(home_source(64)).hexdigest(), pinned['sources']['source/kwce/kwce_home.cpp'])

    def test_r65_uses_the_console_frame(self):
        text = home_source(65).decode('utf-8')
        self.assertNotIn('screenheight / 500.0f', text)
        self.assertNotIn('screenheight * 0.08f', text)
        self.assertIn('static float scale() { return screenheight / 480.0f; }', text)
        self.assertEqual(text.count('home_frame(true);'), 1)
        self.assertEqual(text.count('home_frame(false);'), 1)
        self.assertLess(text.index('home_frame(true);'), text.index('render(g_home, scale(), 0xFF);'))
        self.assertLess(text.index('KwceCursorDraw(i, w->ir.x'), text.index('home_frame(false);'))
        # Drawing, hit testing and the cursor share the same horizontal unit.
        self.assertIn('s * kx() * (wide()?1.3684211f:1.f), s, 1.f', text)
        self.assertIn('/ (scale() * kx()), ly = (screenheight * 0.5f - y) / scale();', text)
        self.assertIn('/ (s * kx() * (wide()?1.3684211f:1.f));', text)

    def test_on_screen_size_matches_the_console(self):
        # Player: 854 (16:9) / 640 (4:3) virtual units over 640 EFB pixels and VI width 711 / 704.
        for wide, vi, sw, native in ((True, 711, 854, 686 / 832), (False, 704, 640, 670 / 608)):
            scale, kx, x0, y0 = player_frame(wide, vi, sw)
            self.assertEqual(scale, 1.0)                      # one layout unit per NTSC line
            vi_per_unit = kx * vi / sw                        # VI pixels per adjusted layout unit
            self.assertAlmostEqual(vi_per_unit, native, places=6)
            self.assertEqual(y0, 12)                          # 456 of 480 lines, as the console
            visible = (640 - 2 * x0) * vi / 640               # VI pixels of the clipped picture
            self.assertAlmostEqual(visible, 686 if wide else 670, delta=2.5)
        # A live 720-pixel VI width (WiiMC's optional full width) keeps the same size on screen.
        scale, kx, _, _ = player_frame(True, 720, 854)
        self.assertAlmostEqual(kx * 720 / 854, 686 / 832, places=6)

    def test_settings_top_bar_is_hidden_like_the_console(self):
        # bar_00 moves 230 -> 310 (cntrl_up); its lower edge then sits at the +228 picture edge.
        # R31's /500 showed +-250 units, which left that edge and the clipped label on screen.
        old_visible = 240 / (480 / 500)
        self.assertGreater(old_visible, 228 + 15)
        _, _, _, y0 = player_frame(True, 711, 854)
        self.assertEqual(240 - y0, 228)


if __name__ == '__main__':
    unittest.main()

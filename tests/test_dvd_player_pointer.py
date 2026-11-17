"""DVD menu pointer mapping (R60): run the patched helper on the host.

The picture quad is the one GX_UpdateScaling() draws. Old upstream mapping is
modelled only to show the defect this replaces; hardware pointer feel is not
verified here.
"""
import ctypes
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kwce.dvd_player_fork import patches

ROOT = Path(__file__).resolve().parents[1]


def helper(revision):
    for path, old, new in patches(revision):
        if path.endswith('gx_supp.c') and 'KwceScreenToPicture' in new:
            return new[:new.index('void GX_SetScreenPos')]
    return None


class PointerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); w = Path(cls.tmp.name)
        (w/'t.c').write_text(
            'int hor_pos, vert_pos, video_diffx, video_diffy, video_haspect, video_vaspect,'
            ' mplayerwidth, mplayerheight; float hor_zoom = 1, vert_zoom = 1;\n' + helper(60))
        subprocess.run(['cc', '-std=c11', '-shared', '-fPIC', '-Wall', '-Werror', str(w/'t.c'),
                        '-o', str(w/'t.so')], check=True, capture_output=True)
        cls.lib = ctypes.CDLL(str(w/'t.so'))
        cls.lib.KwceScreenToPicture.argtypes = [ctypes.c_double, ctypes.c_double,
                                                ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double)]

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def setup(self, width, haspect, vaspect, **extra):
        values = dict(mplayerwidth=width, mplayerheight=480, video_haspect=haspect, video_vaspect=vaspect,
                      hor_pos=0, vert_pos=0, video_diffx=0, video_diffy=0)
        values.update(extra)
        for k, v in values.items(): ctypes.c_int.in_dll(self.lib, k).value = v

    def map(self, sx, sy):
        fx, fy = ctypes.c_double(), ctypes.c_double()
        ok = self.lib.KwceScreenToPicture(sx, sy, ctypes.byref(fx), ctypes.byref(fy))
        return ok, fx.value, fy.value

    def test_pillarboxed_4_3_picture_on_wide_console_reaches_every_edge(self):
        # 16:9 console: 854 wide, 4:3 DVD drawn 640 wide (half extents 320x240).
        self.setup(854, 320, 240)
        left, right = 107/854, 747/854
        for fx in (0.02, 0.25, 0.5, 0.93, 0.98):
            for fy in (0.02, 0.5, 0.88, 0.98):
                ok, x, y = self.map(left+fx*(right-left), fy)
                self.assertTrue(ok); self.assertAlmostEqual(x, fx, 3); self.assertAlmostEqual(y, fy, 3)
        self.assertEqual(self.map(0.05, 0.5)[0], 0)   # on the black side bar
        self.assertEqual(self.map(0.95, 0.5), (0, -1.0, -1.0))

    def test_full_screen_4_3_console_is_identity(self):
        self.setup(640, 320, 240)
        for fx, fy in ((0.93, 0.88), (0.07, 0.1), (0.5, 0.5)):
            ok, x, y = self.map(fx, fy)
            self.assertTrue(ok); self.assertAlmostEqual(x, fx, 3); self.assertAlmostEqual(y, fy, 3)

    def test_user_shift_and_zoom_follow_the_drawn_quad(self):
        self.setup(640, 320, 240, hor_pos=20, vert_pos=-10)
        ok, x, y = self.map((320+20)/640, (240-10)/480)
        self.assertTrue(ok); self.assertAlmostEqual(x, 0.5, 3); self.assertAlmostEqual(y, 0.5, 3)

    def test_old_mapping_could_not_reach_an_edge_button(self):
        # Upstream: vo_screenwidth=720 (image width), vo_dwidth x vo_dheight=480x360.
        def old(ir_x, ir_y):
            ix = ir_x*720/640-(720-480)/2; iy = ir_y-(480-360)/2
            return None if not (0 <= ix <= 480 and 0 <= iy <= 360) else (ix/480, iy/360)
        self.assertIsNone(old(0.93*640, 0.88*480))        # next-page arrow position
        self.assertIsNotNone(old(320, 240))               # centre still worked
        self.setup(640, 320, 240)
        self.assertTrue(self.map(0.93, 0.88)[0])

    def test_patch_wiring_and_frozen_revisions(self):
        new, prev = json.dumps(patches(60)), json.dumps(patches(59))
        self.assertIn('KwceScreenToPicture(pointer_x / 10000.0, pointer_y / 10000.0', new)
        self.assertIn('x*10000.0/screenwidth', new)
        self.assertNotIn('KwceScreenToPicture', prev)
        self.assertIsNone(helper(59))


class DiscReadWaitTests(unittest.TestCase):
    def test_disc_streams_wait_longer_than_the_network_give_up(self):
        rows = [(p, o, n) for p, o, n in patches(61) if p.endswith('cache2.c') and 'getWeird' in o]
        self.assertEqual(len(rows), 1)
        _, old, new = rows[0]
        self.assertIn('getWeird > 80', old)
        self.assertIn('STREAMTYPE_DVDNAV', new); self.assertIn('STREAMTYPE_DVD)', new)
        self.assertIn('? 1500 : 80', new)   # other stream types keep upstream's limit
        self.assertFalse([1 for p, o, n in patches(60) if p.endswith('cache2.c') and 'getWeird' in o])
        source = (ROOT/'external/other-tools/wiimc/source/mplayer/stream/cache2.c').read_text(errors='replace')
        self.assertEqual(source.count(old), 1)             # anchor is the upstream give-up
        self.assertIn('#define READ_USLEEP_TIME 10000', source)  # 10 ms per poll -> 0.8 s / 15 s


if __name__ == '__main__': unittest.main()

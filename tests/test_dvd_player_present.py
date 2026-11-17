"""R62-R64 player behaviour: still-menu release, presentation policy, logging.

The policy header is compiled and run on the host. The decoder/VI behaviour
itself was checked in the isolated emulator with a real disc menu; these tests
pin the rules and the patch wiring so later revisions cannot silently drop them.
"""
import ctypes
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kwce.dvd_player_fork import patches

ROOT = Path(__file__).resolve().parents[1]


def patched_header(revision):
    text = (ROOT/'homebrew/kwce-dvd/r22/source/kwce/kwce_present.h').read_text()
    for path, old, new in patches(revision):
        if path.endswith('kwce_present.h'):
            assert text.count(old) == 1; text = text.replace(old, new)
    return text


class PresentPolicyTests(unittest.TestCase):
    def build(self, revision):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); w = Path(tmp.name)
        (w/'p.c').write_text(patched_header(revision) +
                             '\nint present(unsigned m,int s,int f,int h,unsigned n){return KwceShouldPresent(m,s,f,h,n);}'
                             '\nint selftest(void){return KwcePresentSelfTest();}\n')
        subprocess.run(['cc', '-std=c11', '-shared', '-fPIC', '-Wall', '-Werror', str(w/'p.c'), '-o', str(w/'p.so')],
                       check=True, capture_output=True)
        return ctypes.CDLL(str(w/'p.so'))

    def test_wrong_field_waits_one_retrace_only(self):
        new, old = self.build(64), self.build(63)
        self.assertEqual(new.selftest(), 0); self.assertEqual(old.selftest(), 0)
        for sync, wrong in ((1, 1), (2, 0)):
            self.assertEqual(new.present(0, sync, wrong, 0, 0), 0)      # first retrace: wait for the field
            self.assertEqual(new.present(0, sync, wrong, 0, 1), 1)      # next retrace: show regardless
            self.assertEqual(new.present(0, sync, 1-wrong, 0, 0), 1)    # matching field: show at once
            self.assertEqual(old.present(0, sync, wrong, 0, 1), 0)      # previous rule needed a third retrace
        for mode in (1, 2):                                             # progressive output never waits
            self.assertEqual(new.present(mode, 2, 0, 0, 0), 1)
        self.assertEqual(new.present(0, 2, 0, 1, 0), 1)                 # HOME never waits

    def simulate(self, lib, field_of, frames=60, single_wait=False):
        """Frames become pending right after the previous draw; count shown frames per retrace."""
        shown = 0; pending = False; missed = 0; retrace = 0; lost = 0
        for _ in range(frames):
            waits = 0
            while pending and (waits < 1 if single_wait else waits < 4):
                if lib.present(0, 2, field_of(retrace), 0, missed): pending = False; shown += 1; missed = 0
                else: missed += 1
                retrace += 1; waits += 1
            if pending: lost += 1                                        # drawn over before it was shown
            pending = True
        return shown, lost, retrace

    def test_no_frame_is_drawn_over_and_rate_is_two_retraces(self):
        lib = self.build(64)
        for field_of in (lambda r: r & 1, lambda r: 0):                  # alternating fields / field never matches
            shown, lost, retraces = self.simulate(lib, field_of)
            self.assertEqual(lost, 0); self.assertGreaterEqual(shown, 59)
            self.assertLessEqual(retraces, 2*60)                         # at most two retraces per frame
        # The R62 draw path waited one retrace and then drew over the pending frame.
        shown, lost, _ = self.simulate(self.build(63), lambda r: 0, single_wait=True)
        self.assertGreater(lost, 20)


class StillAndLoggingWiringTests(unittest.TestCase):
    def rows(self, revision, suffix):
        return [(o, n) for p, o, n in patches(revision) if p.endswith(suffix)]

    def test_still_release_feeds_one_sequence_end_per_still(self):
        new = json.dumps(self.rows(64, 'mplayer.c'))
        self.assertIn('kwce_seq_end[4 + 64] = {0x00, 0x00, 0x01, 0xB7}', new)
        self.assertIn('if (in_size > 4)\\n        kwce_nav_fed = 1;', new)   # only real pictures arm the release
        self.assertIn('kwce_nav_fed = 0;', new)
        self.assertNotIn('kwce_nav_fed', json.dumps(self.rows(61, 'mplayer.c')))
        # The decoder rule this relies on is present in the pinned upstream source.
        mpeg = (ROOT/'external/other-tools/wiimc/source/mplayer/ffmpeg/libavcodec/mpeg12.c').read_text(errors='replace')
        self.assertIn('buf_size == 4 && AV_RB32(buf) == SEQ_END_CODE', mpeg)

    def test_truncated_frame_pictures_are_skipped_only_on_discs(self):
        new = json.dumps(self.rows(64, 'video.c'))
        self.assertIn('kwce_last_slice < picture.display_picture_height/16', new)
        self.assertIn('picture.picture_structure==3', new)                 # frame pictures only
        self.assertIn('STREAMTYPE_DVDNAV', new)
        self.assertEqual(self.rows(61, 'video.c'), [])

    def test_draw_waits_until_the_pending_frame_was_shown(self):
        new = json.dumps(self.rows(64, 'gx_supp.c'))
        self.assertIn('while(flip_pending && kwceWaits++<4) VIDEO_WaitVSync();', new)
        self.assertNotIn('kwceWaits', json.dumps(self.rows(62, 'gx_supp.c')))

    def test_still_refresh_step_and_clock_agree(self):
        new = json.dumps(self.rows(64, 'mplayer.c'))
        self.assertIn('frame_time = 1.0f / 60.0f;', new)
        self.assertIn('mpctx->sh_video->pts += 1.0f / 60.0f;', new)

    def test_no_sd_append_per_trace_line_once_video_runs(self):
        new = json.dumps(self.rows(64, 'kwce_dvd.cpp'))
        self.assertIn('if (!strcmp(event,\\"video-config\\")) kwceLogDirect=0;', new)
        self.assertIn('if (!strcmp(event,\\"player-exit\\")) kwceLogDirect=1;', new)
        self.assertIn('KwceDvdTraceFlush(); /* playback is paused here */', json.dumps(self.rows(64, 'kwce_home.cpp')))
        self.assertIn('KwceDvdPerf(kwceFlips)', json.dumps(self.rows(64, 'video.cpp')))

    def test_battery_bars_use_console_thresholds(self):
        new = json.dumps(self.rows(64, 'kwce_home.cpp'))
        self.assertIn('raw >= 0x55 ? 4 : raw >= 0x44 ? 3 : raw >= 0x33 ? 2 : raw >= 0x03 ? 1 : 0', new)

    def test_debug_ring_never_reaches_release_revisions(self):
        for revision in (62, 63, 64):
            self.assertNotIn('KWCE-RING', json.dumps(patches(revision)))
        self.assertIn('KWCE-RING', json.dumps(patches(900)))


if __name__ == '__main__': unittest.main()

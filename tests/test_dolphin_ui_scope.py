import unittest
from dataclasses import replace
from kwce.dolphin_ui_scope import Process, Target, ScopeError, match, select, revalidate, capture_name, overlaps


class DolphinUIScopeTests(unittest.TestCase):
    def setUp(self):
        self.target = Target('test', r'C:\project\sandbox\test\Dolphin-x64\Dolphin.exe', r'C:\project\sandbox\test\user')
        self.process = Process(100, self.target.executable,
                               (self.target.executable, '--user', self.target.user), 123456)

    def test_executable_and_profile_must_both_match(self):
        self.assertEqual(match(self.process, [self.target]), self.target)
        for bad in [replace(self.process, executable=r'C:\personal\Dolphin.exe'),
                    replace(self.process, argv=(self.target.executable, '--user', r'C:\personal\user')),
                    replace(self.process, argv=(self.target.executable,)),
                    replace(self.process, argv=(*self.process.argv, '--user', self.target.user)),
                    replace(self.process, argv=(self.target.executable, '-u'+self.target.user)),
                    replace(self.process, argv=(self.target.executable, '--user', r'C:\project\sandbox\test\user\..\baseline')),
                    replace(self.process, created=0)]:
            self.assertIsNone(match(bad, [self.target]))

    def test_windows_case_and_equal_form(self):
        p = replace(self.process, executable=self.target.executable.upper(),
                    argv=(self.target.executable.upper(), '--user='+self.target.user.upper()))
        self.assertEqual(match(p, [self.target]), self.target)

    def test_ambiguous_target_refused_and_outside_pid_never_selected(self):
        second = replace(self.process, pid=101)
        outside = Process(9, r'C:\personal\Dolphin.exe', ('Dolphin.exe',), 99)
        self.assertEqual(select([self.process, outside], [self.target])[0], self.process)
        with self.assertRaises(ScopeError): select([self.process, second], [self.target])
        with self.assertRaises(ScopeError): select([self.process, outside], [self.target], 9)
        self.assertEqual(select([self.process, second], [self.target], 101)[0], second)

    def test_pid_reuse_stale_window_failed_focus_and_occlusion(self):
        for current, window_pid, foreground, unobscured in [
            (replace(self.process, created=123457), 100, True, True),
            (self.process, 101, True, True), (self.process, 100, False, True),
            (self.process, 100, True, False)]:
            with self.assertRaises(ScopeError):
                revalidate(self.process, current, [self.target], window_pid, foreground, unobscured)
        revalidate(self.process, self.process, [self.target], 100)

    def test_capture_names_cannot_escape_private_directory(self):
        for name in ['../outside', r'..\outside', '/absolute', 'C:outside', 'a/b', 'name.png','CON','nul','COM1','LPT9']:
            with self.assertRaises(ScopeError): capture_name(name)
        self.assertEqual(capture_name('weather-clock-01'), 'weather-clock-01.png')

    def test_small_overlay_between_sample_points_is_detected(self):
        self.assertTrue(overlaps((0,0,1000,1000),(100,100,110,110)))
        self.assertFalse(overlaps((0,0,1000,1000),(1000,100,1010,110)))

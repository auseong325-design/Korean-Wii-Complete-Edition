"""Long-lived Dolphin helpers must not inherit the caller's stdout pipe.

A helper that inherits the pipe keeps it open until Dolphin exits, so a caller that reads the pipe
(for example PowerShell `| Select-Object`) blocks for as long as Dolphin runs (~90 minutes).
"""
import ast
import subprocess
import sys
import textwrap
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import launch_dolphin  # noqa: E402


class LauncherDetachTest(unittest.TestCase):
    def test_detach_kwargs_close_every_std_handle(self):
        kw = launch_dolphin.detach_kwargs()
        for key in ('stdin', 'stdout', 'stderr'):
            self.assertIs(kw[key], subprocess.DEVNULL, key)
        self.assertTrue(kw['close_fds'])

    def test_reader_of_the_pipe_is_not_blocked_by_a_long_lived_child(self):
        parent = textwrap.dedent(f'''
            import subprocess, sys
            sys.path.insert(0, {str(SCRIPTS)!r})
            import launch_dolphin
            p = launch_dolphin.popen_detached([sys.executable, '-c', 'import time; time.sleep(25)'])
            print(p.pid, flush=True)
        ''')
        started = time.monotonic()
        result = subprocess.run([sys.executable, '-c', parent], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, timeout=20)
        elapsed = time.monotonic() - started
        child_pid = int(result.stdout.strip().splitlines()[-1])
        try:
            self.assertLess(elapsed, 15, 'the launcher pipe stayed open while the child was running')
        finally:
            subprocess.run(['taskkill', '/PID', str(child_pid), '/F'], capture_output=True)

    def test_every_launcher_popen_redirects_or_detaches_stdout(self):
        files = sorted(SCRIPTS.glob('launch_*.py')) + [SCRIPTS / 'run_channel_test.py']
        offenders = []
        for path in files:
            tree = ast.parse(path.read_bytes(), filename=str(path))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == 'Popen' and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == 'subprocess'):
                    redirected = any(k.arg == 'stdout' or k.arg is None for k in node.keywords)
                    if not redirected:
                        offenders.append(f'{path.name}:{node.lineno}')
        self.assertEqual(offenders, [], 'Popen without a stdout redirect can hold the caller pipe open')


if __name__ == '__main__':
    unittest.main()

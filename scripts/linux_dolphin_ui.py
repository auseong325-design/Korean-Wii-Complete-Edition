"""X11/XWayland render-only control, scoped to the isolated Linux launcher.

Use XRes host PID, not _NET_WM_PID (which uses the sandbox PID namespace).
No main-window tree, titles, desktop screenshots or emulator logs are read.
"""
import argparse
import ctypes as C
import ctypes.util
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import time
import os
import stat

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kwce.linux_runtime import PRIVATE, default_profile, direct, running, runtime, stop
if '--online' in sys.argv:      # same render-window control for workspace/online profiles
    sys.argv.remove('--online')
    from kwce.linux_online import PRIVATE, running, runtime, stop


def render_window(profile):
    rows = running(profile)
    if len(rows) != 1:
        raise ValueError('Expected one validated isolated Dolphin process')
    row = rows[0]
    args = Path(f"/proc/{row['pid']}/cmdline").read_bytes().split(b'\0')
    if b'--batch' not in args or b'--logger' in args or b'--debugger' in args:
        raise ValueError('Only batch render-window mode is permitted')

    class Spec(C.Structure):
        _fields_ = [('client', C.c_ulong), ('mask', C.c_uint)]
    class Value(C.Structure):
        _fields_ = [('spec', Spec), ('length', C.c_long), ('value', C.c_void_p)]
    x = C.CDLL(ctypes.util.find_library('X11'))
    x.XOpenDisplay.argtypes = [C.c_char_p]
    x.XOpenDisplay.restype = C.c_void_p
    x.XCloseDisplay.argtypes = [C.c_void_p]
    r = C.CDLL(ctypes.util.find_library('XRes'))
    r.XResQueryClientIds.argtypes = [C.c_void_p, C.c_long, C.POINTER(Spec),
                                    C.POINTER(C.c_long), C.POINTER(C.POINTER(Value))]
    r.XResGetClientPid.argtypes = [C.POINTER(Value)]
    r.XResGetClientPid.restype = C.c_int
    r.XResClientIdsDestroy.argtypes = [C.c_long, C.POINTER(Value)]
    display = x.XOpenDisplay(None)
    if not display:
        raise ValueError('Local X display unavailable')
    windows = []
    try:
        found = subprocess.run(['xdotool', 'search', '--onlyvisible', '--class', 'dolphin'],
                               capture_output=True, text=True, check=False)
        for item in found.stdout.split():
            spec = Spec(int(item), 2)
            count, values = C.c_long(), C.POINTER(Value)()
            if r.XResQueryClientIds(display, 1, C.byref(spec), C.byref(count), C.byref(values)) == 0:
                try:
                    if any(r.XResGetClientPid(C.byref(values[i])) == row['pid'] for i in range(count.value)):
                        windows.append(item)
                finally:
                    r.XResClientIdsDestroy(count, values)
    finally:
        x.XCloseDisplay(display)
    if len(windows) != 1:
        raise ValueError('Ambiguous render window or modal dialog; no input/capture performed')
    return windows[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', default=default_profile())
    sub = ap.add_subparsers(dest='action', required=True)
    sub.add_parser('stop')
    sub.add_parser('focus')
    p = sub.add_parser('shot')
    p.add_argument('--scale', type=float, default=.5)
    p = sub.add_parser('key')
    p.add_argument('keys', nargs='+', choices=['a', 'b', 'h', 'x', 'z', 'c', 's', 'd', 'i', 'k', 'j', 'l', 'q', 'w', 't', 'g', 'f', '1', '2', 'plus', 'minus', 'Up', 'Down', 'Left', 'Right', 'Return', 'Escape'])
    p = sub.add_parser('click')
    p.add_argument('x', type=float)
    p.add_argument('y', type=float)
    p.add_argument('--button', choices=['1', '2', '3'], default='1')
    p = sub.add_parser('pad', help='profile-local GC FIFO; requires a prepared Pipe controller')
    p.add_argument('button', choices=['A', 'B', 'X', 'Y', 'Z', 'START', 'L', 'R', 'D_UP', 'D_DOWN', 'D_LEFT', 'D_RIGHT'])
    p.add_argument('--hold', type=int, default=400, help='hold in milliseconds (50..5000)')
    p = sub.add_parser('pointer', help='profile-local Pipe Wiimote pointer (normalized coordinates)')
    p.add_argument('x', type=float)
    p.add_argument('y', type=float)
    args = ap.parse_args()
    if args.action == 'stop':
        stop(args.profile)
        return
    window = render_window(args.profile)
    if args.action in ('pad', 'pointer'):
        if args.action == 'pad' and not 50 <= args.hold <= 5000:
            raise ValueError('GC hold must be 50..5000 milliseconds')
        if args.action == 'pointer' and not (0 <= args.x <= 1 and 0 <= args.y <= 1):
            raise ValueError('Normalized pointer coordinates required')
        folder = runtime(args.profile)
        pipe = direct(folder / 'user/Pipes/kwce-gc', folder)
        if not stat.S_ISFIFO(pipe.stat().st_mode):
            raise ValueError('Prepared GC input FIFO required')
        fd = os.open(pipe, os.O_WRONLY | os.O_NONBLOCK)
        try:
            if args.action == 'pointer':
                os.write(fd, f'SET MAIN {args.x:.5f} {1-args.y:.5f}\n'.encode('ascii'))
            else:
                os.write(fd, ('PRESS ' + args.button + '\n').encode('ascii'))
                time.sleep(args.hold / 1000)
                if not running(args.profile):
                    raise ValueError('Isolated process exited during input')
                os.write(fd, ('RELEASE ' + args.button + '\n').encode('ascii'))
        finally:
            os.close(fd)
        print('PASS profile-local controller input')
        return
    if args.action == 'shot':
        if not .1 <= args.scale <= 1:
            raise ValueError('Scale must be 0.1..1')
        out = PRIVATE / 'captures' / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.png')
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists() or out.is_symlink():
            raise ValueError('Capture overwrite refused')
        subprocess.run(['import', '-silent', '-window', window, str(out)], check=True, timeout=10)
        from PIL import Image
        with Image.open(out) as im:
            im.resize((round(im.width * args.scale), round(im.height * args.scale))).save(out)
        print(str(out))
        return
    subprocess.run(['xdotool', 'windowactivate', '--sync', window], check=True, timeout=5)
    subprocess.run(['xdotool', 'windowfocus', '--sync', window], check=True, timeout=5)
    if render_window(args.profile) != window:
        raise ValueError('Render identity changed')
    if args.action == 'key':
        for key in args.keys:
            if subprocess.check_output(['xdotool', 'getactivewindow'], text=True).strip() != window:
                raise ValueError('Render window lost focus; input stopped')
            subprocess.run(['xdotool', 'keydown', key], check=True)
            time.sleep(.4)
            subprocess.run(['xdotool', 'keyup', key], check=True)
            time.sleep(.15)
    elif args.action == 'click':
        if not 0 <= args.x <= 1 or not 0 <= args.y <= 1:
            raise ValueError('Normalized coordinates required')
        text = subprocess.check_output(['xdotool', 'getwindowgeometry', '--shell', window], text=True)
        geometry = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
        subprocess.run(['xdotool', 'mousemove', '--window', window,
                        str(round(args.x * (int(geometry['WIDTH']) - 1))),
                        str(round(args.y * (int(geometry['HEIGHT']) - 1)))], check=True)
        if subprocess.check_output(['xdotool', 'getactivewindow'], text=True).strip() != window:
            raise ValueError('Render window lost focus; click stopped')
        subprocess.run(['xdotool', 'mousedown', args.button], check=True)
        time.sleep(.4)
        subprocess.run(['xdotool', 'mouseup', args.button], check=True)
    print('PASS scoped render input')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'FAIL render control: {exc}' if isinstance(exc, ValueError) else 'FAIL render control: tool error')
        raise SystemExit(1)

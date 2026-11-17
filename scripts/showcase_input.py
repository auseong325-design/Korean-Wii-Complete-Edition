"""Smooth scripted input for a running showcase profile (profile FIFO only, no X11 needed).

  showcase_input.py --profile NAME "move 0.50 0.40 500; press A; wait 1.5; press D_DOWN 120"

Commands (';'-separated):
  move X Y [MS]      glide the Wiimote pointer to normalized X,Y over MS ms (default 450), eased
  jump X Y           set the pointer immediately
  press BTN [MS]     press and release (A B X Y Z START L R D_UP D_DOWN D_LEFT D_RIGHT), hold MS (default 120)
  hold BTN / release BTN
  gpress BTN [MS] / ghold BTN / grelease BTN / gstick X Y   the same on GC pad 1 (its own FIFO);
                     gstick takes -1..1 (0 0 = centre)
  wait SECONDS
Wiimote pipe mapping: A/B = A/B, X/Y = 1/2, L/R = -/+, START = HOME.
The last pointer position is kept in the profile's pointer.json so moves continue smoothly.
"""
import argparse
import json
import math
import os
from pathlib import Path
import stat
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kwce.linux_online import running, runtime
from kwce.linux_runtime import direct

BUTTONS = {'A', 'B', 'X', 'Y', 'Z', 'START', 'L', 'R', 'D_UP', 'D_DOWN', 'D_LEFT', 'D_RIGHT'}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--profile', required=True); ap.add_argument('script')
    ap.add_argument('--label', help='log this run as an edit segment (emulated start/end seconds) in segments.jsonl')
    a = ap.parse_args()
    if len(running(a.profile)) != 1:
        raise ValueError('Expected one running showcase Dolphin')
    folder = runtime(a.profile)
    pipe = direct(folder / 'user/Pipes/kwce-gc', folder)
    if not stat.S_ISFIFO(pipe.stat().st_mode):
        raise ValueError('Prepared input FIFO required')
    state = folder / 'pointer.json'

    def emu_seconds():
        # Dolphin splits the DTK dump into _dtkdump.wav, _dtkdump1.wav, ... at title switches/size limits
        waves = sorted((folder / 'user/Dump/Audio').glob('*_dtkdump*.wav'), key=lambda p: p.stat().st_mtime)
        return round(sum(w.stat().st_size - 44 for w in waves if w.name.startswith(waves[-1].name.split('_dtkdump')[0])) / 192000, 2) if waves else None

    started = emu_seconds()
    x, y = json.loads(state.read_text()) if state.exists() else (0.5, 0.5)
    fd = os.open(pipe, os.O_WRONLY | os.O_NONBLOCK)
    gpipe = direct(folder / 'user/Pipes/kwce-pad', folder)
    gfd = os.open(gpipe, os.O_WRONLY | os.O_NONBLOCK) if gpipe.exists() and stat.S_ISFIFO(gpipe.stat().st_mode) else None

    def point(px, py):
        os.write(fd, f'SET MAIN {px:.5f} {1 - py:.5f}\n'.encode('ascii'))

    try:
        for raw in a.script.split(';'):
            part = raw.split()
            if not part:
                continue
            op = part[0].lower()
            if op in ('move', 'jump'):
                tx, ty = float(part[1]), float(part[2])
                if not (0 <= tx <= 1 and 0 <= ty <= 1):
                    raise ValueError('Normalized pointer coordinates required')
                if op == 'jump':
                    x, y = tx, ty; point(x, y); continue
                ms = float(part[3]) if len(part) > 3 else 450
                steps = max(1, int(ms / 1000 * 60))
                sx, sy = x, y
                for i in range(1, steps + 1):
                    t = i / steps; e = 0.5 - 0.5 * math.cos(math.pi * t)
                    point(sx + (tx - sx) * e, sy + (ty - sy) * e); time.sleep(ms / 1000 / steps)
                x, y = tx, ty
            elif op in ('press', 'hold', 'release'):
                btn = part[1].upper()
                if btn not in BUTTONS:
                    raise ValueError('Unknown button')
                if op in ('press', 'hold'):
                    os.write(fd, f'PRESS {btn}\n'.encode('ascii'))
                if op == 'press':
                    time.sleep((float(part[2]) if len(part) > 2 else 120) / 1000)
                if op in ('press', 'release'):
                    os.write(fd, f'RELEASE {btn}\n'.encode('ascii'))
            elif op in ('gpress', 'ghold', 'grelease', 'gstick'):
                if gfd is None:
                    raise ValueError('GC pad FIFO missing (reconfigure the profile)')
                if op == 'gstick':
                    sx2, sy2 = float(part[1]), float(part[2])
                    os.write(gfd, f'SET MAIN {(sx2 + 1) / 2:.4f} {(sy2 + 1) / 2:.4f}\n'.encode('ascii'))
                else:
                    btn = part[1].upper()
                    if btn not in BUTTONS:
                        raise ValueError('Unknown button')
                    if op in ('gpress', 'ghold'):
                        os.write(gfd, f'PRESS {btn}\n'.encode('ascii'))
                    if op == 'gpress':
                        time.sleep((float(part[2]) if len(part) > 2 else 120) / 1000)
                    if op in ('gpress', 'grelease'):
                        os.write(gfd, f'RELEASE {btn}\n'.encode('ascii'))
            elif op == 'wait':
                time.sleep(float(part[1]))
            else:
                raise ValueError(f'Unknown command {op}')
            if not running(a.profile):
                raise ValueError('Dolphin exited during input')
    finally:
        os.close(fd)
        if gfd is not None:
            os.close(gfd)
        state.write_text(json.dumps([x, y]))
    ended = emu_seconds()
    if a.label:
        waves = sorted((folder / 'user/Dump/Audio').glob('*_dtkdump*.wav'), key=lambda p: p.stat().st_mtime)
        with (folder / 'segments.jsonl').open('a') as log:
            log.write(json.dumps(dict(label=a.label, audio=waves[-1].name if waves else None, start=started, end=ended)) + '\n')
    print(f'PASS input (emulated {started} -> {ended} s)')


if __name__ == '__main__':
    main()

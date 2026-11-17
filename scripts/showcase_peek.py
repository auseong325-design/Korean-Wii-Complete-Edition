"""Look at a running (or finished) showcase recording without the X display: newest frame of the
newest frame dump, written to workspace/private/showcase/peek/ at the given scale.

  showcase_peek.py --profile NAME [--scale 0.75] [--at SECONDS_FROM_END]
"""
import argparse
from datetime import datetime
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kwce.linux_online import runtime
from kwce.linux_showcase import PRIVATE


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', required=True); ap.add_argument('--scale', type=float, default=.75)
    ap.add_argument('--at', type=float, default=0.2)
    a = ap.parse_args()
    frames = sorted((runtime(a.profile) / 'user/Dump/Frames').glob('*'), key=lambda p: p.stat().st_mtime)
    if not frames:
        raise SystemExit('No frame dump yet')
    out = PRIVATE / 'peek' / (datetime.now().strftime('%H%M%S-%f') + '.png'); out.parent.mkdir(parents=True, exist_ok=True)
    vf = f'scale=iw*{a.scale}:-2'
    # A growing Matroska file has no cues/duration: splice its header onto the last few clusters
    # (every frame is intra-coded) and keep the last decoded frame.
    src = frames[-1]; size = src.stat().st_size; cluster = bytes.fromhex('1f43b675')
    with src.open('rb') as f:
        head = f.read(1 << 16); cut = head.find(cluster)
        f.seek(max(cut, size - int(a.at * 12 * 1024 * 1024))); tail = f.read()
    k = tail.find(cluster)
    if cut < 0 or k < 0:
        raise SystemExit('No cluster found')
    tmp = PRIVATE / 'peek/tail.mkv'; tmp.write_bytes(head[:cut] + tail[k:])
    subprocess.run(['ffmpeg', '-v', 'quiet', '-i', str(tmp), '-vf', vf, '-update', '1', '-y', str(out)],
                   capture_output=True, timeout=120)
    tmp.unlink()
    if not out.exists():
        raise SystemExit('No frame decoded')
    print(out)


if __name__ == '__main__':
    main()

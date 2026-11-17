"""Estimate the Wii system memory (NAND) a KWCE install takes: channel contents + the data the channels
create after their first runs. Prints a table and writes configs/nand-usage-vN.json (new number only).

  .venv\\Scripts\\python.exe scripts\\measure_nand_usage.py --package kwce-rc-sd-v53 --out configs/nand-usage-v1.json

Contents: decrypted content sizes of each kwce-rc/<id>/korean.wad (the default build). Data: the largest
title/<tid>/data folder found in any local Dolphin profile under workspace/ (channels that were actually run
there), counted per file in 128 KiB Wii blocks. Only sizes are read; nothing is copied. A channel never run
in any profile is listed with data 0 and "measured": false.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import public_patch as pp  # noqa: E402

BLOCK = 128 * 1024


def blocks(n): return -(-n // BLOCK)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--package', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    pkg = ROOT / 'workspace/hardware' / a.package
    out = ROOT / a.out
    if out.exists():
        raise SystemExit(f'{a.out} exists; use a new number')
    channels = []
    for line in (pkg / 'kwce-rc/packages.txt').read_text(encoding='utf-8').splitlines():
        if line.startswith('#') or not line.strip():
            continue
        f = line.split('|')
        if len(f) >= 6 and f[5] == '1':
            continue                                  # remove-only legacy entry: nothing is installed
        channels.append((f[0], f[1].lower(), f[2], f[3] == '1'))
    profiles = sorted({p.parent for p in (ROOT / 'workspace').rglob('Wii/title') if p.is_dir()})
    rows = []
    for cid, tid, name, experimental in channels:
        w = pp.Wad((pkg / f'kwce-rc/{cid}/korean.wad').read_bytes())
        content = sum(r['size'] for r in w.records)
        best = (0, 0, None)
        for prof in profiles:
            d = prof / 'title' / tid[:8] / tid[8:] / 'data'
            if d.is_dir():
                sizes = [p.stat().st_size for p in d.rglob('*') if p.is_file()]
                b = sum(blocks(s) for s in sizes)
                if b > best[1]:
                    best = (sum(sizes), b, prof.parent.relative_to(ROOT).as_posix())
        rows.append(dict(id=cid, title_id=tid, name=name, experimental=experimental,
                         content_bytes=content, content_blocks=blocks(content),
                         data_bytes=best[0], data_blocks=best[1], measured=best[2] is not None, data_profile=best[2]))
    total = dict(content_blocks=sum(r['content_blocks'] for r in rows), data_blocks=sum(r['data_blocks'] for r in rows),
                 content_bytes=sum(r['content_bytes'] for r in rows), data_bytes=sum(r['data_bytes'] for r in rows))
    total['blocks'] = total['content_blocks'] + total['data_blocks']
    total['bytes'] = total['content_bytes'] + total['data_bytes']
    rec = dict(package=a.package, block_bytes=BLOCK, profiles_scanned=len(profiles), channels=rows, total=total,
               note='Default Korean builds; data = largest data folder seen after real runs (estimate).')
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    for r in rows:
        print(f"{r['id']:<14} {r['content_blocks']:5d} + {r['data_blocks']:3d} blocks"
              f"  ({(r['content_bytes'] + r['data_bytes']) / 1e6:5.1f}MB){'' if r['measured'] else '  data not measured'}")
    print(f"total          {total['content_blocks']:5d} + {total['data_blocks']:3d} = {total['blocks']} blocks"
          f" ({total['bytes'] / 1e6:.0f}MB), profiles {len(profiles)}")


if __name__ == '__main__':
    main()

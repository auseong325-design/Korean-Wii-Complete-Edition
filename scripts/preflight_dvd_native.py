"""Read-only DOL preflight. Writes a new private report, never an SD payload."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.dvd_native_loader import preflight


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', type=int, default=31)
    args = parser.parse_args()
    player = ROOT / f'workspace/channels/dvd-player/build-v{args.revision}/boot.dol'
    menu = ROOT / 'workspace/console-baseline/menu-original-43K.dol'
    report = preflight(player.read_bytes(), menu.read_bytes())
    base = ROOT / 'workspace/private'
    n = 1
    while (base / f'dvd-native-preflight-v{n}.json').exists():
        n += 1
    out = base / f'dvd-native-preflight-v{n}.json'
    with out.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(f'PASS static DOL validation: {len(report["target_regions"])} regions; '
          f'{len(report["menu_collisions"])} menu overlaps; '
          f'runtime=UNVERIFIED; boot=UNVERIFIED; installable=NO')


if __name__ == '__main__':
    main()

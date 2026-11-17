"""Refresh Emulator_BAT from active catalog entries; never touches NAND/SD."""
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.emulator_shortcuts import synchronize,load_plans


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
    changed=synchronize(ROOT,check=args.check)
    if args.check and changed:raise SystemExit('BAT collection is stale: run scripts/sync_emulator_bats.py')
    print(f'PASS: Emulator_BAT {len(load_plans(ROOT))} launchers; '+('up to date'if args.check else f'{len(changed)} files refreshed'))


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError):raise SystemExit('BAT sync refused: check catalog, menu settings and generated-file ownership')from None

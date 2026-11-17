"""Freeze a numbered, non-bootable PPC research fixture. No SD/install option."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.dvd_sd_service import compile_service, SOURCE, FIXTURE_BASE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', type=int, required=True)
    args = parser.parse_args()
    if args.revision < 1:
        parser.error('Revision must be positive')
    out = ROOT / f'workspace/experiments/dvd-sd-service-v{args.revision}'
    if out.exists():
        parser.error('Existing research revision must not be overwritten')
    blob, symbols = compile_service()
    second, second_symbols = compile_service()
    if (blob, symbols) != (second, second_symbols):
        raise ValueError('Research component is not reproducible')
    meta = dict(schema=1, local_only=True, bootable=False,
                source_revision=1, fixture_base=FIXTURE_BASE, bytes=len(blob),
                sha256=hashlib.sha256(blob).hexdigest(),
                sources={name: hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()
                         for name in ('service.c', 'service.h')},
                installed=False, nand_writes=False, sd_deployment=False,
                limits=['Unicorn fixture address only; no reviewed code placement',
                        'Single icon/banner batch; no player payload or DVD detection',
                        'Board creation/Settings cancellation/UI ownership not wired',
                        'Physical I/O, OS scheduling and complete menu exit unverified'])
    out.mkdir(parents=True)
    (out/'service.bin').write_bytes(blob)
    (out/'symbols.json').write_text(json.dumps(symbols, indent=2)+'\n')
    (out/'manifest.json').write_text(json.dumps(meta, indent=2)+'\n')
    print(json.dumps(dict(revision=args.revision, bytes=len(blob),
                          reproducible=True, local_only=True, bootable=False)))


if __name__ == '__main__':
    main()

"""Build the Korean-console WiiLink real-order Food editions (kwce.food_variants).

  --variant dominos-us|dominos-ca|justeat-uk|justeat-ie|justeat-es|justeat-de|justeat-at|justeat-it
  --all            every variant
  --local          Dolphin-only test build (127.0.0.2, http) instead of the hardware candidate
  --reproduce      rebuild into workspace/private and require byte-identical output

Output (new folder per variant and revision; an existing folder is never overwritten):
  hardware: workspace/channels/food/<variant>-hardware-v<N>/food-ko-hardware-test.wad
  local:    workspace/channels/food/<variant>-build-v<N>/food-ko-local-test.wad
Nothing is installed. Real orders were never placed or simulated.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import food_variants as fv  # noqa: E402

# revision 1: area bridge + server country + Korean fonts/HOME/HOME CSV/IMET names
# revision 2: --local only; Domino's skips the payload's default-Dolphin-device-ID stop screen
REVISIONS = (1, 2)


def build_one(variant, revision, local, reproduce):
    kind = 'build' if local else 'hardware'
    name = 'food-ko-local-test.wad' if local else 'food-ko-hardware-test.wad'
    out = ROOT / f'workspace/channels/food/{variant}-{kind}-v{revision}'
    expected = None
    if reproduce:
        expected = (out / name).read_bytes()
        n = 1
        while (ROOT / f'workspace/private/food-variant-reproduce-{variant}-{kind}-v{revision}-{n}').exists():
            n += 1
        out = ROOT / f'workspace/private/food-variant-reproduce-{variant}-{kind}-v{revision}-{n}'
    if out.exists():
        raise SystemExit(f'{out.relative_to(ROOT)} exists; existing builds are preserved')
    wad, manifest = fv.build(variant, local=local, revision=revision)
    manifest = dict(revision=revision, **manifest)
    out.mkdir(parents=True)
    (out / name).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if expected is not None and expected != wad:
        raise SystemExit(f'REPRODUCE FAILED: {variant} {kind}-v{revision}')
    c = manifest['server_country']
    print(('Reproduced byte-identically' if expected is not None else 'Built'), f'{variant} {kind}-v{revision}:',
          f"country {manifest['country_code']} at {c['site']} ({c['original']} -> {c['patched']}),",
          f"area {manifest['korean_area_bridge']['source_area']}->{manifest['korean_area_bridge']['resource_area']},",
          f"wad {manifest['wad_sha256'][:16]}", '(local only)' if local else '(not installed)')


def main():
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--variant', choices=sorted(fv.VARIANTS))
    group.add_argument('--all', action='store_true')
    ap.add_argument('--revision', type=int, default=1, choices=REVISIONS)
    ap.add_argument('--local', action='store_true')
    ap.add_argument('--reproduce', action='store_true')
    args = ap.parse_args()
    for variant in (sorted(fv.VARIANTS) if args.all else [args.variant]):
        build_one(variant, args.revision, args.local, args.reproduce)


if __name__ == '__main__':
    main()

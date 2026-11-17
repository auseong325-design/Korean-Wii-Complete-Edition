"""Korean Internet Channel local test build (emulator only). Originals stay untouched.

  .venv\\Scripts\\python.exe scripts\\build_internet.py --revision 1 [--reproduce]

Writes workspace/channels/internet/build-vN/internet-ko-local-test.wad and
build-manifest.json (create-once). --reproduce rebuilds into
workspace/private/internet-reproduce-vN-M and requires identical bytes.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.internet_build import build, config_paths  # noqa: E402

REVISIONS = (1, 2, 3, 4, 5, 6, 7, 8)
WAD = 'internet-ko-local-test.wad'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--revision', type=int, choices=REVISIONS, default=REVISIONS[-1])
    ap.add_argument('--reproduce', action='store_true')
    args = ap.parse_args()
    out = ROOT / f'workspace/channels/internet/build-v{args.revision}'
    expected = None
    if args.reproduce:
        expected = (out / WAD).read_bytes()
        n = 1
        while (ROOT / f'workspace/private/internet-reproduce-v{args.revision}-{n}').exists():
            n += 1
        out = ROOT / f'workspace/private/internet-reproduce-v{args.revision}-{n}'
    if out.exists():
        raise SystemExit('Existing Internet Channel build preserved: ' + str(out))
    wad, manifest = build(local=True, revision=args.revision)
    if expected is not None and wad != expected:
        raise SystemExit('Internet Channel reproduction differs from build-v%d' % args.revision)
    manifest = dict(revision=args.revision, artifact=WAD, wad_sha256=hashlib.sha256(wad).hexdigest(), wad_size=len(wad),
                    configs={k: dict(path=v, sha256=hashlib.sha256((ROOT / v).read_bytes()).hexdigest()) for k, v in config_paths(args.revision).items()},
                    **manifest)
    out.mkdir(parents=True)
    (out / WAD).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(('Reproduced byte-identically' if expected is not None else 'Built'), 'Internet Channel local test revision', args.revision,
          '- lng', manifest['language_file']['translated'], 'manual runs', manifest['manual']['translated_runs'],
          'local URLs', sum(r['occurrences'] for r in manifest['executable']['local_urls']), 'sha256', manifest['wad_sha256'])


if __name__ == '__main__':
    main()

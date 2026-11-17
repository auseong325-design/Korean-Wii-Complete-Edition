"""Korean Internet Channel hardware candidate (never installed by this project).

  .venv\\Scripts\\python.exe scripts\\build_internet_hardware.py --revision 1 [--reproduce]

Same Korean resources as the local build, but every original URL and default
favorite address is kept (titles translated), no loopback redirect is present
(kwce.hardware checks the 127.0.0.x/localhost counts against the original) and
the WAD is fakesigned. The Internet Channel has no WiiLink patch: WiiLink only
redistributes the stock WAD. hardware_success_verified stays false.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.internet_build import build, ORIGINAL, config_paths  # noqa: E402
from kwce.hardware import hardware_wad  # noqa: E402

REVISIONS = (1, 2, 3, 4, 5, 6, 7, 8)
WAD = 'internet-ko-hardware-candidate.wad'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--revision', type=int, choices=REVISIONS, default=REVISIONS[-1])
    ap.add_argument('--reproduce', action='store_true')
    args = ap.parse_args()
    out = ROOT / f'workspace/channels/internet/hardware-v{args.revision}'
    expected = None
    if args.reproduce:
        expected = (out / WAD).read_bytes()
        n = 1
        while (ROOT / f'workspace/private/internet-hardware-reproduce-v{args.revision}-{n}').exists():
            n += 1
        out = ROOT / f'workspace/private/internet-hardware-reproduce-v{args.revision}-{n}'
    if out.exists():
        raise SystemExit('Existing Internet Channel hardware candidate preserved: ' + str(out))
    korean, manifest = build(local=False, revision=args.revision)
    if manifest['executable']['local_urls'] or any(r.get('urls') == 'local test pages' for r in manifest['favorites'].values()):
        raise SystemExit('Hardware candidate must not carry local test addresses')
    wad, checks = hardware_wad(korean, ORIGINAL.read_bytes())
    if expected is not None and wad != expected:
        raise SystemExit('Internet Channel hardware reproduction differs from hardware-v%d' % args.revision)
    manifest = dict(revision=args.revision, artifact=WAD, hardware_candidate=True, installed_anywhere=False,
                    wad_sha256=hashlib.sha256(wad).hexdigest(), wad_size=len(wad), unsigned_korean_sha256=hashlib.sha256(korean).hexdigest(),
                    hardware_checks=checks, wiilink_patch=None, urls_changed=[],
                    configs={k: dict(path=v, sha256=hashlib.sha256((ROOT / v).read_bytes()).hexdigest()) for k, v in config_paths(args.revision).items()},
                    **manifest)
    manifest['local_only'] = False
    out.mkdir(parents=True)
    (out / WAD).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(('Reproduced byte-identically' if expected is not None else 'Built'), 'Internet Channel hardware candidate revision', args.revision,
          '- fakesigned, original URLs, not installed; sha256', manifest['wad_sha256'])


if __name__ == '__main__':
    main()

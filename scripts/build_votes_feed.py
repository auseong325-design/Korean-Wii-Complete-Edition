"""Write the synthetic Votes feed (local-feed-v1) and, with --install, stage it in the test NAND.

local-feed-v1 is a preserved, byte-deterministic artifact: it holds first_data.bin, voting.bin,
ok.bin, routes.tsv and a fixture-manifest.json that satisfies kwce.channel_access.validate_fixtures.
It exercises the country graph, the regional map and the multi-language question switch - all of
which depend on WiiLink supply data the public service does not send for country 136.

  build_votes_feed.py                 # (re)write workspace/channels/votes/local-feed-v1 and verify
  build_votes_feed.py --reproduce     # rebuild into workspace/private and require byte-identical output
  build_votes_feed.py --install       # back up the sandbox feed, then copy local-feed-v1 into it

No Dolphin, no SD, no network, no server contact; the existing sandbox feed is backed up, never deleted.
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.votes_feed import build_feed
from kwce.channel_access import validate_fixtures

FEED = ROOT / 'workspace/channels/votes/local-feed-v1'
SANDBOX = ROOT / 'workspace/sandbox/votes-test-v1/local-feed'
PRIVATE = ROOT / 'workspace/private'


def _manifest(files):
    sha = lambda b: hashlib.sha256(b).hexdigest()
    route_bytes = ''.join(k + '\t' + v + '\n' for k, v in ROUTES.items()).encode('ascii')
    return dict(channel='votes', synthetic=True,
                routes_sha256=hashlib.sha256(route_bytes).hexdigest(),
                files=[dict(path=n, size=len(d), sha256=sha(d)) for n, d in files.items()]), route_bytes


FILES, ROUTES = build_feed()


def write_feed(dest):
    dest.mkdir(parents=True, exist_ok=True)
    manifest, route_bytes = _manifest(FILES)
    for name, data in FILES.items():
        (dest / name).write_bytes(data)
    (dest / 'routes.tsv').write_bytes(route_bytes)
    (dest / 'fixture-manifest.json').write_text(json.dumps(manifest, indent=2))
    rows, routes = validate_fixtures(dest, 'votes')
    return rows, routes, manifest


def digest(dest):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(dest.iterdir()) if p.is_file()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reproduce', action='store_true', help='rebuild into workspace/private, require identical bytes')
    ap.add_argument('--install', action='store_true', help='back up and copy local-feed-v1 into the test NAND feed')
    args = ap.parse_args()

    if args.reproduce:
        if not FEED.exists():
            raise SystemExit('local-feed-v1 does not exist yet; run without --reproduce first')
        expected = digest(FEED)
        n = 1
        while (PRIVATE / f'votes-feed-reproduce-{n}').exists():
            n += 1
        tmp = PRIVATE / f'votes-feed-reproduce-{n}'
        rows, routes, _ = write_feed(tmp)
        if digest(tmp) != expected:
            raise SystemExit('Votes feed reproduction differs from local-feed-v1')
        print(f'Reproduced byte-identically into {tmp} ({rows} files, {routes} routes)')
        return

    rows, routes, manifest = write_feed(FEED)
    print(json.dumps(dict(dest=str(FEED.relative_to(ROOT)), files=rows, routes=routes,
                          file_hashes={f['path']: f['sha256'][:16] for f in manifest['files']}), indent=2))

    if args.install:
        from prepare_channel_access import stopped
        stopped()
        for p in SANDBOX.parent.rglob('*'):
            if p.is_symlink() or p.is_junction():
                raise SystemExit('Indirect sandbox path refused')
        n = 1
        while (PRIVATE / f'votes-sandbox-feed-before-rich-{n}').exists():
            n += 1
        backup = PRIVATE / f'votes-sandbox-feed-before-rich-{n}'
        shutil.copytree(SANDBOX, backup)
        for name in list(FILES) + ['routes.tsv', 'fixture-manifest.json']:
            tmp = SANDBOX / (name + '.feed-tmp')
            tmp.write_bytes((FEED / name).read_bytes())
            tmp.replace(SANDBOX / name)
        rows, routes = validate_fixtures(SANDBOX, 'votes')
        print(f'Installed into {SANDBOX.relative_to(ROOT)} ({rows} files, {routes} routes); '
              f'previous feed backed up at {backup.relative_to(ROOT)}')


if __name__ == '__main__':
    main()

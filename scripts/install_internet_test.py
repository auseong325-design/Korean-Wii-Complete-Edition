"""Install a numbered Internet Channel local build into internet-test-v1.

  .venv\\Scripts\\python.exe scripts\\install_internet_test.py --revision N

Requires Dolphin to be closed. Keeps a private snapshot of the profile before
installing, updates configs/internet-runtime.lock.json (builds) and
workspace/channels/internet/active-build.json. The shared catalog is not
edited here; the lead merges workspace/channels/internet/catalog-entry.json.
"""
import argparse
import json
import shutil

from audit_sd import ROOT, PRIVATE, sha256
from prepare_channel_access import stopped
from prepare_gc_v6 import snapshot
from prepare_internet_test import register, PROFILE, BASE, LOCK, ACTIVE, FEED
import launch_dolphin as launcher
from kwce.channels import load_library


def refresh_feed(feed=FEED):
    """Copy the configured local feed into the profile and rebuild the lock's
    pinned feed files, so a newer feed revision (font-aware pages) takes effect."""
    fixture = json.loads((feed / 'fixture-manifest.json').read_text(encoding='utf-8'))
    if not (fixture.get('local_only') and fixture.get('synthetic') and fixture.get('fictional')) or fixture.get('accepts_orders_uploads_or_posts'):
        raise ValueError('Internet local feed scope differs')
    target = BASE / 'local-feed'
    for name in [r['path'] for r in fixture['files']] + ['routes.tsv', 'fixture-manifest.json']:
        shutil.copy2(feed / name, target / name)
    lock = json.loads(LOCK.read_text())
    for row in lock['files']:
        row['sha256'] = sha256(ROOT / row['path'])  # feed files changed; helper unchanged
    lock['feed_revision'] = fixture['revision']
    LOCK.write_text(json.dumps(lock, indent=2) + '\n')
    return fixture['revision']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--revision', type=int, required=True)
    ap.add_argument('--feed', type=int, default=None, help='local-feed-vN to install (default: the prepared feed)')
    args = ap.parse_args()
    feed_dir = FEED if args.feed is None else ROOT / f'workspace/channels/internet/local-feed-v{args.feed}'
    if not (feed_dir / 'fixture-manifest.json').is_file():
        raise SystemExit('Missing Internet Channel local feed: ' + feed_dir.name)
    stopped()
    register()
    wad = ROOT / f'workspace/channels/internet/build-v{args.revision}/internet-ko-local-test.wad'
    meta = json.loads(wad.with_name('build-manifest.json').read_text(encoding='utf-8'))
    if not meta.get('local_only') or sha256(wad) != meta['wad_sha256']:
        raise ValueError('Internet build identity/scope')
    n = 1
    while (PRIVATE / f'internet-before-install-{n}.json').exists():
        n += 1
    (PRIVATE / f'internet-before-install-{n}.json').write_text(json.dumps(snapshot(BASE / 'user'), indent=2))
    lib = load_library()
    title = lib.title.Title()
    title.load_wad(wad.read_bytes())
    lib.nand.EmuNAND(BASE / 'user/Wii').install_title(title)
    # Clear this channel's save so the new build's first-run bookmark import
    # runs again (a stale save from a prior run would leave favorites empty).
    data = BASE / 'user/Wii/title/00010001/48414445/data'
    cleared = []
    if data.exists():
        for p in sorted(data.iterdir()):
            if p.is_file() and not p.is_symlink():
                cleared.append(p.name)
                p.unlink()
    launcher.scrub_download_tasks(PROFILE)
    feed_revision = refresh_feed(feed_dir)
    ACTIVE.write_text(json.dumps(dict(revision=args.revision, wad_sha256=meta['wad_sha256'], feed_revision=feed_revision), indent=2) + '\n')
    lock = json.loads(LOCK.read_text())
    lock['builds'][str(args.revision)] = meta['wad_sha256']
    LOCK.write_text(json.dumps(lock, indent=2) + '\n')
    print('Installed Internet Channel build', args.revision, 'into internet-test-v1; local feed v%d, save cleared %s, lock and active build updated' % (feed_revision, cleared or 'none'))


if __name__ == '__main__':
    main()

"""Install a numbered synthetic Kirby TV feed into the sandbox's local-feed.

The numbered workspace/channels/kirbytv/local-feed-vN stays untouched; only the
sandbox server root is refreshed, the previous sandbox feed is recorded in
workspace/private first, and the runtime lock is updated to the new hashes.
"""
import argparse
import json
import shutil
from audit_sd import ROOT, PRIVATE, sha256
from prepare_channel_access import stopped
from prepare_kirbytv_test import register, BASE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', type=int, required=True)
    args = parser.parse_args()
    stopped()
    register()
    source = ROOT / f'workspace/channels/kirbytv/local-feed-v{args.revision}'
    manifest = json.loads((source / 'fixture-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('revision') != args.revision or not manifest.get('local_only') or not manifest.get('synthetic') \
            or manifest.get('real_episodes') or manifest.get('order_or_upload_accepted'):
        raise ValueError('Kirby TV feed scope differs')
    for row in manifest['files']:
        if '/' in row['path'] or '\\' in row['path'] or sha256(source / row['path']) != row['sha256']:
            raise ValueError('Kirby TV feed payload differs: ' + row['path'])
    feed = BASE / 'local-feed'
    number = 1
    while (PRIVATE / f'kirbytv-feed-before-install-{number}.json').exists():
        number += 1
    before = [dict(path=p.name, sha256=sha256(p)) for p in sorted(feed.iterdir()) if p.is_file()]
    (PRIVATE / f'kirbytv-feed-before-install-{number}.json').write_text(json.dumps(before, indent=2))
    for p in feed.iterdir():
        if p.is_file() and p.name not in {r['path'] for r in manifest['files']} | {'fixture-manifest.json'}:
            raise ValueError('Unexpected file in the sandbox feed: ' + p.name)
    for row in manifest['files']:
        shutil.copy2(source / row['path'], feed / row['path'])
        if sha256(feed / row['path']) != row['sha256']:
            raise ValueError('Feed copy mismatch: ' + row['path'])
    (feed / 'fixture-manifest.json').write_text(json.dumps(dict(
        revision=args.revision, local_only=True, synthetic=True, files=manifest['files']), indent=2))
    path = ROOT / 'configs/kirbytv-runtime.lock.json'
    lock = json.loads(path.read_text())
    prefix = 'workspace/sandbox/kirbytv-test-v1/local-feed/'
    lock['files'] = [r for r in lock['files'] if not r['path'].startswith(prefix)]
    for name in ['fixture-manifest.json', *(r['path'] for r in manifest['files'])]:
        lock['files'].append(dict(path=prefix + name, sha256=sha256(feed / name)))
    lock['feed_revision'] = args.revision
    path.write_text(json.dumps(lock, indent=2))
    print('Installed Kirby TV local-feed-v%d into the sandbox (%d files); runtime lock updated' % (args.revision, len(manifest['files'])))


if __name__ == '__main__':
    main()

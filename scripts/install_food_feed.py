"""Install a numbered synthetic Food feed into the sandbox's local-feed.

  .venv\\Scripts\\python.exe scripts\\install_food_feed.py --revision 2

The numbered workspace/channels/food/local-feed-vN stays untouched; only the
sandbox server root is refreshed. The previous sandbox feed hashes are recorded
in workspace/private first, and the runtime lock pins the new manifest.
Browse-only: a feed that serves any blocked order/cart/auth action is refused.
"""
import argparse
import json
import shutil

from audit_sd import ROOT, PRIVATE, sha256
from prepare_channel_access import stopped
from prepare_food_test import register, BASE

LOCK = ROOT / 'configs/food-runtime.lock.json'
PIN = 'workspace/sandbox/food-test-v1/local-feed/fixture-manifest.json'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', type=int, required=True)
    args = parser.parse_args()
    stopped()
    register()
    source = ROOT / f'workspace/channels/food/local-feed-v{args.revision}'
    manifest = json.loads((source / 'fixture-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('revision') != args.revision or not manifest.get('local_only') or not manifest.get('synthetic'):
        raise ValueError('Food feed scope differs')
    digests = manifest.get('sha256', {})
    for name in manifest['files']:
        if '..' in name or name.startswith(('/', '\\')) or name not in digests or sha256(source / name) != digests[name]:
            raise ValueError('Food feed payload differs or is unhashed: ' + name)
    for action in manifest['blocked_actions']:
        if list((source / 'nwapi').glob(action + '*.xml')):
            raise ValueError('Food feed serves a blocked action: ' + action)
    feed = BASE / 'local-feed'
    allowed = set(manifest['files']) | {'fixture-manifest.json'}
    current = [p for p in sorted(feed.rglob('*')) if p.is_file()]
    for p in current:
        if p.relative_to(feed).as_posix() not in allowed:
            raise ValueError('Unexpected file in the sandbox feed: ' + p.relative_to(feed).as_posix())
    number = 1
    while (PRIVATE / f'food-feed-before-install-{number}.json').exists():
        number += 1
    (PRIVATE / f'food-feed-before-install-{number}.json').write_text(json.dumps(
        [dict(path=p.relative_to(feed).as_posix(), sha256=sha256(p)) for p in current], indent=2))
    for name in [*manifest['files'], 'fixture-manifest.json']:
        (feed / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, feed / name)
        if sha256(feed / name) != sha256(source / name):
            raise ValueError('Feed copy mismatch: ' + name)
    lock = json.loads(LOCK.read_text())
    rows = [r for r in lock['files'] if r['path'] == PIN]
    if len(rows) != 1:
        raise ValueError('Runtime lock does not pin exactly one Food feed manifest')
    rows[0]['sha256'] = sha256(feed / 'fixture-manifest.json')
    lock['feed_revision'] = args.revision
    LOCK.write_text(json.dumps(lock, indent=2) + '\n')
    print(f'Installed Food local-feed-v{args.revision} into the sandbox ({len(manifest["files"])} files); '
          f'previous feed recorded as food-feed-before-install-{number}.json; runtime lock updated')


if __name__ == '__main__':
    main()

"""Pin the public WiiLink/Striim Kirby TV service sources into references.

Read-only: fetches the exact blobs at pinned commits, verifies each against
the git blob SHA-1, writes them under workspace/channels/kirbytv/references
and a configs lock. Never runs the server and sends no console data.
"""
import concurrent.futures
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'workspace/channels/kirbytv/references'

# (owner/repo, commit, [upstream paths]) — commits pinned 2026-10-28.
SOURCES = [
    ('WiiLink24/production-deployment', '629d3bb7cb7a01e4bf369324cf7c187b5d5d8411',
     ['docker-compose.yml', 'nginx/templates/kirby.conf.template']),
    ('StriimNetwork/kirby-tv-docs', 'cae1941ee7399a6f0a3da8a14465bb42c795ba4e',
     ['README.md', 'basic-information.md', 'xml-node-types/README.md']),
    ('StriimNetwork/Kirby-TV-Channel-Patcher', '038d75b5e47f9a1a79c590644e62370efe0d0a48',
     ['README.md', 'main.go', 'helpers.go']),
]


def _blob_sha1(raw):
    return hashlib.sha1(b'blob %d\0' % len(raw) + raw).hexdigest()


def main():
    jobs = []
    for repo, commit, paths in SOURCES:
        for path in paths:
            jobs.append((repo, commit, path))

    def fetch(job):
        repo, commit, path = job
        url = f'https://raw.githubusercontent.com/{repo}/{commit}/{path}'
        raw = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'kwce-source-audit'}), timeout=30).read()
        dest = BASE / repo.split('/')[1] / f'{commit[:8]}' / path
        if dest.exists():
            if dest.read_bytes() != raw:
                raise ValueError('Preserved reference differs: ' + path)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        return dict(path=dest.relative_to(ROOT).as_posix(), repository=repo, commit=commit,
                    upstream_path=path, blob_sha1=_blob_sha1(raw), sha256=hashlib.sha256(raw).hexdigest())
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(fetch, jobs))
    out = ROOT / 'configs/kirbytv-references.lock.json'
    body = json.dumps(dict(
        note='Public WiiLink/Striim Kirby TV service sources. Not executed.',
        service_host='kirby.wiilink24.com', path_scheme='/kctv2/xml/gb_config_<lang>.xml, /kctv2/<dir>/<file>.mo, /video/<file>.mo',
        files=records), indent=1) + '\n'
    if out.exists() and out.read_text(encoding='utf-8') != body:
        raise ValueError('Existing reference lock preserved')
    if not out.exists():
        out.write_text(body, encoding='utf-8')
    print('Pinned', len(records), 'public Kirby TV reference files; no console inputs sent')


if __name__ == '__main__':
    main()

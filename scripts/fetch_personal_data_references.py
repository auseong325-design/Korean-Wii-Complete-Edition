"""Pin WiiLink's public Set Personal Data source (GPL-3.0) by commit.

Reads only public GitHub files; never sends console material. Every blob is
verified against its git blob SHA-1 from the pinned tree, stored under
workspace/channels/personal-data/references/set-personal-data-<commit8>/ and
listed with SHA-256 in configs/personal-data-references.lock.json.
Existing files and an existing lock are never overwritten.
"""
import concurrent.futures,hashlib,json,sys,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPO='WiiLink24/set-personal-data'
COMMIT='18fa5a7d696dfb0f8c7fcdcd2fc5613f2c41dabf'  # master, 2024-12-19 "feat: Support apartment numbers"
TREE='c87a2fe4e65ca009ab0be581ab7942a58141a46b'
SKIP=('.idea/','.vscode/')
BASE=ROOT/f'workspace/channels/personal-data/references/set-personal-data-{COMMIT[:8]}'
LOCK=ROOT/'configs/personal-data-references.lock.json'

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'kwce-source-audit'}),timeout=60).read()

def main():
    commit=json.loads(get(f'https://api.github.com/repos/{REPO}/commits/{COMMIT}'))
    if commit['sha']!=COMMIT or commit['commit']['tree']['sha']!=TREE:raise ValueError('Pinned commit/tree differs')
    tree=json.loads(get(f'https://api.github.com/repos/{REPO}/git/trees/{TREE}?recursive=1'))
    if tree.get('truncated'):raise ValueError('Tree listing truncated')
    rows=[r for r in tree['tree']if r['type']=='blob'and not r['path'].startswith(SKIP)]
    def fetch(row):
        raw=get(f'https://raw.githubusercontent.com/{REPO}/{COMMIT}/{row["path"]}')
        if hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()!=row['sha']:raise ValueError('Public source blob differs: '+row['path'])
        path=BASE/row['path']
        if path.exists():
            if path.read_bytes()!=raw:raise ValueError('Preserved reference differs: '+row['path'])
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        return dict(path=path.relative_to(ROOT).as_posix(),upstream_path=row['path'],git_blob_sha1=row['sha'],sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6)as pool:records=sorted(pool.map(fetch,rows),key=lambda r:r['upstream_path'])
    lock=dict(repository=REPO,commit=COMMIT,tree=TREE,license='GPL-3.0',excluded_prefixes=list(SKIP),files=records)
    raw=json.dumps(lock,indent=2)+'\n'
    if LOCK.exists():
        if LOCK.read_text(encoding='utf-8')!=raw:raise ValueError('Existing reference lock preserved')
    else:LOCK.write_text(raw,encoding='utf-8')
    print('Pinned',REPO,COMMIT[:12],':',len(records),'files; no console inputs')

if __name__=='__main__':sys.exit(main())

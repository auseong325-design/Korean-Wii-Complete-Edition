"""Pin read-only public WiiLink24/cam-server source files by commit.

Only protocol/route source and its license are copied into the channel's
reference folder; the server itself is never executed. No console data,
title keys, tickets or resources are sent anywhere.
"""
import concurrent.futures,hashlib,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'workspace/private/photoprints-cam-server-source-index-20261028.json'
LOCK=ROOT/'configs/photoprints-references.lock.json'
REPO='cam-server'
COMMIT='ab059bc04567ed21a8bf219d8ea86fd4afacbd2d'
WANTED=('LICENSE','README.md','cam.py','models.py','formparser_override.py','render.py','config-example.py')

def wanted(path):
    return path in WANTED or(path.startswith(('camlib/','routes/'))and path.endswith('.py'))

def main():
    index=json.loads(INDEX.read_text(encoding='utf-8-sig'))
    if index['repository']!='WiiLink24/'+REPO or index['commit']!=COMMIT or index.get('truncated'):raise ValueError('Pinned cam-server index differs')
    base=ROOT/f'workspace/channels/photoprints/references/{REPO}-{COMMIT[:8]}'
    rows=[r for r in index['tree']if r['type']=='blob'and wanted(r['path'])]
    def fetch(row):
        url=f'https://raw.githubusercontent.com/WiiLink24/{REPO}/{COMMIT}/{row["path"]}'
        raw=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'kwce-source-audit'}),timeout=30).read()
        if hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()!=row['sha']:raise ValueError('Public source blob differs: '+row['path'])
        path=base/row['path']
        if path.exists():
            if path.read_bytes()!=raw:raise ValueError('Preserved reference differs: '+row['path'])
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        return dict(path=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(raw).hexdigest(),repository='WiiLink24/'+REPO,commit=COMMIT,upstream_path=row['path'],license='MIT')
    with concurrent.futures.ThreadPoolExecutor(max_workers=6)as pool:records=sorted(pool.map(fetch,rows),key=lambda r:r['path'])
    raw=json.dumps(dict(executed=False,purpose='read-only protocol reference for synthetic local feed shapes',files=records),indent=2)+'\n'
    if LOCK.exists()and LOCK.read_text(encoding='utf-8')!=raw:raise ValueError('Existing photoprints reference lock preserved')
    if not LOCK.exists():LOCK.write_text(raw,encoding='utf-8')
    print('Pinned public cam-server references:',len(records),'files at',COMMIT[:8],'; server not executed')
if __name__=='__main__':main()

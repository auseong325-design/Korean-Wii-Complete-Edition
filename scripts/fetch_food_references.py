"""Pin the public WiiLink Food Channel server source (read-only reference).

Fetches only the protocol-relevant files of WiiLink24/food-server at one
commit, verifies each git blob SHA-1, and records a create-once lock. The
server is never run; no console data is sent anywhere.
"""
import hashlib,json,sys,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPO='WiiLink24/food-server'
COMMIT='e7fc48f2cb45af17c33251637c8299c4c142af0f'  # master, 2026-01-19 "chore: run black"
FILES=['LICENSE.md','README.md','food.py','helpers.py','responses.py','models.py','config-example.py','requirements.txt',
       'thepantry/encodemii.py','thepantry/items.py','thepantry/menus.py','thepantry/restaurants.py','thepantry/forms.py']
INDEX=ROOT/'workspace/private/food-server-source-index-20261028.json'
BASE=ROOT/f'workspace/channels/food/references/food-server-{COMMIT[:8]}'
LOCK=ROOT/'configs/food-server-references.lock.json'
HEADERS={'User-Agent':'kwce-source-audit','Accept':'application/vnd.github+json'}

def get(url):return urllib.request.urlopen(urllib.request.Request(url,headers=HEADERS),timeout=30).read()

def main():
    if INDEX.exists():index=json.loads(INDEX.read_text(encoding='utf-8'))
    else:
        tree=json.loads(get(f'https://api.github.com/repos/{REPO}/git/trees/{COMMIT}?recursive=1'))
        if tree.get('truncated')or tree.get('sha')!=COMMIT and not tree.get('tree'):raise ValueError('Public tree listing incomplete')
        index=dict(repository=REPO,commit=COMMIT,tree=[dict(path=r['path'],type=r['type'],sha=r['sha'],size=r.get('size'))for r in tree['tree']])
        INDEX.parent.mkdir(parents=True,exist_ok=True);INDEX.write_text(json.dumps(index,indent=1),encoding='utf-8')
    if index['commit']!=COMMIT or index['repository']!=REPO:raise ValueError('Pinned index differs')
    blobs={r['path']:r for r in index['tree']if r['type']=='blob'}
    records=[]
    for name in FILES:
        row=blobs[name];raw=get(f'https://raw.githubusercontent.com/{REPO}/{COMMIT}/{name}')
        if hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()!=row['sha']:raise ValueError('Public source blob differs: '+name)
        path=BASE/name
        if path.exists():
            if path.read_bytes()!=raw:raise ValueError('Preserved reference differs: '+name)
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        records.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(raw).hexdigest(),repository=REPO,commit=COMMIT,upstream_path=name,git_blob_sha1=row['sha']))
    raw=json.dumps(dict(repository=REPO,commit=COMMIT,source='https://github.com/'+REPO,license='MIT (LICENSE.md)',server_executed=False,files=records),indent=2)+'\n'
    if LOCK.exists()and LOCK.read_text(encoding='utf-8')!=raw:raise ValueError('Existing food reference lock preserved')
    if not LOCK.exists():LOCK.write_text(raw,encoding='utf-8')
    print('Pinned public food-server references:',len(records),'files at',COMMIT[:8],'; server not executed, no console inputs')
if __name__=='__main__':main()

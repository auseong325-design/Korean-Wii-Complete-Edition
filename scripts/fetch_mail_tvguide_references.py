"""Read immutable public protocol sources; never upload console material."""
import concurrent.futures,hashlib,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    rows=[]
    for repo,channel in [('Mail-Server','mail'),('tv-api','tvguide')]:
        index=json.loads((ROOT/f'workspace/private/{repo}-source-index-20261025.json').read_text(encoding='utf-8-sig'))
        commit=index['commit'];base=ROOT/f'workspace/channels/{channel}/references/{repo}-{commit[:8]}'
        for row in index['tree']:
            if row['type']!='blob'or not(row['path'].endswith(('.go','.md','.json'))or row['path']=='LICENSE'):continue
            path=base/row['path'];url=f'https://raw.githubusercontent.com/WiiLink24/{repo}/{commit}/{row["path"]}'
            rows.append((path,url,row,commit,repo))
    def fetch(item):
        path,url,row,commit,repo=item
        raw=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'kwce-source-audit'}),timeout=30).read()
        if hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()!=row['sha']:raise ValueError('Public source blob differs')
        if path.exists():
            if path.read_bytes()!=raw:raise ValueError('Preserved reference differs')
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        return dict(path=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(raw).hexdigest(),repository='WiiLink24/'+repo,commit=commit,upstream_path=row['path'])
    with concurrent.futures.ThreadPoolExecutor(max_workers=6)as pool:records=list(pool.map(fetch,rows))
    out=ROOT/'configs/mail-tvguide-references.lock.json';raw=json.dumps(dict(files=records),indent=2)+'\n'
    if out.exists()and out.read_text()!=raw:raise ValueError('Existing protocol lock preserved')
    if not out.exists():out.write_text(raw)
    print('Pinned public mail/TV references:',len(records),'files; no console inputs')
if __name__=='__main__':main()

"""Download only the user-requested Forecast sources; no private data sent."""
import concurrent.futures,datetime,hashlib,json,sys,urllib.request,urllib.parse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'workspace/channels/forecast/originals'
BASE='https://repo.mariocube.com/WADs/_WiiWare, VC, DLC, Channels & IOS/F/'
FILES=[(f'forecast-{region.lower()}-v7.wad',BASE+f'Forecast Channel ({region}) (v7) (Channel).wad')for region in ['USA','Japan','Europe']]
FILES.append(('forecast-usa-wiilink-archive.wad','https://repo.mariocube.com/WADs/WiiLink/WAD/Forecast Channel (USA) (WiiLink).wad'))

def download(row):
    alias,url=row;url=urllib.parse.quote(url,safe=':/%&');target=DEST/alias
    if not target.exists():
        request=urllib.request.Request(url,headers={'User-Agent':'KWCE-local-research/0.1'})
        with urllib.request.urlopen(request,timeout=90)as response:
            payload=response.read(80*1024*1024+1)
            if len(payload)>80*1024*1024:raise ValueError('Download exceeds expected channel bounds')
            if payload[:4]!=b'\x00\x00\x00 ':raise ValueError('Download is not the expected WAD header')
            with target.open('xb')as file:file.write(payload)
    stat=target.stat()
    return dict(alias=alias,url=url,size=stat.st_size,mtime_ns=stat.st_mtime_ns,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),source='MarioCube archive; signature provenance not yet verified')

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:rows=list(pool.map(download,FILES))
    manifest=DEST/'acquisition.json'
    result=dict(acquired_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=rows)
    if not manifest.exists():manifest.write_text(json.dumps(result,indent=2),encoding='utf-8')
    else:
        previous=json.loads(manifest.read_text(encoding='utf-8'))
        if previous['files']!=rows:raise ValueError('Preserved channel source differs from acquisition manifest')
    print(json.dumps(dict(downloaded=len(rows),files=[{k:r[k]for k in ['alias','size','sha256']}for r in rows])))

if __name__=='__main__':main()

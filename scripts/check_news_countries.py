"""Inspect public News envelope metadata only; discard article content."""
import concurrent.futures,datetime,json,struct,sys,urllib.request,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library

def inspect(item):
    from libWiiPy.archive import decompress_lz77
    country,hour=item
    try:
        with urllib.request.urlopen(f'http://news.wiilink.ca/v2/1/{country:03d}/news.bin.{hour:02d}',timeout=15) as response:raw=response.read(8*1024*1024+1)
        if not 320<len(raw)<=8*1024*1024:raise ValueError('envelope')
        data=decompress_lz77(raw[320:]);version,size,crc,updated,end=struct.unpack_from('>5I',data)
        if version!=512 or size!=len(data) or zlib.crc32(data[12:])&0xffffffff!=crc or data[20]!=country or data[44]!=1:raise ValueError('header')
        epoch=datetime.datetime(2000,1,1,tzinfo=datetime.timezone.utc)
        expiry=epoch+datetime.timedelta(minutes=end)
        return dict(country=country,hour=hour,valid=True,expiry_utc=expiry.isoformat(),expired=expiry<datetime.datetime.now(datetime.timezone.utc))
    except Exception as error:return dict(country=country,hour=hour,valid=False,error=type(error).__name__)

def main():
    load_library();tasks=[(c,h) for c in (49,136) for h in range(24)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(inspect,tasks))
    n=1
    while (ROOT/f'workspace/private/news-country-audit-v{n}.json').exists():n+=1
    (ROOT/f'workspace/private/news-country-audit-v{n}.json').write_text(json.dumps(dict(checked_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),rows=rows,signature_verified=False),indent=2),encoding='utf-8')
    for country in (49,136):
        group=[r for r in rows if r['country']==country]
        print(f"country {country}: structurally valid {sum(r['valid'] for r in group)}/24, expired {sum(r.get('expired',False) for r in group)}/24; signature not verified")
if __name__=='__main__':main()

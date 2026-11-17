"""Inspect anonymous public News headers; never output/save articles or images."""
import concurrent.futures,datetime,json,struct,sys,urllib.request,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library

def inspect(hour):
    from libWiiPy.archive import decompress_lz77
    try:
        url=f'http://news.wiilink.ca/v2/1/136/news.bin.{hour:02d}'
        with urllib.request.urlopen(url,timeout=15)as response:raw=response.read(8*1024*1024+1)
        if not 320<len(raw)<=8*1024*1024:raise ValueError('Envelope size')
        data=decompress_lz77(raw[320:])
        if len(data)<104:raise ValueError('Header size')
        version,size,crc,updated,end=struct.unpack_from('>5I',data)
        if version!=512 or size!=len(data)or zlib.crc32(data[12:])&0xffffffff!=crc:raise ValueError('Header integrity')
        if data[20]!=136 or data[44]!=1:raise ValueError('Country/language')
        epoch=datetime.datetime(2000,1,1,tzinfo=datetime.timezone.utc)
        expires=epoch+datetime.timedelta(minutes=end)
        return dict(hour=hour,valid_structure=True,updated_utc=(epoch+datetime.timedelta(minutes=updated)).isoformat(),expires_utc=expires.isoformat(),expired=expires<datetime.datetime.now(datetime.timezone.utc))
    except Exception as error:return dict(hour=hour,valid_structure=False,error=type(error).__name__)

def main():
    load_library()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:rows=list(pool.map(inspect,range(24)))
    result=dict(checked_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),country=136,language=1,files=rows,valid=sum(r['valid_structure']for r in rows),expired=sum(r.get('expired',False)for r in rows),signature_verified=False,hardware_verified=False)
    folder=ROOT/'workspace/private';number=1
    while(folder/f'news-service-audit-v{number}.json').exists():number+=1
    (folder/f'news-service-audit-v{number}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k]for k in ['valid','expired','signature_verified','hardware_verified']}))
if __name__=='__main__':main()

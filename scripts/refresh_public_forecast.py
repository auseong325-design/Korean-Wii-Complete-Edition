"""Acquire public country-136 weather only; never submit console data."""
import datetime,hashlib,json,sys,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.forecast_cache import REFERENCES,inspect_public_download

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Forecast public endpoint redirected')

def main():
    now=datetime.datetime.now(datetime.timezone.utc);name='public-'+now.strftime('%Y%m%dT%H%M%SZ');folder=REFERENCES/name
    if folder.exists():raise SystemExit('Public snapshot already exists')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect());raw={};records={}
    for kind in ['forecast','short']:
        request=urllib.request.Request(f'http://fore.wiilink24.com/1/136/{kind}.bin',headers={'User-Agent':'KWCE-public-weather-local-test'})
        with opener.open(request,timeout=25)as response:
            if response.status!=200:raise ValueError('Public Forecast HTTP status')
            raw[kind]=response.read(1024*1024+1)
        records[kind]=inspect_public_download(raw[kind],kind)
        if not datetime.datetime.fromisoformat(records[kind]['opened_utc'])<=now<datetime.datetime.fromisoformat(records[kind]['closed_utc']):raise ValueError('Server public cache is outside current UTC validity')
    folder.mkdir()
    for kind in raw:
        with (folder/f'{kind}.bin').open('xb')as stream:stream.write(raw[kind])
    record=dict(fetched_utc=now.isoformat(),country=136,data_language=1,method='Host-only public HTTP download; no emulator network, no identifiers, no authentication',files=records)
    (folder/'manifest.json').write_text(json.dumps(record,indent=2))
    (REFERENCES/'active-public-snapshot.json').write_text(json.dumps(dict(snapshot=name,manifest_sha256=hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest())))
    print(json.dumps(record))

if __name__=='__main__':main()

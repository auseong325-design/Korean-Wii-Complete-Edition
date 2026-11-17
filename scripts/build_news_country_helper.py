"""Build a separately pinned, local-only replay helper for two country routes."""
import json,os,subprocess
from pathlib import Path
from audit_sd import ROOT,sha256

def main():
    out=ROOT/'tools/feed-sandbox/v4/bin'
    if out.exists():raise ValueError('Existing helper preserved')
    out.mkdir(parents=True)
    source=(ROOT/'scripts/FeedServer.cs').read_text(encoding='utf-8')
    old='string path=req[1],prefix="/v2/1/136/news.bin.";bool valid='
    new='string path=req[1],prefix=path.StartsWith("/v2/1/049/news.bin.")?"/v2/1/049/news.bin.":"/v2/1/136/news.bin.";bool valid='
    if source.count(old)!=1:raise ValueError('Helper route differs')
    source=source.replace(old,new).replace('Path.Combine(feed,"news.bin."+hour.ToString("00"))','Path.Combine(root,"local-feed/news.wiilink.ca/v2/1",prefix.Contains("/049/")?"049":"136","news.bin."+hour.ToString("00"))')
    server=out/'FeedServer-country.cs';server.write_text(source,encoding='utf-8')
    csc=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    for src,name in ((server,'FeedServer.exe'),(ROOT/'scripts/FeedRunner.cs','FeedRunner.exe')):
        subprocess.run([str(csc),'/nologo','/target:exe','/platform:x64','/out:'+str(out/name),str(src)],capture_output=True,check=True)
    files=[server,ROOT/'scripts/FeedRunner.cs',out/'FeedRunner.exe',out/'FeedServer.exe',ROOT/'workspace/sandbox/news-v1/NetProbe.exe']
    (out/'helper-build.json').write_text(json.dumps({'files':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha256(p)} for p in files]},indent=2),encoding='utf-8')
    print('PASS: local-only country helper v4 pinned; two exact routes')
if __name__=='__main__':main()

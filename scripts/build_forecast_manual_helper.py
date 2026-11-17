"""Build a separately locked capability-zero helper for the capture clone only."""
import json,os,subprocess
from pathlib import Path
from audit_sd import ROOT,sha256
from prepare_channel_access import stopped


def main():
    stopped();base=ROOT/'tools/channel-sandbox/v1/bin'
    lock=json.loads((base/'helper-build.json').read_text())
    for row in lock['files']:
        if sha256(ROOT/row['path'])!=row['sha256']:raise ValueError('Original helper differs')
    out=ROOT/'tools/channel-sandbox/manual-v1/bin'
    if out.exists():raise SystemExit('Existing manual helper preserved')
    text=(base/'ChannelRunner.cs').read_text()
    old='new string[]{"forecast-v1"}'
    if text.count(old)!=1:raise ValueError('Capture path guard identity')
    text=text.replace(old,'new string[]{"forecast-manual-v1"}')
    old='args[1]!="menu"&&args[1]!="forecast"&&args[1]!="forecast-preview"'
    if text.count(old)!=2:raise ValueError('Capture mode guard identity')
    text=text.replace(old,'args[1]!="forecast-preview"')
    out.mkdir(parents=True);source=out/'ChannelRunner.cs';source.write_text(text,encoding='utf-8');exe=out/'AppContainerRunner.exe'
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler),'/nologo','/target:exe','/platform:x64','/out:'+str(exe),str(source)],check=True)
    files=lock['files']+[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256(p))for p in [source,exe,Path(__file__),ROOT/'workspace/sandbox/forecast-manual-v1/NetProbe.exe']]
    (out/'helper-build.json').write_text(json.dumps(dict(capability_count=0,capture_only=True,files=files),indent=2))
    print('Built separately locked capture-only capability-zero helper; original helper preserved')


if __name__=='__main__':main()

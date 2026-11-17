"""New immutable capability-zero review helper, including cached Wii Menu."""
import json,os,subprocess
from pathlib import Path
from audit_sd import ROOT,sha256
from prepare_channel_access import stopped


def main():
    stopped();base=ROOT/'tools/channel-sandbox/review-v1/bin';out=ROOT/'tools/channel-sandbox/review-v2/bin'
    if out.exists():raise SystemExit('Existing review helper preserved')
    lock=json.loads((base/'helper-build.json').read_text())
    for row in lock['files']:
        if sha256(ROOT/row['path'])!=row['sha256']:raise ValueError('Previous helper differs')
    text=(base/'ChannelRunner.cs').read_text()
    guard='args[1]!="menu"&&args[1]!="forecast"&&args[1]!="forecast-preview"'
    if text.count(guard)!=2:raise ValueError('Mode guard identity')
    text=text.replace(guard,guard+'&&args[1]!="menu-preview"')
    text=text.replace('args[1]=="forecast-preview"?', '(args[1]=="forecast-preview"||args[1]=="menu-preview")?')
    text=text.replace('args[1]=="menu"?', '(args[1]=="menu"||args[1]=="menu-preview")?')
    out.mkdir(parents=True);cs=out/'ChannelRunner.cs';cs.write_text(text,encoding='utf-8');exe=out/'AppContainerRunner.exe'
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler),'/nologo','/target:exe','/platform:x64','/out:'+str(exe),str(cs)],check=True)
    files=lock['files']+[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256(p))for p in [cs,exe,Path(__file__)]]
    (out/'helper-build.json').write_text(json.dumps(dict(capability_count=0,review_only=True,cached_menu=True,files=files),indent=2))
    print('Built fixed-root review helper v2; zero capabilities and network probes preserved')


if __name__=='__main__':main()

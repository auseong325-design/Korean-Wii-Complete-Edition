"""Build immutable capability-zero access helpers, preserving the News pair."""
import json, os, subprocess, argparse, shutil
from pathlib import Path
from audit_sd import ROOT, sha256

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,default=2);args=ap.parse_args()
    if not 1<=args.revision<=20:raise SystemExit('Invalid helper revision')
    out=ROOT/f'tools/channel-access/v{args.revision}/bin'
    if out.exists(): raise SystemExit('Existing helper preserved')
    out.mkdir(parents=True)
    text=(ROOT/'scripts/FeedRunner.cs').read_text()
    text=text.replace('class FeedRunner', 'class ChannelTestRunner').replace('FeedServer.exe','ChannelTestServer.exe')
    text=text.replace('bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","news-v1"),StringComparison.OrdinalIgnoreCase);', '''string key=Path.GetFileName(root);
   string expected=key=="votes-test-v1"?"0001000148414a45":key=="nintendo-test-v1"?"0001000148415445":key=="mii-contest-test-v1"?"0001000148415045":null;
   bool approved=expected!=null&&String.Equals(root,Path.Combine(project,"workspace","sandbox",key),StringComparison.OrdinalIgnoreCase);''')
    text=text.replace('args[2]!="0001000248414745"','args[2]!=expected').replace('approved News title','approved local-test title')
    text=text.replace('args.Length!=3||args[2]!=expected||(args[1]!="menu"&&args[1]!="channel")',
        'args.Length!=3||!((args[1]=="avatar"&&key=="mii-contest-test-v1"&&args[2]=="0001000248414341")||(args[2]==expected&&(args[1]=="menu"||args[1]=="channel")))')
    runner=out/'ChannelTestRunner.cs';runner.write_text(text,encoding='utf-8')
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    server=out/'ChannelTestServer.cs';shutil.copy2(ROOT/'scripts/ChannelTestServer.cs',server)
    sources=[runner,server];paths=[ROOT/'scripts/FeedRunner.cs',*sources]
    for source in sources:
        exe=out/(source.stem+'.exe')
        subprocess.run([str(compiler),'/nologo','/target:exe','/platform:x64','/out:'+str(exe),str(source)],check=True)
        paths.append(exe)
    for channel in ['votes','nintendo','mii-contest']:paths.append(ROOT/f'workspace/sandbox/{channel}-test-v1/NetProbe.exe')
    (out/'helper-build.json').write_text(json.dumps(dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256(p))for p in paths]),indent=2))
    print('Built separate capability-zero helper pair')

if __name__=='__main__':main()

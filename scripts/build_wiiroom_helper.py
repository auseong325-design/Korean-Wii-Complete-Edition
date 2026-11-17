"""Separate immutable Wii Room capability-zero helper; old helpers untouched."""
import json,os,subprocess
from pathlib import Path
from audit_sd import ROOT,sha256

def main():
    out=ROOT/'tools/wiiroom-sandbox/v1/bin'
    target=ROOT/'configs/wiiroom-runtime.lock.json'
    if out.exists()or target.exists():raise SystemExit('Existing Wii Room helper/lock preserved')
    original=ROOT/'tools/channel-access/v12/bin/ChannelTestRunner.cs'
    previous=json.loads((original.parent/'helper-build.json').read_text())
    if not any(r['path']==original.relative_to(ROOT).as_posix()and r['sha256']==sha256(original)for r in previous['files']):raise ValueError('Original helper lock differs')
    text=original.read_text();start='string expected=key=="votes-test-v1"?"0001000148414a45":key=="nintendo-test-v1"?"0001000148415445":key=="mii-contest-test-v1"?"0001000148415045":null;'
    guard='args.Length!=3||!((args[1]=="avatar"&&key=="mii-contest-test-v1"&&args[2]=="0001000248414341")||(args[2]==expected&&(args[1]=="menu"||args[1]=="channel")))'
    if text.count(start)!=1 or text.count(guard)!=1:raise ValueError('Helper derivation anchor differs')
    text=text.replace(start,'string expected=key=="wiiroom-test-v1"?"000100014843494a":null;').replace(guard,'args.Length!=3||args[2]!=expected||(args[1]!="menu"&&args[1]!="channel")').replace('ChannelTestRunner','WiiRoomRunner').replace('ChannelTestServer.exe','WiiRoomServer.exe')
    server=(ROOT/'scripts/ChannelTestServer.cs').read_text().replace('class ChannelTestServer','class WiiRoomServer').replace('bool nas=path=="/ac"||path=="/pr";','bool nas=false;')
    out.mkdir(parents=True);(out/'WiiRoomRunner.cs').write_text(text,encoding='utf-8');(out/'WiiRoomServer.cs').write_text(server,encoding='utf-8')
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    for source in out.glob('*.cs'):
        subprocess.run([str(compiler),'/nologo','/target:exe','/platform:x64','/out:'+str(source.with_suffix('.exe')),str(source)],check=True)
    files=[original,ROOT/'scripts/ChannelTestServer.cs',*(p for p in sorted(out.iterdir())if p.suffix in('.cs','.exe'))]
    (out/'helper-build.json').write_text(json.dumps(dict(capability_count=0,profile='wiiroom-test-v1-user',files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256(p))for p in files]),indent=2))
    root=ROOT/'workspace/sandbox/wiiroom-test-v1'
    lock=dict(runtime_version='2609a',capability_count=0,external_network_allowed=False,profile='wiiroom-test-v1-user',title_id='000100014843494a',files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256(p))for p in[root/'Dolphin-x64/Dolphin.exe',root/'NetProbe.exe',out/'helper-build.json',root/'local-feed/fixture-manifest.json',ROOT/'workspace/channels/wiiroom/build-v1/build-manifest.json']])
    lock['builds']={str(i):json.loads((ROOT/f'workspace/channels/wiiroom/build-v{i}/build-manifest.json').read_text())['wad_sha256']for i in range(1,7)if(ROOT/f'workspace/channels/wiiroom/build-v{i}/build-manifest.json').exists()}
    target.write_text(json.dumps(lock,indent=2));print('Built Wii Room helper v1: one profile/title, capability 0, local fixture routes only')

if __name__=='__main__':main()

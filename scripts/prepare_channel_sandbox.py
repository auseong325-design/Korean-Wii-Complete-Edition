"""Compile a separate offline channel AppContainer runner, preserve GC helpers."""
import json,os,subprocess
from pathlib import Path
from audit_sd import ROOT,sha256

def main():
    if 'dolphin.exe' in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin before helper build')
    folder=ROOT/'tools/channel-sandbox/v1/bin';folder.mkdir(parents=True,exist_ok=True)
    original=ROOT/'scripts/AppContainerRunner.cs';text=original.read_text()
    replacements=[('"../../.."','"../../../.."'),('new string[]{"gc-v2","gc-v3","gc-v4","gc-v5"}','new string[]{"forecast-v1"}'),('args[1]!="menu"&&args[1]!="disc"','args[1]!="menu"&&args[1]!="forecast"&&args[1]!="forecast-preview"'),('args[1]!="menu"&&!root.EndsWith("gc-v5",StringComparison.OrdinalIgnoreCase)','args[1]!="menu"&&args[1]!="forecast"&&args[1]!="forecast-preview"'),('string boot=args[1]=="disc"?" --exec "+Quote(Path.Combine(root,"disc/GALJ01.iso")):" --nand_title 0000000100000002";','string boot=args[1]=="menu"?" --nand_title 0000000100000002":" --nand_title 0001000248414645";'),('Path.Combine(root,"Dolphin-x64","Dolphin.exe")','Path.Combine(root,"Dolphin-x64",args[1]=="forecast-preview"?"Dolphin-cache-preview.exe":"Dolphin.exe")')]
    for old,new in replacements:
        if text.count(old)!=1:raise ValueError('Channel helper source guard failed')
        text=text.replace(old,new)
    old='Path.Combine(root,"Dolphin-x64",args[1]=="forecast-preview"?"Dolphin-cache-preview.exe":"Dolphin.exe")'
    if text.count(old)!=1:raise ValueError('Replay distribution guard failed')
    text=text.replace(old,'Path.Combine(root,args[1]=="forecast-preview"?"Dolphin-replay-x64":"Dolphin-x64","Dolphin.exe")')
    generated=folder/'ChannelRunner.cs';generated.write_text(text,encoding='utf-8')
    csc=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe';exe=folder/'AppContainerRunner.exe'
    subprocess.run([str(csc),'/nologo','/target:exe','/platform:x64','/out:'+str(exe),str(generated)],check=True)
    probe_source=ROOT/'scripts/NetProbe.cs';probe=ROOT/'workspace/sandbox/forecast-v1/NetProbe.exe'
    subprocess.run([str(csc),'/nologo','/target:exe','/platform:x64','/out:'+str(probe),str(probe_source)],check=True)
    tracked=[original,generated,exe,Path(__file__).resolve(),probe_source,probe]
    manifest=dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256(p))for p in tracked])
    (folder/'helper-build.json').write_text(json.dumps(manifest,indent=2))
    subprocess.run([str(exe),str(ROOT/'workspace/sandbox/forecast-v1'),'probe'],check=True)

if __name__=='__main__':main()

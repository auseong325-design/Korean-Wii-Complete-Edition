"""Clone stopped GC v6 into a dedicated Votes NAND and capability-zero runner."""
import configparser,json,os,shutil,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
from prepare_gc_v6 import snapshot
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
import launch_dolphin as launcher
def register():
 launcher.NATIVE_PROFILES['votes-v1-user']='workspace/sandbox/votes-v1';launcher.PROFILES=(*launcher.PROFILES,'votes-v1-user')
def main():
 if 'dolphin.exe'in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin before Votes preparation')
 target=ROOT/'workspace/sandbox/votes-v1';parent=ROOT/'workspace/sandbox/gc-v6';forecast=ROOT/'workspace/sandbox/forecast-v1'
 if target.exists():raise SystemExit('Existing Votes profile preserved')
 launcher.validate('gc-native-v6-user');launcher.validate_native_runtime('gc-native-v6-user')
 before=snapshot(forecast);(PRIVATE/'forecast-v12-before-votes-manifest.json').write_text(json.dumps(before))
 for folder in ['user','Dolphin-x64']:shutil.copytree(parent/folder,target/folder,ignore=shutil.ignore_patterns('Logs','ScreenShots','Cache','StateSaves'))
 shutil.copy2(forecast/'NetProbe.exe',target/'NetProbe.exe')
 p=target/'user/Config/Dolphin.ini';c=configparser.ConfigParser(strict=False);c.optionxform=str;c.read(p,encoding='utf-8-sig')
 for section in c.sections():
  for key,value in list(c[section].items()):c[section][key]=value.replace(str(parent),str(target))
 c['Core']['DefaultISO']='';c['Core']['OverrideRegionSettings']='True'
 with p.open('w',encoding='utf-8')as stream:c.write(stream)
 lib=load_library();t=lib.title.Title();t.load_wad((ROOT/'workspace/channels/votes/build-v10/votes-ko-ui-test.wad').read_bytes())
 if (target/'user/Wii/title/00010001/48414a45').exists():raise ValueError('Votes already present')
 lib.nand.EmuNAND(target/'user/Wii').install_title(t);register();launcher.scrub_download_tasks('votes-v1-user');launcher.validate('votes-v1-user')
 src=ROOT/'tools/channel-sandbox/v1/bin/ChannelRunner.cs';old=json.loads((src.parent/'helper-build.json').read_text())
 for row in old['files']:
  if sha256(ROOT/row['path'])!=row['sha256']:raise ValueError('Existing channel helper changed')
 folder=ROOT/'tools/votes-sandbox/v1/bin';folder.mkdir(parents=True)
 text=src.read_text().replace('forecast-v1','votes-v1').replace('0001000248414645','0001000148414a45').replace('forecast','votes')
 generated=folder/'VotesRunner.cs';generated.write_text(text,encoding='utf-8');exe=folder/'AppContainerRunner.exe'
 subprocess.run([str(Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'),'/nologo','/target:exe','/platform:x64','/out:'+str(exe),str(generated)],check=True)
 paths=[src,generated,exe,target/'NetProbe.exe'];record=dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256(p))for p in paths])
 (folder/'helper-build.json').write_text(json.dumps(record,indent=2));subprocess.run([str(exe),str(target),'probe'],check=True)
 if snapshot(forecast)!=before:raise ValueError('Forecast profile changed')
 print(json.dumps(dict(prepared=True,profile='votes-v1-user',forecast_files_preserved=len(before))))
if __name__=='__main__':main()

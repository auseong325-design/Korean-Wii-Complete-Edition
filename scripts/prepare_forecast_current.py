"""Create the current weather test profile without changing preserved users."""
import configparser,json,os,re,shutil,subprocess
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_gc_v6 import snapshot


def main():
    stopped();source=ROOT/'workspace/sandbox/forecast-review-v1';target=ROOT/'workspace/sandbox/forecast-v2'
    helper=ROOT/'tools/channel-sandbox/forecast-v2/bin'
    if target.exists()or helper.exists():raise SystemExit('Existing current weather profile preserved')
    revision=json.loads((source/'active-build.json').read_text())['revision']
    meta=json.loads((ROOT/f'workspace/channels/forecast/build-v{revision}/build-manifest.json').read_text(encoding='utf-8'))
    if revision<95 or meta.get('visual_diagnostic_only'):raise SystemExit('A normal final candidate must be installed first')
    for p in source.rglob('*'):
        if p.is_symlink()or p.is_junction():raise ValueError('Indirect source refused')
    before=snapshot(source);record=PRIVATE/'forecast-review-before-current-v2.json'
    if record.exists():raise SystemExit('Existing preservation record retained')
    record.write_text(json.dumps(before))
    target.mkdir()
    for folder in ['user','Dolphin-x64','Dolphin-replay-x64']:
        shutil.copytree(source/folder,target/folder,ignore=shutil.ignore_patterns('Cache','Logs','ScreenShots','StateSaves'))
    shutil.copy2(source/'NetProbe.exe',target/'NetProbe.exe')
    (target/'active-build.json').write_text(json.dumps(dict(revision=revision)))
    (target/'current-profile.json').write_text(json.dumps(dict(schema=1,purpose='localized-forecast-current-cache',real_emulator_network=False)))
    for p in (target/'user/Config').glob('*.ini'):
        p.write_text(p.read_text(encoding='utf-8-sig').replace(str(source),str(target)),encoding='utf-8')
    ini=target/'user/Config/Dolphin.ini';c=configparser.ConfigParser(strict=False);c.optionxform=str;c.read(ini,encoding='utf-8-sig')
    c['Core']['DefaultISO']='';c['Core']['EnableCustomRTC']='False';c['Interface']['ConfirmStop']='False'
    with ini.open('w',encoding='utf-8')as stream:c.write(stream)
    controls=target/'user/Config/WiimoteNew.ini';text=controls.read_text(encoding='utf-8-sig')
    values={'Buttons/A':'`Click 0` | `Z` | pulse(`Click 0`, 0.3) | pulse(`Z`, 0.3)',
            'Buttons/B':'`Click 1` | `X` | pulse(`Click 1`, 0.3) | pulse(`X`, 0.3)',
            'Buttons/Home':'RETURN | pulse(`Click 2`, 0.25)','D-Pad/Down':'DOWN'}
    for key,value in values.items():text=re.sub(r'^'+re.escape(key)+r'\s*=.*$',key+' = '+value,text,flags=re.M)
    controls.write_text(text,encoding='utf-8')
    binding=json.loads((ROOT/'configs/forecast-cache-profiles.lock.json').read_text())['profiles'][source.name]
    (target/'cache-snapshot.json').write_text(json.dumps(binding));(target/'cache-mode.json').write_text(json.dumps(dict(localized=True)))
    base=ROOT/'tools/channel-sandbox/review-v2/bin';lock=json.loads((base/'helper-build.json').read_text())
    for row in lock['files']:
        if sha256(ROOT/row['path'])!=row['sha256']:raise ValueError('Previous helper changed')
    text=(base/'ChannelRunner.cs').read_text();old='new string[]{"forecast-review-v1"}'
    if text.count(old)!=1:raise ValueError('Root scope identity')
    helper.mkdir(parents=True);cs=helper/'ChannelRunner.cs';cs.write_text(text.replace(old,'new string[]{"forecast-v2"}'),encoding='utf-8');exe=helper/'AppContainerRunner.exe'
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler),'/nologo','/target:exe','/platform:x64','/out:'+str(exe),str(cs)],check=True)
    files=lock['files']+[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256(p))for p in [cs,exe,Path(__file__)]]
    (helper/'helper-build.json').write_text(json.dumps(dict(capability_count=0,current_only=True,cached_menu=True,files=files),indent=2))
    if snapshot(source)!=before:raise ValueError('Review source changed during clone')
    print('Prepared independent current weather profile and capability-zero helper; source preserved')


if __name__=='__main__':main()

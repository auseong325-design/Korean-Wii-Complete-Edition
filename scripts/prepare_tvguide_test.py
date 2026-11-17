"""Separate Korean locale TV Guide NAND and zero-capability fixture helper."""
import configparser,json,os,shutil,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_gc_v6 import snapshot
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
import launch_dolphin as launcher
PROFILE='tvguide-test-v1-user';TITLE='0001000148424e4a';BASE=ROOT/'workspace/sandbox/tvguide-test-v1';HELPER=ROOT/'tools/tvguide-sandbox/v1/bin'
def register():
    launcher.NATIVE_PROFILES[PROFILE]='workspace/sandbox/tvguide-test-v1'
    if PROFILE not in launcher.PROFILES:launcher.PROFILES=(*launcher.PROFILES,PROFILE)
def main():
    stopped()
    if BASE.exists()or HELPER.exists():raise SystemExit('Existing TV profile/helper preserved')
    source=ROOT/'workspace/sandbox/votes-test-v1';before=snapshot(source);(PRIVATE/'tvguide-template-before-v1.json').write_text(json.dumps(before,indent=2));BASE.mkdir(parents=True)
    for name in ['user','Dolphin-x64']:shutil.copytree(source/name,BASE/name,ignore=shutil.ignore_patterns('Logs','Cache','ScreenShots','StateSaves'))
    shutil.copy2(source/'NetProbe.exe',BASE/'NetProbe.exe')
    path=BASE/'user/Config/Dolphin.ini';cfg=configparser.ConfigParser(strict=False);cfg.optionxform=str;cfg.read(path,encoding='utf-8-sig')
    for section in cfg.sections():
        for key,value in cfg[section].items():cfg[section][key]=value.replace(str(source),str(BASE)).replace(source.as_posix(),BASE.as_posix())
    cfg['Core']['DefaultISO']='';cfg['Core']['EnableWiiLink']='False';cfg['Core']['OverrideRegionSettings']='True'
    for key in ['WiiSDCard','WiiSDCardEnableFolderSync','WiiSDCardAllowWrites']:cfg['Core'][key]='False'
    with path.open('w',encoding='utf-8')as f:cfg.write(f)
    lib=load_library();title=lib.title.Title();wad=ROOT/'workspace/channels/tvguide/build-v1/tvguide-ko-local-test.wad';title.load_wad(wad.read_bytes());lib.nand.EmuNAND(BASE/'user/Wii').install_title(title)
    register();launcher.scrub_download_tasks(PROFILE);launcher.validate(PROFILE)
    feed=BASE/'local-feed';feed.mkdir();(feed/'routes.tsv').write_text('');(feed/'fixture-manifest.json').write_text(json.dumps(dict(revision=1,local_only=True,synthetic=True,files=[]),indent=2))
    text=(ROOT/'scripts/FeedRunner.cs').read_text();old='bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","news-v1"),StringComparison.OrdinalIgnoreCase);'
    if text.count(old)!=1:raise ValueError('TV helper source guard')
    text=text.replace(old,'bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","tvguide-test-v1"),StringComparison.OrdinalIgnoreCase);').replace('0001000248414745',TITLE).replace('class FeedRunner','class TvGuideRunner').replace('FeedServer.exe','TvGuideServer.exe')
    server=(ROOT/'scripts/ChannelTestServer.cs').read_text().replace('class ChannelTestServer','class TvGuideServer').replace('bool nas=path=="/ac"||path=="/pr";','bool nas=false;')
    HELPER.mkdir(parents=True);(HELPER/'TvGuideRunner.cs').write_text(text,encoding='utf-8');(HELPER/'TvGuideServer.cs').write_text(server,encoding='utf-8')
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    for sourcefile in HELPER.glob('*.cs'):subprocess.run([str(compiler),'/nologo','/target:exe','/platform:x64','/out:'+str(sourcefile.with_suffix('.exe')),str(sourcefile)],check=True,capture_output=True)
    locked=[BASE/'Dolphin-x64/Dolphin.exe',BASE/'NetProbe.exe',*(p for p in sorted(HELPER.iterdir())if p.suffix in('.cs','.exe')),feed/'fixture-manifest.json']
    manifest=json.loads(wad.with_name('build-manifest.json').read_text(encoding='utf-8'))
    (ROOT/'configs/tvguide-runtime.lock.json').write_text(json.dumps(dict(profile=PROFILE,title_id=TITLE,capability_count=0,external_network_allowed=False,files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256(p))for p in locked],builds={'1':manifest['wad_sha256']}),indent=2))
    (ROOT/'workspace/channels/tvguide/active-build.json').write_text(json.dumps(dict(revision=1,wad_sha256=manifest['wad_sha256']),indent=2))
    path=ROOT/'configs/channels.catalog.json';catalog=json.loads(path.read_text(encoding='utf-8'));catalog['channels'].append(dict(id='tvguide',display_name_ko='TV 가이드',title_id=TITLE,base_region='Japan',base_version=512,stage='internal-review',full_localization_complete=False,installs=[dict(profile='tvguide-test-v1',artifact='build-v1',role='active',launch='scripts/launch_tvguide.py')],status_doc='docs/channels/tvguide.md',run_doc='docs/channels/run-tvguide.md',remaining='첫 실행/편성표·지역/TV 리모컨·배너 그림·설명서·오류 전체 검수, 합성 편성 응답과 WiiLink 연동',installer_selectable=False,public_WAD_distribution=False,hardware_validation=False,emulator_live_service_verified=False));path.write_text(json.dumps(catalog,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    if snapshot(source)!=before:raise ValueError('TV template changed')
    print('Installed TV Guide v1 in separate sanitized Korean profile; original/template preserved; capability-zero helper ready')
if __name__=='__main__':main()

"""Isolated Korean-locale profile for the Korean Set Personal Data build.

Clones the sanitized votes-test-v1 profile (Korean 9 / Korea 136, offline WC24,
SD off, no keys.bin) into workspace/sandbox/personal-data-test-v1, installs
build-v1 through libWiiPy EmuNAND, copies local-feed-v1 (no routes: SPD has no
service), compiles the capability-0 AppContainer helper from
scripts/FeedRunner.cs + scripts/ChannelTestServer.cs and writes
configs/personal-data-runtime.lock.json. The hidden title is booted directly
with Dolphin's --nand_title. The shared catalog is not edited
(workspace/channels/personal-data/catalog-entry.json carries the row).
"""
import configparser,json,os,shutil,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_gc_v6 import snapshot
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
import launch_dolphin as launcher
PROFILE='personal-data-test-v1-user';TITLE='000100084843434a'
BASE=ROOT/'workspace/sandbox/personal-data-test-v1';HELPER=ROOT/'tools/personal-data-sandbox/v1/bin'
CHANNEL=ROOT/'workspace/channels/personal-data';FEED=CHANNEL/'local-feed-v1';WAD_NAME='personal-data-ko-local-test.wad'
LOCK=ROOT/'configs/personal-data-runtime.lock.json';TEMPLATE=ROOT/'workspace/sandbox/votes-test-v1'
PD_DIR=BASE/'user/Wii/title/00010008/4843434a/data/nocopy'

def register():
    launcher.NATIVE_PROFILES[PROFILE]='workspace/sandbox/personal-data-test-v1'
    if PROFILE not in launcher.PROFILES:launcher.PROFILES=(*launcher.PROFILES,PROFILE)

def build_wad(revision):
    wad=CHANNEL/f'build-v{revision}'/WAD_NAME;meta=json.loads(wad.with_name('build-manifest.json').read_text(encoding='utf-8'))
    if not meta.get('local_only')or meta.get('title_id')!=TITLE or sha256(wad)!=meta['wad_sha256']:raise ValueError('Personal-data build identity/scope')
    return wad,meta

def feed_manifest(folder):
    record=json.loads((folder/'fixture-manifest.json').read_text(encoding='utf-8'))
    if not(record.get('local_only')and record.get('synthetic')and record.get('fictional')):raise ValueError('Personal-data fixture scope differs')
    for row in record['files']:
        p=folder/row['path']
        if Path(row['path']).name!=row['path']or not p.is_file()or sha256(p)!=row['sha256']:raise ValueError('Personal-data fixture payload differs')
    if (folder/'routes.tsv').read_bytes()!=b'':raise ValueError('Personal-data fixture must not serve routes')
    return record

def helper_sources():
    runner=(ROOT/'scripts/FeedRunner.cs').read_text()
    old='bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","news-v1"),StringComparison.OrdinalIgnoreCase);'
    if runner.count(old)!=1 or runner.count('0001000248414745')!=1 or runner.count('class FeedRunner')!=1:raise ValueError('Personal-data helper source guard')
    runner=runner.replace(old,'bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","personal-data-test-v1"),StringComparison.OrdinalIgnoreCase);')
    runner=runner.replace('0001000248414745',TITLE).replace('class FeedRunner','class PersonalDataRunner').replace('FeedServer.exe','PersonalDataServer.exe')
    server=(ROOT/'scripts/ChannelTestServer.cs').read_text();nas='bool nas=path=="/ac"||path=="/pr";'
    if server.count('class ChannelTestServer')!=1 or server.count(nas)!=1:raise ValueError('Personal-data server source guard')
    return runner,server.replace('class ChannelTestServer','class PersonalDataServer').replace(nas,'bool nas=false;')

def main():
    stopped()
    if BASE.exists()or HELPER.exists():raise SystemExit('Existing personal-data profile/helper preserved')
    wad,meta=build_wad(1);feed_manifest(FEED)
    before=snapshot(TEMPLATE);(PRIVATE/'personal-data-template-before-v1.json').write_text(json.dumps(before,indent=2));BASE.mkdir(parents=True)
    for name in['user','Dolphin-x64']:shutil.copytree(TEMPLATE/name,BASE/name,ignore=shutil.ignore_patterns('Logs','Cache','ScreenShots','StateSaves'))
    shutil.copy2(TEMPLATE/'NetProbe.exe',BASE/'NetProbe.exe')
    if (BASE/'user/Wii/title/00010008/4843434a').exists():raise ValueError('Template already holds an HCCJ title/data')
    path=BASE/'user/Config/Dolphin.ini';cfg=configparser.ConfigParser(strict=False);cfg.optionxform=str;cfg.read(path,encoding='utf-8-sig')
    for section in cfg.sections():
        for key,value in cfg[section].items():cfg[section][key]=value.replace(str(TEMPLATE),str(BASE)).replace(TEMPLATE.as_posix(),BASE.as_posix())
    cfg['Core']['DefaultISO']='';cfg['Core']['EnableWiiLink']='False';cfg['Core']['OverrideRegionSettings']='True'
    for key in['WiiSDCard','WiiSDCardEnableFolderSync','WiiSDCardAllowWrites']:cfg['Core'][key]='False'
    with path.open('w',encoding='utf-8')as f:cfg.write(f)
    lib=load_library();title=lib.title.Title();title.load_wad(wad.read_bytes());lib.nand.EmuNAND(BASE/'user/Wii').install_title(title)
    if not(BASE/'user/Wii/title/00000001/0000003a/content/title.tmd').is_file():raise ValueError('Profile lacks IOS58 required by the SPD TMD')
    register();launcher.scrub_download_tasks(PROFILE);launcher.validate(PROFILE)
    local=BASE/'local-feed';local.mkdir()
    for name in['routes.tsv','fictional-pd-plain.bin','fixture-manifest.json']:shutil.copy2(FEED/name,local/name)
    feed_manifest(local)
    runner,server=helper_sources();HELPER.mkdir(parents=True)
    (HELPER/'PersonalDataRunner.cs').write_text(runner,encoding='utf-8');(HELPER/'PersonalDataServer.cs').write_text(server,encoding='utf-8')
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    for source in sorted(HELPER.glob('*.cs')):subprocess.run([str(compiler),'/nologo','/target:exe','/platform:x64','/out:'+str(source.with_suffix('.exe')),str(source)],check=True,capture_output=True)
    locked=[BASE/'Dolphin-x64/Dolphin.exe',BASE/'NetProbe.exe',*(p for p in sorted(HELPER.iterdir())if p.suffix in('.cs','.exe')),local/'fixture-manifest.json']
    LOCK.write_text(json.dumps(dict(profile=PROFILE,title_id=TITLE,capability_count=0,external_network_allowed=False,boot='--nand_title '+TITLE,
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256(p))for p in locked],builds={'1':meta['wad_sha256']},fictional_data_installed=False),indent=2)+'\n')
    (CHANNEL/'active-build.json').write_text(json.dumps(dict(revision=1,wad_sha256=meta['wad_sha256']),indent=2)+'\n')
    if snapshot(TEMPLATE)!=before:raise ValueError('Personal-data template profile changed')
    print('Installed Korean Set Personal Data build-v1 in separate sanitized Korean profile; template preserved; capability-zero helper ready; no pd.dat (built-in template)')
if __name__=='__main__':main()

"""Read-only channel artifacts and entire GC v6 preservation verification."""
import configparser,json,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.channel_validation import verify_installed_title

def main():
    if 'dolphin.exe'in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin before preservation verification')
    channels=ROOT/'workspace/channels/forecast';before=json.loads((PRIVATE/'gc-v6-before-channels-manifest.json').read_text());gc=ROOT/'workspace/sandbox/gc-v6'
    old={r['path']:r for r in before};current={p.relative_to(gc).as_posix():p for p in gc.rglob('*')if p.is_file()};missing=sorted(old.keys()-current.keys());added=sorted(current.keys()-old.keys());changed=[]
    for name in old.keys()&current.keys():
        p=current[name];st=p.stat();r=old[name]
        if st.st_size!=r['size']or st.st_mtime_ns!=r['mtime_ns']or sha256(p)!=r['sha256']:changed.append(name)
    preservation=dict(files_before=len(old),files_after=len(current),missing=missing,added=added,changed=sorted(changed))
    (PRIVATE/'gc-v6-channel-preservation-result.json').write_text(json.dumps(preservation,indent=2))
    if missing or added or changed:raise SystemExit('GC v6 preservation differs; private comparison saved; original not repaired')
    acquisition=json.loads((channels/'originals/acquisition.json').read_text())
    for row in acquisition['files']:
        p=channels/'originals'/row['alias'];st=p.stat()
        if (st.st_size,st.st_mtime_ns,sha256(p))!=(row['size'],row['mtime_ns'],row['sha256']):raise ValueError('Original channel source differs')
    source_lock=json.loads((ROOT/'configs/channel-tools.lock.json').read_text())
    for row in source_lock['files']:
        if sha256(ROOT/row['path'])!=row['sha256']:raise ValueError('Pinned channel tool differs')
    references=json.loads((ROOT/'configs/forecast-server-references.lock.json').read_text())
    for row in references['files']:
        if sha256(ROOT/'external/channel-tools/ForecastChannel-reference'/row['path'])!=row['sha256']:raise ValueError('Forecast public reference differs')
    runtime_refs=json.loads((ROOT/'configs/channel-runtime-references.lock.json').read_text())
    for row in runtime_refs['files']:
        if sha256(ROOT/'external/channel-tools/dolphin-reference'/row['local'])!=row['sha256']:raise ValueError('Channel Dolphin reference differs')
    active=json.loads((channels/'active-build.json').read_text())['revision'];build=channels/f'build-v{active}';meta=json.loads((build/'build-manifest.json').read_text(encoding='utf-8'));wad=build/'forecast-ko-personal-test.wad'
    if sha256(wad)!=meta['wad_sha256']:raise ValueError('Channel WAD differs')
    title=load_library().title.Title();title.load_wad(wad.read_bytes())
    for index in range(12):title.get_content_by_index(index)
    count=verify_installed_title(ROOT/'workspace/sandbox/forecast-v1/user/Wii','0001000248414645',title.tmd.dump())
    patches=channels/f'patches/v{active}';patch=json.loads((patches/'manifest.json').read_text())
    if patch['output_sha256']!=meta['wad_sha256']or not patch['byte_identical_WAD_rebuild_verified']:raise ValueError('Private channel patch manifest differs')
    for row in patch['contents']:
        if sha256(patches/row['file'])!=row['patch_sha256']:raise ValueError('Private channel delta differs')
    cfg=configparser.ConfigParser(strict=False);cfg.read(ROOT/'workspace/sandbox/forecast-v1/user/Config/Dolphin.ini',encoding='utf-8-sig')
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    if any(p.startswith(('workspace/','sd/','external/','tools/','.venv/'))for p in tracked):raise ValueError('Excluded material tracked')
    result=dict(passed=True,active_revision=active,installed_contents_verified=count,original_WADs_preserved=len(acquisition['files']),pinned_channel_files=len(source_lock['files']),pinned_server_references=len(references['files']),pinned_Dolphin_references=len(runtime_refs['files']),GC_v6_whole_profile_preserved=True,GC_v6_files=len(before),private_patch_byte_identical=True,custom_RTC_enabled=cfg['Core'].getboolean('EnableCustomRTC',fallback=False),real_console_touched=False,emulator_network_success_verified=False)
    (PRIVATE/'channel-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

if __name__=='__main__':main()

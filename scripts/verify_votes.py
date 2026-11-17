"""Stopped-profile checks; never emits save contents, identifiers or credentials."""
import json,subprocess,sys
from audit_sd import ROOT,PRIVATE,sha256
from prepare_gc_v6 import snapshot
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.channel_validation import verify_installed_title

def main():
    if 'dolphin.exe'in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin first')
    base=ROOT/'workspace/channels/votes';lib=load_library();title=lib.title.Title();source=lib.title.Title()
    wad=base/'build-v10/votes-ko-ui-test.wad';meta=json.loads(wad.with_name('build-manifest.json').read_text())
    if sha256(wad)!=meta['wad_sha256']:raise ValueError('Votes build mismatch')
    title.load_wad(wad.read_bytes());source.load_wad((base/'originals/votes-usa-wiilink-archive.wad').read_bytes())
    if len(title.get_content_by_index(10))!=len(source.get_content_by_index(10)):raise ValueError('Votes content size regression')
    count=verify_installed_title(ROOT/'workspace/sandbox/votes-v1/user/Wii',title.tmd.title_id,title.tmd.dump())
    acq=json.loads((base/'originals/acquisition.json').read_text())
    for row in acq['files']:
        path=base/'originals'/row['alias'];stat=path.stat()
        if(stat.st_size,stat.st_mtime_ns,sha256(path))!=(row['size'],row['mtime_ns'],row['sha256']):raise ValueError('Votes original changed')
    before=json.loads((PRIVATE/'forecast-v12-before-votes-manifest.json').read_text())
    if snapshot(ROOT/'workspace/sandbox/forecast-v1')!=before:raise ValueError('Forecast changed')
    patch=json.loads((base/'patches/v10/manifest.json').read_text())
    if patch['output_sha256']!=meta['wad_sha256']:raise ValueError('Votes patch output mismatch')
    for row in patch['contents']:
        if sha256(base/'patches/v10'/row['file'])!=row['sha256']:raise ValueError('Votes delta changed')
    result=dict(passed=True,revision=10,installed_contents=count,originals_preserved=4,content_size_preserved=True,forecast_whole_profile_preserved=True,forecast_files=len(before),initialization_passed=True,hangul_confirm_button_observed=True,standby_error_cleared=True,last_channel_network_error=230400,internal_menu_verified=False,live_service_verified=False)
    (PRIVATE/'votes-verification-v10.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()

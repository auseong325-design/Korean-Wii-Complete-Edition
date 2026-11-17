"""Read-only stopped Mii Contest alpha checks; metadata-only stdout."""
import json,subprocess,sys
from audit_sd import ROOT,PRIVATE,sha256
from prepare_gc_v6 import snapshot
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.channel_validation import verify_installed_title

def main():
    if 'dolphin.exe'in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin first')
    base=ROOT/'workspace/channels/mii-contest';wad=base/'build-v7/mii-contest-ko-ui-test.wad';meta=json.loads(wad.with_name('build-manifest.json').read_text())
    if sha256(wad)!=meta['wad_sha256']:raise ValueError('Mii Contest WAD differs')
    lib=load_library();title=lib.title.Title();title.load_wad(wad.read_bytes());count=verify_installed_title(ROOT/'workspace/sandbox/mii-contest-v1/user/Wii',title.tmd.title_id,title.tmd.dump())
    acq=json.loads((base/'originals/acquisition.json').read_text())
    for row in acq['files']:
        path=base/'originals'/row['alias'];stat=path.stat()
        if(stat.st_size,stat.st_mtime_ns,sha256(path))!=(row['size'],row['mtime_ns'],row['sha256']):raise ValueError('Source original changed')
    before=json.loads((PRIVATE/'forecast-before-mii-contest-v4-manifest.json').read_text())
    if snapshot(ROOT/'workspace/sandbox/forecast-v1')!=before:raise ValueError('Forecast profile changed')
    result=dict(passed=True,revision=7,installed_contents=count,originals_preserved=len(acq['files']),forecast_whole_profile_preserved=True,forecast_files=len(before),full_localization_complete=False,review_complete=False,live_service_verified=False)
    (PRIVATE/'mii-contest-verification-v7.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()

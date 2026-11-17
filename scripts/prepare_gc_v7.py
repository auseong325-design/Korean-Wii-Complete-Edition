"""Preserve v6 in full; clone it to v7 with the animated DVD disc model (resource only)."""
import hashlib,json,shutil,struct,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
sys.path.insert(0,str(ROOT))
from kwce.disk_dvd_anim import patch_dvd_animation
from launch_dolphin import scrub_download_tasks,validate,validate_native_runtime

def snapshot(folder):
    return [dict(path=p.relative_to(folder).as_posix(),size=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns,sha256=sha256(p))for p in sorted(folder.rglob('*'))if p.is_file()]

def main():
    if 'dolphin.exe' in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin before cloning profiles')
    parent=ROOT/'workspace/sandbox/gc-v6';target=ROOT/'workspace/sandbox/gc-v7';out=ROOT/'workspace/experiments/gc-native-v7'
    if target.exists() or out.exists():raise SystemExit('Existing v7 preserved')
    validate_native_runtime('gc-native-v6-user')
    before=snapshot(parent);(PRIVATE/'gc-v6-before-v7-manifest.json').write_text(json.dumps(before,indent=2))
    for folder in ['user','Dolphin-x64','disc']:
        shutil.copytree(parent/folder,target/folder,ignore=shutil.ignore_patterns('Logs','ScreenShots','Cache','StateSaves'))
    shutil.copy2(parent/'NetProbe.exe',target/'NetProbe.exe')
    cfg=target/'user/Config/Dolphin.ini';text=cfg.read_text(encoding='utf-8-sig')
    cfg.write_text(text.replace(str(parent),str(target)),encoding='utf-8')
    content=target/'user/Wii/title/00000001/00000002/content';tmd=bytearray((content/'title.tmd').read_bytes())
    for i in range(int.from_bytes(tmd[0x1de:0x1e0],'big')):
        at=0x1e4+36*i;cid,index=struct.unpack_from('>IH',tmd,at)
        if index==1:
            path=content/f'{cid:08x}.app';resource,record=patch_dvd_animation(path.read_bytes())
            path.write_bytes(resource);struct.pack_into('>Q',tmd,at+8,len(resource));tmd[at+16:at+36]=hashlib.sha1(resource).digest();break
    else:raise ValueError('Resource content missing')
    (content/'title.tmd').write_bytes(tmd)
    scrub_download_tasks('gc-native-v7-user');validate('gc-native-v7-user')  # runtime check after prepare_gc_sandbox --revision 7
    out.mkdir(parents=True);(out/'menu-resource.app').write_bytes(resource)
    (out/'build-manifest.json').write_text(json.dumps(dict(parent='gc-native-v6-user',resource_sha256=hashlib.sha256(resource).hexdigest(),dvd_animation=record,TMD_signature_valid=False),ensure_ascii=False,indent=2),encoding='utf-8')
    if snapshot(parent)!=before:raise ValueError('Preserved v6 changed during clone')
    print(json.dumps(dict(built=True,resource_bytes=len(resource),parent_files_preserved=len(before),**{k:record[k] for k in ('loop_tags_disabled','disk_in_tracks_held')})))

if __name__=='__main__':main()

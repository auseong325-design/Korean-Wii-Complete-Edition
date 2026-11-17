"""Preserve v5 in full; build header fix and FST-guard experiment separately."""
import configparser,hashlib,json,shutil,struct,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
sys.path.insert(0,str(ROOT))
from kwce.gc_header import patch_gc_header
from kwce.dolphin_fst import inspect_fst
from launch_dolphin import scrub_download_tasks,validate,validate_native_runtime

def snapshot(folder):
    return [dict(path=p.relative_to(folder).as_posix(),size=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns,sha256=sha256(p))for p in sorted(folder.rglob('*'))if p.is_file()]

def main():
    if 'dolphin.exe' in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin before cloning profiles')
    parent=ROOT/'workspace/sandbox/gc-v5';target=ROOT/'workspace/sandbox/gc-v6';out=ROOT/'workspace/experiments/gc-native-v6'
    if (target/'user').exists() or out.exists():raise SystemExit('Existing v6 preserved')
    validate_native_runtime('gc-native-v5-user')
    before=snapshot(parent);(PRIVATE/'gc-v5-before-v6-manifest.json').write_text(json.dumps(before,indent=2))
    for folder in ['user','Dolphin-x64','disc']:
        shutil.copytree(parent/folder,target/folder,ignore=shutil.ignore_patterns('Logs','ScreenShots','Cache','StateSaves'))
    from kwce.dolphin_fst_retry import patch_fst_retry
    exe=target/'Dolphin-x64/Dolphin.exe';modified,retry=patch_fst_retry(exe.read_bytes())
    if retry!=json.loads((ROOT/'configs/gc-fst-runtime.lock.json').read_text()):raise ValueError('FST runtime lock mismatch')
    exe.write_bytes(modified)
    shutil.copy2(parent/'NetProbe.exe',target/'NetProbe.exe')
    cfg=target/'user/Config/Dolphin.ini';c=configparser.ConfigParser(strict=False);c.optionxform=str;c.read(cfg,encoding='utf-8-sig')
    for section in c.sections():
        for key,value in list(c[section].items()):c[section][key]=value.replace(str(parent),str(target))
    with cfg.open('w',encoding='utf-8')as f:c.write(f)
    content=target/'user/Wii/title/00000001/00000002/content';tmd=bytearray((content/'title.tmd').read_bytes())
    for i in range(int.from_bytes(tmd[0x1de:0x1e0],'big')):
        at=0x1e4+36*i;cid,index=struct.unpack_from('>IH',tmd,at)
        if index==1:
            resource,record=patch_gc_header((content/f'{cid:08x}.app').read_bytes())
            (content/f'{cid:08x}.app').write_bytes(resource);struct.pack_into('>Q',tmd,at+8,len(resource));tmd[at+16:at+36]=hashlib.sha1(resource).digest();break
    else:raise ValueError('Resource content missing')
    (content/'title.tmd').write_bytes(tmd)
    scrub_download_tasks('gc-native-v6-user');validate('gc-native-v6-user')
    fst=inspect_fst((target/'user/Wii/fst.bin').read_bytes())
    out.mkdir(parents=True);(out/'menu-resource.app').write_bytes(resource)
    dol=(ROOT/'workspace/experiments/gc-native-v5/menu-gc-native.dol').read_bytes()
    (out/'menu-gc-native.dol').write_bytes(dol)
    (out/'build-manifest.json').write_text(json.dumps(dict(parent='gc-native-v5-user',patched_dol_sha256=hashlib.sha256(dol).hexdigest(),header=record,fst_before=fst,fst_runtime=retry,TMD_signature_valid=False),ensure_ascii=False,indent=2),encoding='utf-8')
    if snapshot(parent)!=before:raise ValueError('Preserved v5 changed during clone')
    print(json.dumps(dict(built=True,header_bytes_changed=1,parent_files_preserved=len(before),FST_valid=True)))

if __name__=='__main__':main()

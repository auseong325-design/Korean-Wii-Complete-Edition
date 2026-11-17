"""Preserve v4; create a separate offline native GC integration profile."""
import configparser,json,shutil,subprocess,sys,struct,hashlib
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
sys.path.insert(0,str(ROOT))
from launch_dolphin import scrub_download_tasks,validate
from kwce.gc_fixture import raw_card

def main():
    if 'dolphin.exe' in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin')
    runtime=ROOT/'workspace/sandbox/gc-v5'
    if (runtime/'user').exists() or (runtime/'Dolphin-x64').exists() or (ROOT/'workspace/experiments/gc-native-v5').exists():raise SystemExit('Existing v5 preserved')
    validate('gc-native-v4-user')
    runtime.mkdir(parents=True,exist_ok=True)
    for folder in ['user','Dolphin-x64']:shutil.copytree(ROOT/'workspace/sandbox/gc-v4'/folder,runtime/folder)
    from kwce.gc_native import patch_gc_native
    original=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    dol,menu_patch=patch_gc_native(original,japanese_cards=True,japanese_comments=True)
    content=runtime/'user/Wii/title/00000001/00000002/content'
    tmd=bytearray((content/'title.tmd').read_bytes())
    for i in range(int.from_bytes(tmd[0x1de:0x1e0],'big')):
        at=0x1e4+36*i;cid,index=struct.unpack_from('>IH',tmd,at)
        if index==6:
            (content/f'{cid:08x}.app').write_bytes(dol)
            struct.pack_into('>Q',tmd,at+8,len(dol));tmd[at+16:at+36]=hashlib.sha1(dol).digest();break
    else:raise ValueError('Menu DOL content missing')
    (content/'title.tmd').write_bytes(tmd)
    out=ROOT/'workspace/experiments/gc-native-v5';out.mkdir(exist_ok=False)
    (out/'menu-gc-native.dol').write_bytes(dol)
    (out/'build-manifest.json').write_text(json.dumps(dict(patched_dol_sha256=hashlib.sha256(dol).hexdigest(),patch=menu_patch,TMD_signature_valid=False),indent=2))
    from kwce.dolphin_gc_fix import patch_mios_ipc
    exe=runtime/'Dolphin-x64/Dolphin.exe';modified,fix=patch_mios_ipc(exe.read_bytes());exe.write_bytes(modified)
    if json.loads((ROOT/'configs/gc-runtime.lock.json').read_text())!=fix:raise SystemExit('Runtime derivative lock mismatch')
    cfg=runtime/'user/Config/Dolphin.ini';c=configparser.ConfigParser(strict=False);c.optionxform=str;c.read(cfg,encoding='utf-8')
    old=str(ROOT/'workspace/sandbox/gc-v4');new=str(runtime)
    for section in c.sections():
        for key,value in list(c[section].items()):c[section][key]=value.replace(old,new)
    c['Core']['CPUThread']='False'
    c['Core']['CPUCore']='1'
    # Existing MIOS loader clears old Wii HLE hooks only after loading a map.
    # An empty local map triggers that cleanup without importing any symbols.
    maps=runtime/'user/Maps';maps.mkdir(exist_ok=True)
    (maps/'mios-ipl.map').write_text('',encoding='ascii')
    for slot in ['A','B']:
        card=runtime/f'user/GC/native-card-{slot}.JAP.raw';card.write_bytes(raw_card(slot=='A',encoding=1,mbits=128));c['Core'][f'Memcard{slot}Path']=str(card)
    catalog=json.loads((PRIVATE/'disc-catalog.json').read_text());row=next(r for r in catalog['files'] if r['name']=='GALJ01.iso')
    iso=runtime/'disc/GALJ01.iso';iso.parent.mkdir(exist_ok=True)
    with Path(row['path']).open('rb') as src,iso.open('xb') as dst:shutil.copyfileobj(src,dst,8*1024*1024)
    if sha256(iso)!=row['sha256']:raise SystemExit('Disc verification failed')
    c['Core']['DefaultISO']=str(iso)
    with cfg.open('w',encoding='utf-8') as f:c.write(f)
    # Extra device logs stay local and are never emitted verbatim.
    log=runtime/'user/Config/Logger.ini';lc=configparser.ConfigParser(strict=False);lc.optionxform=str;lc.read(log,encoding='utf-8')
    for key in ['IOS_ES','DVD','DSP','DSPHLE','EXI','SI']:lc['Logs'][key]='True'
    with log.open('w',encoding='utf-8') as f:lc.write(f)
    scrub_download_tasks('gc-native-v5-user');validate('gc-native-v5-user')
    (PRIVATE/'gc-v5-preparation.json').write_text(json.dumps(dict(parent='gc-native-v4-user',disc_hash_verified=True,CPUThread=False,resources_unchanged=True,japanese_comment_converter=True),indent=2))
    print('PASS: separate v5 profile, staged disc verified, single CPU thread')

if __name__=='__main__':main()

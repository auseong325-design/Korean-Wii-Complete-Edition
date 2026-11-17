"""Preserve v7 in full; clone it to v8 = v7 + disc channel DVD hook + DVD player channel.

Menu content 6 gets kwce.dvd_disc_hook on top of the GC native DOL; the DVD player
WAD (workspace/channels/dvd-player/wad-vN) is installed into the test NAND with
libWiiPy; synthetic test discs (workspace/test-media/wii, hashed JSON beside each)
are staged in disc/ next to the catalogued GC disc.
"""
import argparse,hashlib,json,shutil,struct,subprocess,sys
from audit_sd import ROOT,PRIVATE,sha256
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.dvd_disc_hook import patch_dvd_hook
from launch_dolphin import scrub_download_tasks,validate,validate_native_runtime

def snapshot(folder):
    return [dict(path=p.relative_to(folder).as_posix(),size=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns,sha256=sha256(p))for p in sorted(folder.rglob('*'))if p.is_file()]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--wad',type=int,required=True);args=ap.parse_args()
    if 'dolphin.exe' in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin before cloning profiles')
    parent=ROOT/'workspace/sandbox/gc-v7';target=ROOT/'workspace/sandbox/gc-v8';out=ROOT/'workspace/experiments/gc-native-v8'
    if target.exists() or out.exists():raise SystemExit('Existing v8 preserved')
    validate_native_runtime('gc-native-v7-user')
    before=snapshot(parent);(PRIVATE/'gc-v7-before-v8-manifest.json').write_text(json.dumps(before,indent=2))
    for folder in ['user','Dolphin-x64','disc']:
        shutil.copytree(parent/folder,target/folder,ignore=shutil.ignore_patterns('Logs','ScreenShots','Cache','StateSaves'))
    shutil.copy2(parent/'NetProbe.exe',target/'NetProbe.exe')
    cfg=target/'user/Config/Dolphin.ini';cfg.write_text(cfg.read_text(encoding='utf-8-sig').replace(str(parent),str(target)),encoding='utf-8')
    content=target/'user/Wii/title/00000001/00000002/content';tmd=bytearray((content/'title.tmd').read_bytes())
    for i in range(int.from_bytes(tmd[0x1de:0x1e0],'big')):
        at=0x1e4+36*i;cid,index=struct.unpack_from('>IH',tmd,at)
        if index==6:
            path=content/f'{cid:08x}.app';menu,hook=patch_dvd_hook(path.read_bytes())
            path.write_bytes(menu);struct.pack_into('>Q',tmd,at+8,len(menu));tmd[at+16:at+36]=hashlib.sha1(menu).digest();break
    else:raise ValueError('Menu DOL content missing')
    (content/'title.tmd').write_bytes(tmd)
    wad=ROOT/f'workspace/channels/dvd-player/wad-v{args.wad}/dvd-player.wad'
    lib=load_library();title=lib.title.Title();title.load_wad(wad.read_bytes())
    lib.nand.EmuNAND(target/'user/Wii').install_title(title)
    staged=[]
    for meta_path in sorted((ROOT/'workspace/test-media/wii').glob('*.json')):
        meta=json.loads(meta_path.read_text(encoding='utf-8'));iso=meta_path.with_suffix('.iso')
        if not meta.get('synthetic') or sha256(iso)!=meta['sha256']:raise SystemExit('Unverified test disc')
        shutil.copy2(iso,target/'disc'/iso.name);shutil.copy2(meta_path,target/'disc'/meta_path.name);staged.append(iso.name)
    scrub_download_tasks('gc-native-v8-user');validate('gc-native-v8-user')  # runtime check after the v8 helper build
    out.mkdir(parents=True);(out/'menu-dvd-hook.dol').write_bytes(menu)
    (out/'build-manifest.json').write_text(json.dumps(dict(parent='gc-native-v7-user',menu_sha256=hashlib.sha256(menu).hexdigest(),dvd_hook=hook,
        dvd_player_wad=wad.relative_to(ROOT).as_posix(),dvd_player_wad_sha256=sha256(wad),synthetic_discs=staged,TMD_signature_valid=False),ensure_ascii=False,indent=2),encoding='utf-8')
    if snapshot(parent)!=before:raise ValueError('Preserved v7 changed during clone')
    print(json.dumps(dict(built=True,menu_bytes=len(menu),wad=args.wad,discs=staged,parent_files_preserved=len(before))))

if __name__=='__main__':main()

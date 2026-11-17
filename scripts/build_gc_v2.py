"""Build separate native-GC experiment with two synthetic GCI card folders."""
from pathlib import Path
import json,struct,hashlib,shutil,subprocess,sys,configparser,argparse
from audit_sd import ROOT,PRIVATE,sha256
sys.path.insert(0,str(ROOT))
from kwce.gc_native import patch_gc_native

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,choices=[2,3,4],default=4);args=ap.parse_args();rev=args.revision
    p=subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True)
    if 'dolphin.exe' in p.stdout.lower():raise SystemExit('Close Dolphin')
    runtime=ROOT/f'workspace/sandbox/gc-v{rev}';user=runtime/'user';out=ROOT/f'workspace/experiments/gc-native-v{rev}'
    if user.exists() or out.exists():raise SystemExit('Output exists; no overwrite')
    from launch_dolphin import validate,scrub_download_tasks,user_path
    source=user_path('gc-visual-v1-user')
    original=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes();patched,detail=patch_gc_native(original,japanese_cards=rev>=3)
    shutil.copytree(source,user)
    scrub_download_tasks(f'gc-native-v{rev}-user');validate(f'gc-native-v{rev}-user')
    out.mkdir(parents=True)
    (out/'menu-gc-native.dol').write_bytes(patched)
    content=user/'Wii/title/00000001/00000002/content';tmd=bytearray((content/'title.tmd').read_bytes());base=0x140
    boot=struct.unpack_from('>H',tmd,base+0xa0)[0];count=struct.unpack_from('>H',tmd,base+0x9e)[0]
    for i in range(count):
        at=base+0xa4+i*36;cid,index=struct.unpack_from('>IH',tmd,at)
        if index==boot:
            boot_name=f'{cid:08x}.app';(content/boot_name).write_bytes(patched);struct.pack_into('>Q',tmd,at+8,len(patched));tmd[at+16:at+36]=hashlib.sha1(patched).digest();break
    else:raise ValueError('No boot content')
    icons=None
    if rev>=4:
        from kwce.gc_icons import patch_gc_icons
        for i in range(count):
            at=base+0xa4+i*36;cid,index=struct.unpack_from('>IH',tmd,at)
            if index==1:
                resource_name=f'{cid:08x}.app';modified,icons=patch_gc_icons((content/resource_name).read_bytes())
                (out/'menu-resource.app').write_bytes(modified);(content/resource_name).write_bytes(modified)
                struct.pack_into('>Q',tmd,at+8,len(modified));tmd[at+16:at+36]=hashlib.sha1(modified).digest();break
        else:raise ValueError('No resource content')
    (content/'title.tmd').write_bytes(tmd)
    program=runtime/'Dolphin-x64'
    if not program.exists():shutil.copytree(ROOT/'tools/dolphin-2609a/Dolphin-x64',program)
    cfg=user/'Config/Dolphin.ini';s=cfg.read_text(encoding='utf-8')
    c=configparser.ConfigParser(strict=False);c.optionxform=str;c.read_string(s)
    for section in ['Core','General']: 
        if not c.has_section(section):c.add_section(section)
    c['Core']['SerialPort1']='255';c['Core']['SerialPort2']='255'
    if not c.has_section('Input'):c.add_section('Input')
    c['Input']['BackgroundInput']='True'
    if rev>=3:
        from kwce.gc_fixture import raw_card
        for slot in ['A','B']:
            c['Core'][f'Slot{slot}']='1'
            card=user/f'GC/native-card-{slot}.JAP.raw';card.parent.mkdir(parents=True,exist_ok=True)
            with card.open('xb') as f:f.write(raw_card(slot=='A',encoding=1,mbits=128))
            c['Core'][f'Memcard{slot}Path']=str(card)
    else:
        c['Core']['SlotA']='8';c['Core']['SlotB']='8'
        c['Core']['GCIFolderAPath']=str(user/'GC/Card A');c['Core']['GCIFolderBPath']=str(user/'GC/Card B')
    with cfg.open('w',encoding='utf-8') as f:c.write(f)
    for name in ['Card A','Card B']:(user/'GC'/name).mkdir(parents=True,exist_ok=True)
    manifest=dict(profile=f'gc-native-v{rev}-user',runtime=str(runtime.relative_to(ROOT)),original_menu_sha1=hashlib.sha1(original).hexdigest(),patched_dol_sha256=hashlib.sha256(patched).hexdigest(),patch=detail,boot_content=boot_name,TMD_signature_valid=False,real_console_writes=False,japanese_test_cards=rev>=3,settings_icons=icons)
    (out/'build-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(dict(built=True,instructions_changed=detail['instructions_changed'],originals_preserved=True,OS_sandbox_required=True)))

if __name__=='__main__':main()

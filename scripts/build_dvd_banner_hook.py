"""Build/install a numbered native DVD banner memory hook in the project NAND only."""
import argparse,hashlib,json,shutil,struct,sys
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
sys.path.insert(0,str(ROOT))
from kwce.gc_native import patch_gc_native
from kwce.dvd_disc_hook import patch_dvd_hook
from kwce.dvd_disc_banner_hook import patch_dvd_banner_hook

def main():
    p=argparse.ArgumentParser();p.add_argument('--revision',type=int,required=True);p.add_argument('--install',action='store_true');p.add_argument('--hide-tile',action='store_true');p.add_argument('--hide-version',type=int,choices=(1,2),default=1);a=p.parse_args()
    if a.install:stopped()
    out=ROOT/f'workspace/experiments/dvd-menu-hook-v{a.revision}'
    if a.revision<2 or out.exists():raise ValueError('Numbered DVD menu hook preserved')
    original=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    gc=patch_gc_native(original,japanese_cards=True,japanese_comments=True)[0]
    if a.hide_tile:
        if a.hide_version==2:
            from kwce.dvd_hide_tile_v2 import patch as selected_patch
        else:
            from kwce.dvd_hide_tile_v1 import patch as selected_patch
    else:
        selected_patch=patch_dvd_banner_hook
    data,record=selected_patch(gc);again,_=selected_patch(gc)
    if data!=again:raise ValueError('Native DVD banner hook is not deterministic')
    out.mkdir();(out/'menu.dol').write_bytes(data)
    record.update(revision=a.revision,sha256=hashlib.sha256(data).hexdigest(),source_sha256=sha256(ROOT/'kwce/dvd_disc_banner_hook.py'))
    (out/'build-manifest.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    if a.install:
        rt=ROOT/'workspace/sandbox/dvd-test-v2';manifest=rt/'test-bed-manifest.json';m=json.loads(manifest.read_text())
        folder=rt/'user/Wii/title/00000001/00000002/content';tmd=bytearray((folder/'title.tmd').read_bytes())
        before=PRIVATE/f'dvd-menu-hook-before-v{a.revision}';before.mkdir();shutil.copy2(manifest,before/manifest.name);shutil.copy2(folder/'title.tmd',before/'title.tmd')
        for i in range(int.from_bytes(tmd[0x1de:0x1e0],'big')):
            at=0x1e4+36*i;cid,index=struct.unpack_from('>IH',tmd,at)
            if index==6:
                target=folder/f'{cid:08x}.app'
                prior=m.get('dvd_banner_hook')
                expected=ROOT/f'workspace/experiments/dvd-menu-hook-v{prior["revision"]}/menu.dol'if prior else None
                previous=expected.read_bytes()if expected else patch_dvd_hook(gc)[0]
                if target.read_bytes()!=previous:raise ValueError('Test menu differs from its preserved hook/GC base')
                shutil.copy2(target,before/'menu.dol');target.write_bytes(data)
                struct.pack_into('>Q',tmd,at+8,len(data));tmd[at+16:at+36]=hashlib.sha1(data).digest();break
        else:raise ValueError('Test menu executable content missing')
        (folder/'title.tmd').write_bytes(tmd);m['system_menu_contents']['6']=record['sha256'];m['dvd_banner_hook']=record
        manifest.write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    print(f'PASS: native DVD banner hook v{a.revision}, {record["cave_bytes"]} launch + {record.get("native_code_bytes",0)} native bytes; '+('test NAND selected'if a.install else'not installed'))

if __name__=='__main__':main()

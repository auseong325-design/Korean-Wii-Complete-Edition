"""Build a numbered emulator-only DVD banner preview and select it when stopped."""
import argparse,hashlib,json,struct,sys,shutil
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
sys.path.insert(0,str(ROOT))
from kwce.dvd_menu_preview import patch_preview

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True);ap.add_argument('--install',action='store_true');ap.add_argument('--native',action='store_true',help='select unchanged gc-v6 resources; native memory hook supplies DVD visuals');args=ap.parse_args()
    if args.install:stopped()
    out=ROOT/f'workspace/experiments/dvd-menu-preview-v{args.revision}'
    if out.exists():raise SystemExit('Numbered DVD preview preserved')
    original=ROOT/'workspace/experiments/gc-native-v7/menu-resource.app'
    if args.revision==1:
        from kwce.dvd_menu_preview_v1 import patch_preview as apply
    elif args.revision==2:
        from kwce.dvd_menu_preview_v2 import patch_preview as apply
    elif args.revision==3:
        from kwce.dvd_menu_preview_v3 import patch_preview as apply
    elif args.revision==4:
        from kwce.dvd_menu_preview_v4 import patch_preview as apply
    else:apply=patch_preview
    if args.native:
        if args.revision<6:raise ValueError('Preserved preview revisions cannot change mode')
        original=ROOT/'workspace/experiments/gc-native-v6/menu-resource.app'
        data=again=original.read_bytes();record=dict(native_resources=True,emulator_only=False,hardware_detection=False,memory_hook_required=10,source='unchanged restored gc-v6 menu resources; no emulator visual preview')
    else:data,record=apply(original.read_bytes());again,_=apply(original.read_bytes())
    if data!=again:raise ValueError('DVD preview not deterministic')
    out.mkdir();(out/'menu-resource.app').write_bytes(data)
    record.update(revision=args.revision,sha256=hashlib.sha256(data).hexdigest(),source_sha256=sha256(original))
    (out/'build-manifest.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    if args.install:
        rt=ROOT/'workspace/sandbox/dvd-test-v2';manifest=rt/'test-bed-manifest.json';m=json.loads(manifest.read_text(encoding='utf-8'))
        before=PRIVATE/f'dvd-menu-preview-before-v{args.revision}';before.mkdir();shutil.copy2(manifest,before/manifest.name)
        folder=rt/'user/Wii/title/00000001/00000002/content';tmd=bytearray((folder/'title.tmd').read_bytes());shutil.copy2(folder/'title.tmd',before/'title.tmd')
        for i in range(int.from_bytes(tmd[0x1de:0x1e0],'big')):
            at=0x1e4+36*i;cid,index=struct.unpack_from('>IH',tmd,at)
            if index==1:
                p=folder/f'{cid:08x}.app'
                if sha256(p)!=m['system_menu_contents']['1']:raise ValueError('Selected menu resource differs from manifest')
                shutil.copy2(p,before/'menu-resource.app');p.write_bytes(data)
                struct.pack_into('>Q',tmd,at+8,len(data));tmd[at+16:at+36]=hashlib.sha1(data).digest();break
        else:raise ValueError('Menu resource content missing')
        (folder/'title.tmd').write_bytes(tmd);m['system_menu_contents']['1']=record['sha256'];m['preview']=record;manifest.write_text(json.dumps(m,indent=2),encoding='utf-8')
    print('PASS: numbered DVD menu preview v'+str(args.revision)+('; installed in test NAND only'if args.install else''))

if __name__=='__main__':main()

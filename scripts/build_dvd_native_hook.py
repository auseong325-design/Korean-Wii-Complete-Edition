"""Build a new experimental native DVD hook, optionally install in v3 only."""
import argparse
import hashlib
import json
import shutil
import struct
import sys
from audit_sd import ROOT,sha256
from prepare_channel_access import stopped
sys.path.insert(0,str(ROOT))
from kwce.dvd_native_hook import patch,SOURCE
from kwce.gc_native import patch_gc_native


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True);ap.add_argument('--player',type=int,default=33);ap.add_argument('--module',type=int,default=3);ap.add_argument('--banner',type=int,default=2);ap.add_argument('--source-revision',type=int,choices=[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33],default=1);ap.add_argument('--install',action='store_true');ap.add_argument('--stock-thumbnail',action='store_true');a=ap.parse_args()
    if a.stock_thumbnail and (a.source_revision!=30 or a.install):raise SystemExit('Stock-thumbnail control requires source30 and a separate non-installed build')
    if a.source_revision in (12,14,16,19,20,22,23,32) and a.install:raise SystemExit('Diagnostic drive simulation must never be installed')
    if a.source_revision==33 and a.install:raise SystemExit('Local-only SD ownership review must not be installed')
    if a.install:stopped()
    out=ROOT/f'workspace/experiments/dvd-native-hook-v{a.revision}'
    if out.exists():raise SystemExit('Existing numbered native hook preserved')
    base=patch_gc_native((ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes(),japanese_cards=True,japanese_comments=True)[0]
    player=(ROOT/f'workspace/channels/dvd-player/build-v{a.player}/boot.dol').read_bytes()
    module=(ROOT/f'workspace/experiments/dvd-native-module-v{a.module}/player.ash').read_bytes()
    banner=(ROOT/f'workspace/experiments/dvd-native-banner-v{a.banner}/menu.arc').read_bytes()
    source=ROOT/f'homebrew/kwce-disc-menu/native-v{a.source_revision}'
    data,record=patch(base,player,module,banner,source=source,thumbnail=not a.stock_thumbnail)
    if a.stock_thumbnail:record['thumbnail_hook']=False
    if a.source_revision in (31,32,33):record['icon_cache_store']=True
    if a.source_revision==32:record['thumbnail_read_control']=True
    if a.source_revision==33:record.update(sd_passive_reader=True,sd_attach_hook=False,local_only=True)
    record['banner_sha256']=hashlib.sha256(banner).hexdigest()
    if a.source_revision>=6:record['icon_sha256']=sha256(ROOT/'workspace/experiments/dvd-native-icon-v1/icon.arc')
    out.mkdir();shutil.copytree(source,out/'source')
    record.update(revision=a.revision,player_revision=a.player,module_revision=a.module,banner_revision=a.banner,sha256=hashlib.sha256(data).hexdigest(),
                  source_revision=a.source_revision,sources={p.name:sha256(p) for p in source.iterdir() if p.is_file()})
    (out/'menu.dol').write_bytes(data);(out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    if a.install:
        rt=ROOT/'workspace/sandbox/dvd-test-v3';p=rt/'test-bed-manifest.json';m=json.loads(p.read_text())
        content=rt/'user/Wii/title/00000001/00000002/content';tmd=bytearray((content/'title.tmd').read_bytes())
        for i in range(int.from_bytes(tmd[0x1de:0x1e0],'big')):
            at=0x1e4+36*i;cid,idx=struct.unpack_from('>IH',tmd,at)
            if idx==6:
                target=content/f'{cid:08x}.app'
                if sha256(target)!=m['system_menu_contents']['6']:raise ValueError('Installed native menu differs')
                target.write_bytes(data);struct.pack_into('>Q',tmd,at+8,len(data));tmd[at+16:at+36]=hashlib.sha1(data).digest();break
        else:raise ValueError('Menu DOL missing')
        (content/'title.tmd').write_bytes(tmd)
        m['native_hook'].update(revision=a.revision,sha256=record['sha256'],module_sha256=record['module_sha256'],player_sha256=record['player_sha256']);m['system_menu_contents']['6']=record['sha256'];p.write_text(json.dumps(m,indent=2)+'\n')
        (rt/'sd-sync/kwce/dvd/boot.ash').write_bytes(module)
        (rt/'sd-sync/kwce/dvd/menu.arc').write_bytes(banner)
        if a.source_revision>=6:
            icon=(ROOT/'workspace/experiments/dvd-native-icon-v1/icon.arc').read_bytes()
            if hashlib.sha256(icon).hexdigest()!=record['icon_sha256']:raise ValueError('Native icon differs')
            (rt/'sd-sync/kwce/dvd/icon.arc').write_bytes(icon)
            m['native_hook']['icon_sha256']=record['icon_sha256']
        m['native_hook']['banner_sha256']=record['banner_sha256'];p.write_text(json.dumps(m,indent=2)+'\n')
        (rt/'sd-sync/apps/kwce-dvd/boot.dol').write_bytes(player)
        (rt/'sd-sync/kwce/dvd/active-player.json').write_text(json.dumps(dict(revision=a.player,sha256=record['player_sha256'],css_decryption=False)))
        catalog=ROOT/'configs/channels.catalog.json';j=json.loads(catalog.read_text(encoding='utf-8'))
        bed=next(x for x in j['test_beds'] if x['profile']=='dvd-test-v3');bed['native_hook']=f'dvd-native-hook-v{a.revision}';bed['player_build']=f'build-v{a.player}'
        catalog.write_text(json.dumps(j,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print(f'PASS native v{a.revision}: loader {record["native_bytes"]}, banner {record["banner_bytes"]}; experimental')


if __name__=='__main__':main()

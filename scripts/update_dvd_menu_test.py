"""Select a new verified player/channel in the stopped integrated DVD test bed."""
import argparse,json,shutil,sys
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.channel_validation import verify_installed_title

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--wad',type=int,required=True);args=ap.parse_args();stopped()
    runtime=ROOT/'workspace/sandbox/dvd-test-v2';content=runtime/'sd-sync/kwce/dvd';manifest=runtime/'test-bed-manifest.json'
    record=json.loads(manifest.read_text(encoding='utf-8'));wad=ROOT/f'workspace/channels/dvd-player/wad-v{args.wad}/dvd-player.wad'
    selected=json.loads(wad.with_name('wad-manifest.json').read_text(encoding='utf-8'))
    if sha256(wad)!=selected['wad_sha256']:raise ValueError('DVD WAD identity differs')
    build=selected['player_build'];home=selected['home_ui'];dol=ROOT/f'workspace/channels/dvd-player/build-v{build}/boot.dol';arc=ROOT/f'workspace/channels/dvd-player/home-ui-v{home}/home.arc'
    bm=json.loads(dol.with_name('build-manifest.json').read_text(encoding='utf-8'));hm=json.loads(arc.with_name('home-ui-manifest.json').read_text(encoding='utf-8'))
    if sha256(dol)!=bm['boot_dol_sha256']or sha256(arc)!=hm['sha256']:raise ValueError('DVD build or HOME identity differs')
    lib=load_library();title=lib.title.Title();title.load_wad(wad.read_bytes())
    expected_dol=dol.read_bytes()
    if selected.get('boot_adapter'):
        from kwce.dvd_channel_boot import channel_boot
        expected_dol,adapter=channel_boot(expected_dol)
        if adapter!=selected['boot_adapter']:raise ValueError('DVD channel adapter mismatch')
    if title.get_content_by_index(1)!=expected_dol or title.get_content_by_index(3)!=arc.read_bytes():raise ValueError('DVD WAD payload mismatch')
    n=1
    while(PRIVATE/f'dvd-test-v2-update-before-{n}').exists():n+=1
    backup=PRIVATE/f'dvd-test-v2-update-before-{n}';backup.mkdir();shutil.copy2(manifest,backup/manifest.name)
    for name in ['active-player.json','active-home.json']:shutil.copy2(content/name,backup/name)
    lib.nand.EmuNAND(runtime/'user/Wii').install_title(title);verify_installed_title(runtime/'user/Wii',title.tmd.title_id,title.tmd.dump())
    shutil.copy2(dol,runtime/'sd-sync/apps/kwce-dvd/boot.dol');shutil.copy2(arc,content/'home.arc')
    (content/'active-player.json').write_text(json.dumps(dict(revision=build,sha256=bm['boot_dol_sha256'],css_decryption=bm['css_decryption'])),encoding='utf-8')
    (content/'active-home.json').write_text(json.dumps(dict(revision=home,sha256=hm['sha256'])),encoding='utf-8')
    record.update(player_build=build,home_ui=home,wad=args.wad,wad_sha256=selected['wad_sha256']);manifest.write_text(json.dumps(record,indent=2),encoding='utf-8')
    path=ROOT/'configs/channels.catalog.json';catalog=json.loads(path.read_text(encoding='utf-8'))
    for ch in catalog['channels']:
        if ch['id']=='dvd-player':ch['installs'][0]['artifact']=f'wad-v{args.wad}';ch['base_version']=args.wad
    for row in catalog['test_beds']:
        if row['profile']=='dvd-test-v2':row.update(player_build=f'build-v{build}',home_ui=f'home-ui-v{home}',purpose=f'integrated R{build}/HOME{home}/WAD{args.wad}, patched menu, auto-insert synthetic fixture and verified user DVD')
    path.write_text(json.dumps(catalog,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print(f'PASS: DVD integrated test bed R{build}/HOME{home}/WAD{args.wad}; catalog updated and installed contents verified')

if __name__=='__main__':main()

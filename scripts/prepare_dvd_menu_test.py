"""Create a new v2 DVD test bed: patched menu, current player, auto-insert fixture.
All inputs and the v1 profile are preserved. No real SD or console writes.
"""
import argparse,configparser,json,os,shutil,struct,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.dvd_menu_preview import patch_preview

TARGET=ROOT/'workspace/sandbox/dvd-test-v2'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--build',type=int,required=True);ap.add_argument('--home',type=int,required=True);ap.add_argument('--wad',type=int,required=True);args=ap.parse_args()
    stopped()
    if TARGET.exists():raise SystemExit('Existing DVD menu test bed preserved')
    parent=ROOT/'workspace/sandbox/dvd-test-v1'
    for folder in ['user','Dolphin-x64','sd-sync']:
        shutil.copytree(parent/folder,TARGET/folder,ignore=shutil.ignore_patterns('Logs','Cache','Dump','ScreenShots','StateSaves'))
    shutil.copy2(parent/'NetProbe.exe',TARGET/'NetProbe.exe')
    # Reuse the approved GC/FST runtime and disc-channel hook, without changing gc-v8.
    shutil.copytree(ROOT/'workspace/sandbox/gc-v8/Dolphin-x64',TARGET/'Dolphin-x64',dirs_exist_ok=True)
    src=ROOT/'workspace/sandbox/gc-v8/user/Wii/title/00000001/00000002/content'
    dst=TARGET/'user/Wii/title/00000001/00000002/content';old=bytearray((dst/'title.tmd').read_bytes());base=(src/'title.tmd').read_bytes();content_hashes={}
    for i in range(int.from_bytes(base[0x1de:0x1e0],'big')):
        a=0x1e4+36*i;cid,index=struct.unpack_from('>IH',base,a)
        if index not in (1,6):continue
        data=(src/f'{cid:08x}.app').read_bytes()
        if index==1:data,preview=patch_preview(data)
        for j in range(int.from_bytes(old[0x1de:0x1e0],'big')):
            b=0x1e4+36*j;dcid,dindex=struct.unpack_from('>IH',old,b)
            if dindex==index:
                (dst/f'{dcid:08x}.app').write_bytes(data);struct.pack_into('>Q',old,b+8,len(data))
                import hashlib
                old[b+16:b+36]=hashlib.sha1(data).digest();content_hashes[str(index)]=hashlib.sha256(data).hexdigest();break
        else:raise ValueError('System menu content index missing')
    (dst/'title.tmd').write_bytes(old)
    wad=ROOT/f'workspace/channels/dvd-player/wad-v{args.wad}/dvd-player.wad';wm=json.loads(wad.with_name('wad-manifest.json').read_text(encoding='utf-8'))
    if wm['player_build']!=args.build or wm['home_ui']!=args.home or sha256(wad)!=wm['wad_sha256']:raise ValueError('Selected WAD differs')
    lib=load_library();title=lib.title.Title();title.load_wad(wad.read_bytes());lib.nand.EmuNAND(TARGET/'user/Wii').install_title(title)
    content=TARGET/'sd-sync/kwce/dvd'
    dol=ROOT/f'workspace/channels/dvd-player/build-v{args.build}/boot.dol';home=ROOT/f'workspace/channels/dvd-player/home-ui-v{args.home}/home.arc'
    shutil.copy2(dol,TARGET/'sd-sync/apps/kwce-dvd/boot.dol');shutil.copy2(home,content/'home.arc')
    (content/'active-player.json').write_text(json.dumps(dict(revision=args.build,sha256=sha256(dol),css_decryption=False)),encoding='utf-8')
    (content/'active-home.json').write_text(json.dumps(dict(revision=args.home,sha256=sha256(home))),encoding='utf-8')
    disc=ROOT/'workspace/test-media/wii/kwce-wii-unreadable-v1.iso';dm=json.loads(disc.with_suffix('.json').read_text())
    if not dm['synthetic']or sha256(disc)!=dm['sha256']:raise ValueError('Unverified insertion fixture')
    (TARGET/'disc').mkdir();shutil.copy2(disc,TARGET/'disc/dvd-insertion.iso');shutil.copy2(disc.with_suffix('.json'),TARGET/'disc/dvd-insertion.json')
    ini=TARGET/'user/Config/Dolphin.ini';text=ini.read_text(encoding='utf-8-sig').replace(str(parent),str(TARGET)).replace(parent.as_posix(),TARGET.as_posix())
    ini.write_text(text,encoding='utf-8');config=configparser.ConfigParser(strict=False);config.optionxform=str;config.read(ini,encoding='utf-8-sig')
    config['Core']['DefaultISO']=str(TARGET/'disc/dvd-insertion.iso')
    with ini.open('w',encoding='utf-8')as f:config.write(f,space_around_delimiters=True)
    # A fresh, narrowly scoped capability-zero helper; only the DOL and Wii Menu.
    bindir=ROOT/'tools/dvd-test/v2/bin';bindir.mkdir(parents=True,exist_ok=True)
    source=(ROOT/'tools/dvd-test/v1/bin/DvdTestRunner.cs').read_text(encoding='utf-8').replace('dvd-test-v1','dvd-test-v2')
    source=source.replace('args[1]!="dol"','(args[1]!="dol"&&args[1]!="menu")')
    source=source.replace('" --exec "+Quote(dol)','(args[1]=="menu"?" --nand_title 0000000100000002":" --exec "+Quote(dol))')
    cs=bindir/'DvdTestRunner.cs';cs.write_text(source,encoding='utf-8');csc=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(csc),'/nologo','/target:exe','/platform:x64','/out:'+str(bindir/'DvdTestRunner.exe'),str(cs)],check=True,capture_output=True)
    record=dict(profile='dvd-test-v2',player_build=args.build,home_ui=args.home,wad=args.wad,wad_sha256=wm['wad_sha256'],system_menu_contents=content_hashes,
                runtime_sha256=sha256(TARGET/'Dolphin-x64/Dolphin.exe'),helper_sha256=sha256(bindir/'DvdTestRunner.exe'),preview=preview,insertion_fixture_sha256=dm['sha256'])
    (TARGET/'test-bed-manifest.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('DVD v2 test bed ready: patched menu, current channel, verified synthetic disc auto-inserted')

if __name__=='__main__':main()

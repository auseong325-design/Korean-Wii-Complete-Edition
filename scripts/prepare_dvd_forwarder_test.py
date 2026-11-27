"""Windows test bed for the forwarder-era DVD set (hook 75+): new dvd-test-vN, never in place.

The hooks from source revision 34 on are built on Linux. This copies the stopped
dvd-test-v3 (no KDVD title, synthetic insertion disc, test SD) to a new dvd-test-vN,
installs an existing workspace/experiments/dvd-native-hook-vR (menu-with-card-encoding.dol
= GC hacks + DVD hook, as the console runs them through Priiloader) into its NAND and
copies the kwce/dvd files of a finished SD package (workspace/hardware/<package>) into
its test SD, after checking every file against the hook, player and HOME manifests.
  --create N --revision R --package P     make dvd-test-vN
  --bed N --aspect 4:3|16:9               set SYSCONF IPL.AR + Dolphin aspect (stopped)
dvd-test-v3 and every real SD card are never written.
"""
import argparse,configparser,hashlib,json,os,shutil,struct,subprocess
from pathlib import Path
from audit_sd import ROOT,sha256
from prepare_channel_access import stopped

SOURCE=ROOT/'workspace/sandbox/dvd-test-v3'
SD_FILES=('boot.ash','menu.arc','icon.arc','player.dol','home.arc','wbf1.brfna')

def bed(n):
    if n<4:raise SystemExit('dvd-test-v1..v3 are preserved; forwarder beds start at v4')
    return ROOT/f'workspace/sandbox/dvd-test-v{n}'

def set_aspect(target,aspect):
    p=target/'user/Wii/shared2/sys/SYSCONF';data=bytearray(p.read_bytes());hits=0
    for i in range(int.from_bytes(data[4:6],'big')):
        at=int.from_bytes(data[6+2*i:8+2*i],'big');length=(data[at]&31)+1
        if data[at+1:at+1+length]==b'IPL.AR':
            if data[at]>>5!=3:raise ValueError('Unexpected aspect setting type')
            data[at+1+length]=0 if aspect=='4:3' else 1;hits+=1
    if hits!=1:raise ValueError('Aspect setting identity')
    p.write_bytes(data)
    gfx=target/'user/Config/GFX.ini';c=configparser.ConfigParser(strict=False);c.optionxform=str
    if gfx.exists():c.read(gfx,encoding='utf-8-sig')
    if not c.has_section('Settings'):c.add_section('Settings')
    c['Settings']['AspectRatio']='2' if aspect=='4:3' else '0'  # 2 = force 4:3, 0 = auto (game's 16:9 flag)
    with gfx.open('w',encoding='utf-8')as f:c.write(f)

def create(n,revision,package):
    target=bed(n)
    if target.exists():raise SystemExit('Existing test bed preserved')
    hook=ROOT/f'workspace/experiments/dvd-native-hook-v{revision}';r=json.loads((hook/'manifest.json').read_text())
    if sha256(hook/'menu.dol')!=r['sha256'] or not r.get('forwarder'):raise SystemExit('Unreviewed or changed native hook')
    menu=(hook/'menu-with-card-encoding.dol').read_bytes()
    sd=ROOT/'workspace/hardware'/package/'kwce/dvd'
    expected={'boot.ash':r['module_sha256'],'menu.arc':r['banner_sha256'],'icon.arc':r['icon_sha256'],'player.dol':r['sd_player_sha256']}
    for name,want in expected.items():
        if sha256(sd/name)!=want:raise SystemExit(f'{package}: {name} differs from native hook v{revision}')
    build=json.loads((ROOT/f'workspace/channels/dvd-player/build-v{r["player_revision"]}/build-manifest.json').read_text())
    if build['boot_dol_sha256']!=r['sd_player_sha256']:raise SystemExit('Player build manifest differs')
    home_sha=sha256(sd/'home.arc');home_rev=None
    for p in sorted((ROOT/'workspace/channels/dvd-player').glob('home-ui-v*/home-ui-manifest.json')):
        if json.loads(p.read_text(encoding='utf-8'))['sha256']==home_sha:home_rev=int(p.parent.name.rsplit('-v',1)[1])
    if home_rev is None:raise SystemExit('Packaged home.arc is not a recorded HOME UI build')
    record=json.loads((SOURCE/'test-bed-manifest.json').read_text(encoding='utf-8'))
    target.mkdir()
    for folder in ('user','Dolphin-x64','sd-sync','disc'):
        shutil.copytree(SOURCE/folder,target/folder,ignore=shutil.ignore_patterns('Logs','Cache','Dump','ScreenShots','StateSaves'))
    shutil.copy2(SOURCE/'NetProbe.exe',target/'NetProbe.exe')
    ini=target/'user/Config/Dolphin.ini'
    ini.write_text(ini.read_text(encoding='utf-8-sig').replace(str(SOURCE),str(target)).replace(SOURCE.as_posix(),target.as_posix()),encoding='utf-8')
    content=target/'user/Wii/title/00000001/00000002/content';tmd=bytearray((content/'title.tmd').read_bytes())
    for i in range(int.from_bytes(tmd[0x1de:0x1e0],'big')):
        at=0x1e4+36*i;cid,idx=struct.unpack_from('>IH',tmd,at)
        if idx==6:
            (content/f'{cid:08x}.app').write_bytes(menu);struct.pack_into('>Q',tmd,at+8,len(menu));tmd[at+16:at+36]=hashlib.sha1(menu).digest();break
    else:raise SystemExit('Menu DOL missing')
    (content/'title.tmd').write_bytes(tmd)
    dvd=target/'sd-sync/kwce/dvd'
    for name in SD_FILES:shutil.copy2(sd/name,dvd/name)
    shutil.copy2(sd/'player.dol',target/'sd-sync/apps/kwce-dvd/boot.dol')
    (dvd/'active-player.json').write_text(json.dumps(dict(revision=r['player_revision'],sha256=r['sd_player_sha256'],css_decryption=False)))
    (dvd/'active-home.json').write_text(json.dumps(dict(revision=home_rev,sha256=home_sha)))
    helper=ROOT/f'tools/dvd-test/v{n}/bin';helper.mkdir(parents=True)
    code=(ROOT/'tools/dvd-test/v3/bin/DvdTestRunner.cs').read_text()
    if code.count('"dvd-test-v3"')!=1:raise SystemExit('Helper source layout changed')
    cs=helper/'DvdTestRunner.cs';cs.write_text(code.replace('"dvd-test-v3"',f'"dvd-test-v{n}"'),encoding='utf-8')
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler),'/nologo','/target:exe','/platform:x64','/out:'+str(helper/'DvdTestRunner.exe'),str(cs)],check=True,capture_output=True)
    record.update(profile=f'dvd-test-v{n}',copied_from='dvd-test-v3',player_build=r['player_revision'],home_ui=home_rev,helper_sha256=sha256(helper/'DvdTestRunner.exe'),aspect='16:9',
                  native_hook=dict(revision=revision,sha256=hashlib.sha256(menu).hexdigest(),hook_menu_sha256=r['sha256'],installed='menu-with-card-encoding.dol',
                                   module_sha256=r['module_sha256'],player_sha256=r['sd_player_sha256'],banner_sha256=r['banner_sha256'],icon_sha256=r['icon_sha256'],
                                   sd_package=package,sd_player_path='kwce/dvd/player.dol'),
                  forwarder=True)
    record['system_menu_contents']['6']=hashlib.sha256(menu).hexdigest()
    (target/'test-bed-manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    catalog=ROOT/'configs/channels.catalog.json';j=json.loads(catalog.read_text(encoding='utf-8'))
    j['test_beds'].append(dict(profile=f'dvd-test-v{n}',purpose=f'Windows DVD forwarder test bed (16:9/4:3): {package} DVD set, no KDVD title; scripts/launch_dvd_test.py --profile dvd-test-v{n} --menu',
                               native_hook=f'dvd-native-hook-v{revision}',player_build=f'build-v{r["player_revision"]}',home_ui=f'home-ui-v{home_rev}',platform='windows',role='experimental'))
    catalog.write_text(json.dumps(j,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print(json.dumps(dict(profile=f'dvd-test-v{n}',native_hook=revision,player=r['player_revision'],home_ui=home_rev,package=package)))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--create',type=int);ap.add_argument('--revision',type=int);ap.add_argument('--package')
    ap.add_argument('--bed',type=int);ap.add_argument('--aspect',choices=['4:3','16:9'])
    a=ap.parse_args();stopped()
    if a.create:
        if not(a.revision and a.package):raise SystemExit('--create needs --revision and --package')
        create(a.create,a.revision,a.package)
    elif a.bed and a.aspect:
        target=bed(a.bed);path=target/'test-bed-manifest.json';m=json.loads(path.read_text(encoding='utf-8'))
        if not m.get('forwarder'):raise SystemExit('Not a forwarder test bed')
        set_aspect(target,a.aspect);m['aspect']=a.aspect;path.write_text(json.dumps(m,indent=2)+'\n');print('aspect',a.aspect)
    else:raise SystemExit('Nothing to do')

if __name__=='__main__':main()

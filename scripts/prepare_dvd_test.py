"""Emulator test bed for the KWCE DVD player DOL (stopped Dolphin only).

Creates workspace/sandbox/dvd-test-v1 (new, never overwritten) from the
stopped hardware-test-v1 runtime + NAND, a capability-zero helper that only
boots sd-sync/apps/kwce-dvd/boot.dol, and a Dolphin SD sync folder.
  --build N   copies workspace/channels/dvd-player/build-vN/boot.dol
  --disc N    copies the synthetic workspace/test-media/dvd/kwce-dvd-test-vN.iso
              to sd-sync/kwce/dvd/test-disc.iso (Dolphin cannot read DVD-Video discs)
  --user-disc N copies a hash-verified private VIDEO_TS import without transcoding;
              the previous selected image is backed up before replacement
  --home N    copies workspace/channels/dvd-player/home-ui-vN/home.arc to sd-sync/kwce/dvd/home.arc
The 43K Korean shared font copy goes to sd-sync/kwce/dvd/wbf1.brfna; on a console the
player reads the same files from its own channel contents.
"""
import argparse,configparser,json,os,shutil,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,sha256
from prepare_channel_access import stopped
sys.path.insert(0,str(ROOT))

SANDBOX=ROOT/'workspace/sandbox/dvd-test-v1'
TEMPLATE=ROOT/'workspace/sandbox/hardware-test-v1'
HELPER=ROOT/'tools/dvd-test/v1/bin'

def build_helper():
    if HELPER.exists():return
    HELPER.mkdir(parents=True)
    text=(ROOT/'scripts/FeedRunner.cs').read_text()
    text=text.replace('class FeedRunner','class DvdTestRunner')
    old='bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","news-v1"),StringComparison.OrdinalIgnoreCase);'
    new='bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","dvd-test-v1"),StringComparison.OrdinalIgnoreCase);'
    start=text.index('   if(args.Length!=3||args[2]!="0001000248414745"');end=text.index('   File.WriteAllText(Path.Combine(root,"child-exit.json")')
    block='''   if(args.Length!=2||args[1]!="dol")throw new Exception("Only the DVD player DOL mode is supported");
   string exe=Path.Combine(root,"Dolphin-x64","Dolphin.exe");string user=Path.Combine(root,"user");
   string dol=Path.Combine(root,"sd-sync","apps","kwce-dvd","boot.dol");if(!File.Exists(dol))throw new Exception("DVD player DOL missing");
   int childCode=Run(sid,exe,"--user "+Quote(user)+" --exec "+Quote(dol),Path.GetDirectoryName(exe));
'''
    if old not in text:raise SystemExit('FeedRunner layout changed')
    text=text[:start].replace(old,new)+block+text[end:]
    source=HELPER/'DvdTestRunner.cs';source.write_text(text,encoding='utf-8')
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler),'/nologo','/target:exe','/platform:x64','/out:'+str(HELPER/'DvdTestRunner.exe'),str(source)],check=True,capture_output=True)
    (HELPER/'helper-build.json').write_text(json.dumps(dict(source='scripts/FeedRunner.cs',sha256=sha256(HELPER/'DvdTestRunner.exe')),indent=2))

def create():
    if SANDBOX.exists():return
    SANDBOX.mkdir()
    shutil.copytree(TEMPLATE/'Dolphin-x64',SANDBOX/'Dolphin-x64');shutil.copy2(TEMPLATE/'NetProbe.exe',SANDBOX/'NetProbe.exe')
    shutil.copytree(TEMPLATE/'user',SANDBOX/'user',ignore=shutil.ignore_patterns('Logs','Cache','ScreenShots'))
    ini=SANDBOX/'user/Config/Dolphin.ini';config=configparser.ConfigParser(strict=False);config.optionxform=str;config.read(ini,encoding='utf-8-sig')
    for section in config.sections():
        for key,value in config[section].items():
            if 'hardware-test-v1' in value:config[section][key]=value.replace('hardware-test-v1','dvd-test-v1')
    with ini.open('w',encoding='utf-8')as f:config.write(f,space_around_delimiters=True)
    (SANDBOX/'sd-sync/apps/kwce-dvd').mkdir(parents=True);(SANDBOX/'sd-sync/kwce/dvd').mkdir(parents=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--build',type=int);media=ap.add_mutually_exclusive_group();media.add_argument('--disc',type=int);media.add_argument('--user-disc',type=int,help='verified private VIDEO_TS import revision explicitly supplied by the user');ap.add_argument('--home',type=int);args=ap.parse_args()
    if any(n is not None and n<1 for n in [args.build,args.disc,args.user_disc,args.home]):raise SystemExit('DVD revisions must be positive')
    stopped();build_helper();create()
    dvd=SANDBOX/'sd-sync/kwce/dvd'
    if args.disc is not None or args.user_disc is not None:
        from audit_sd import PRIVATE
        number=1
        while(PRIVATE/f'dvd-test-media-before-{number}').exists():number+=1
        backup=PRIVATE/f'dvd-test-media-before-{number}';backup.mkdir()
        for name in ['test-disc.iso','current-media.json']:
            if(dvd/name).exists():shutil.copy2(dvd/name,backup/name)
    from kwce.channel_korean_font import korean_shared_fonts
    fonts,_=korean_shared_fonts();(dvd/'wbf1.brfna').write_bytes(fonts)
    if args.build:
        dol=ROOT/f'workspace/channels/dvd-player/build-v{args.build}/boot.dol'
        if not dol.exists():raise SystemExit('Unknown DVD player build')
        build_record=json.loads(dol.with_name('build-manifest.json').read_text(encoding='utf-8'))
        if sha256(dol)!=build_record['boot_dol_sha256']:raise SystemExit('DVD player build differs from its manifest')
        shutil.copy2(dol,SANDBOX/'sd-sync/apps/kwce-dvd/boot.dol');print('DOL copied: build',args.build)
        (dvd/'active-player.json').write_text(json.dumps(dict(revision=args.build,sha256=build_record['boot_dol_sha256'],css_decryption=build_record['css_decryption']),indent=2))
    if args.home:
        home=ROOT/f'workspace/channels/dvd-player/home-ui-v{args.home}'
        record=json.loads((home/'home-ui-manifest.json').read_text(encoding='utf-8'))
        if sha256(home/'home.arc')!=record['sha256']:raise SystemExit('HOME Menu archive differs from its manifest')
        shutil.copy2(home/'home.arc',dvd/'home.arc');print('HOME Menu archive copied: v',args.home)
        (dvd/'active-home.json').write_text(json.dumps(dict(revision=args.home,sha256=record['sha256']),indent=2))
    if args.disc:
        iso=ROOT/f'workspace/test-media/dvd/kwce-dvd-test-v{args.disc}.iso'
        meta=json.loads(iso.with_suffix('.json').read_text(encoding='utf-8'))
        if not meta.get('synthetic') or sha256(iso)!=meta['sha256']:raise SystemExit('Only the hashed synthetic test disc is allowed')
        shutil.copy2(iso,dvd/'test-disc.iso')
        (dvd/'current-media.json').write_text(json.dumps(dict(kind='synthetic',revision=args.disc,sha256=sha256(iso),size=iso.stat().st_size),indent=2))
        print('synthetic test disc copied: v',args.disc)
    if args.user_disc is not None:
        from import_dvd_video import verify_iso
        source=ROOT/f'workspace/private/dvd-user-test-v{args.user_disc}';meta=json.loads((source/'import-manifest.json').read_text(encoding='utf-8'));iso=source/'test-disc.iso'
        if not meta.get('user_provided')or meta.get('synthetic')or not meta.get('source_unchanged')or meta.get('transcoded')or sha256(iso)!=meta['iso_sha256']:raise SystemExit('Unverified user DVD import')
        if meta['css_scrambling_marked_sectors']or any(meta['decode_exit_codes']):raise SystemExit('User DVD needs an unresolved input-format check')
        verify_iso(iso,meta['files']);shutil.copy2(iso,dvd/'test-disc.iso')
        if sha256(dvd/'test-disc.iso')!=meta['iso_sha256']:raise ValueError('DVD test media copy differs')
        (dvd/'current-media.json').write_text(json.dumps(dict(kind='user-provided',revision=args.user_disc,sha256=meta['iso_sha256'],size=iso.stat().st_size),indent=2))
        print('verified user DVD image copied: revision',args.user_disc,'; original and previous test image preserved')
    print('DVD test bed ready:',SANDBOX.relative_to(ROOT))

if __name__=='__main__':main()

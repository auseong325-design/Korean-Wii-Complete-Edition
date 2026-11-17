"""Launch only the pinned, isolated TV Guide translation experiment."""
import argparse,configparser,json,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_tvguide_test import register,PROFILE,TITLE,BASE,HELPER
import launch_dolphin as launcher
from kwce.channels import load_library
from kwce.channel_validation import verify_installed_title

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.add_argument('--menu',action='store_true');parser.add_argument('--wait',action='store_true',help=argparse.SUPPRESS);args=parser.parse_args();stopped();register()
    lock=json.loads((ROOT/'configs/tvguide-runtime.lock.json').read_text())
    if lock['profile']!=PROFILE or lock['title_id']!=TITLE or lock['capability_count']!=0 or lock['external_network_allowed']:raise ValueError('TV scope differs')
    for row in lock['files']:
        if sha256(ROOT/row['path'])!=row['sha256']:raise ValueError('Pinned TV artifact differs')
    feed=BASE/'local-feed';fixture=json.loads((feed/'fixture-manifest.json').read_text())
    if not fixture.get('local_only')or not fixture.get('synthetic'):raise ValueError('TV fixture scope differs')
    for row in fixture['files']:
        p=feed/row['path']
        if Path(row['path']).name!=row['path']or not p.is_file()or sha256(p)!=row['sha256']:raise ValueError('TV fixture payload differs')
    if fixture['revision']in(2,3,4,5):
        from kwce.tvguide_fixtures import compressed_header,encrypted_header
        expected=compressed_header()if fixture['revision']==2 else encrypted_header((BASE/'user/Wii/title/00010001/48424e4a/data/wc24pubk.mod').read_bytes(),schema=fixture['revision']-2)
        if(feed/'header.bin').read_bytes()!=expected or(feed/'routes.tsv').read_text()!='GET /header.bin\theader.bin\n':raise ValueError('TV synthetic header differs')
    elif fixture['revision']==6:
        if fixture.get('expected_error')!=117404 or(feed/'routes.tsv').read_bytes()!=b'':raise ValueError('TV unavailable-data diagnostic differs')
    elif fixture['revision']==7:
        # Schedule feed: header + epg + str, each the WC24-enveloped HDPK under
        # root 'main'. Verify the bytes match the fixtures and the routes map
        # every served path (base and /binN/) to the three files.
        from kwce.tvguide_fixtures import feed_v7_resources
        module=(BASE/'user/Wii/title/00010001/48424e4a/data/wc24pubk.mod').read_bytes()
        expected=feed_v7_resources(module)
        if(feed/'header.bin').read_bytes()!=expected['header']or(feed/'epg.bin').read_bytes()!=expected['epg']or(feed/'str.bin').read_bytes()!=expected['string']:raise ValueError('TV schedule feed resources differ')
        routes=(feed/'routes.tsv').read_text()
        for name in('header.bin','epg.bin','str.bin'):
            if('* /%s\t%s'%(name,name))not in routes:raise ValueError('TV schedule feed route missing: '+name)
    elif fixture['revision']!=1:raise ValueError('Unknown TV fixture revision')
    for p in BASE.rglob('*'):
        if p.is_symlink()or p.is_junction():raise ValueError('Indirect TV path')
    if not args.check:launcher.scrub_download_tasks(PROFILE)
    launcher.validate(PROFILE);cfg=configparser.ConfigParser(strict=False);cfg.read(BASE/'user/Config/Dolphin.ini',encoding='utf-8-sig')
    if cfg['Core'].get('DefaultISO')or cfg['Core'].getboolean('EnableWiiLink'):raise ValueError('Unexpected TV boot settings')
    for key in ['WiiSDCard','WiiSDCardEnableFolderSync','WiiSDCardAllowWrites']:
        if cfg['Core'].getboolean(key,fallback=False):raise ValueError('TV SD access refused')
    for section in cfg.sections():
        for key,value in cfg[section].items():
            if(key.lower().endswith(('path','pathoverride'))or key.lower()in('nandroot','dump','load'))and value.strip():
                if not Path(value).resolve().is_relative_to((BASE/'user').resolve()):raise ValueError('TV outside profile path')
    revision=json.loads((ROOT/'workspace/channels/tvguide/active-build.json').read_text())['revision'];wad=ROOT/f'workspace/channels/tvguide/build-v{revision}/tvguide-ko-local-test.wad'
    if sha256(wad)!=lock['builds'].get(str(revision)):raise ValueError('Unapproved TV build')
    title=load_library().title.Title();title.load_wad(wad.read_bytes());verify_installed_title(BASE/'user/Wii',TITLE,title.tmd.dump())
    reference=ROOT/'workspace/sandbox/votes-test-v1/user/Wii/title/00000001'
    for name in ['00000002','00000100','00000101']:
        for p in(reference/name/'content').glob('*'):
            if p.is_file()and sha256(p)!=sha256(BASE/'user/Wii/title/00000001'/name/'content'/p.name):raise ValueError('TV system contents changed')
    if args.check:print('PASS: TV Guide 14 contents, Korean locale, sanitized WC24, pinned runtime/helper, local fixture and preserved system');return
    number=1
    while(PRIVATE/f'tvguide-run-{number}.log').exists():number+=1
    env=launcher.proxy_environment()
    # KD's host HTTP client honors proxy variables, unlike the Wii socket path.
    # The fixture server lives at .2 inside the same zero-capability container.
    env['no_proxy']+=',127.0.0.2'
    if not args.wait:
        controller=1
        while(PRIVATE/f'tvguide-controller-{controller}.log').exists():controller+=1
        command=[sys.executable,str(Path(__file__).resolve()),'--wait']+(['--menu']if args.menu else[])
        with(PRIVATE/f'tvguide-controller-{controller}.log').open('x')as log:
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        print('TV Guide isolated local experiment controller started; PID',process.pid);return
    with(PRIVATE/f'tvguide-run-{number}.log').open('x')as log:
        process=subprocess.Popen([str(HELPER/'TvGuideRunner.exe'),str(BASE),'menu'if args.menu else'channel',TITLE],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        code=process.wait()
    # The container helper waits until its Dolphin child has exited. Only then
    # neutralize its newly registered tasks so the next --check stays useful.
    launcher.scrub_download_tasks(PROFILE)
    if code:raise SystemExit('TV experiment ended with a helper error; private diagnostics preserved')
    print('TV experiment stopped; local scheduled tasks normalized')
if __name__=='__main__':main()

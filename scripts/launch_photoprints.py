"""Launch (or --check) the isolated Korean Photo Prints experiment.

--check statically verifies the pinned runtime, read-only local feed, Korean
locale with SD/WiiLink disabled, the installed title and preserved system
contents, and runs no emulator. A full launch uses the capability-0 helper and
the loopback fixture server; it is the lead's path (Dolphin), not the agent's.
--menu boots the profile's Korean Wii Menu (0000000100000002) through the same
pinned helper, AppContainer and local server instead of the channel, so the
menu icon and banner can be reviewed:

  .venv\\Scripts\\python.exe scripts\\launch_photoprints.py --check
  .venv\\Scripts\\python.exe scripts\\launch_photoprints.py [--menu]   # lead only
"""
import argparse,configparser,json,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_photoprints_test import register,PROFILE,TITLE,BASE,HELPER
import launch_dolphin as launcher
from kwce.channels import load_library
from kwce.channel_validation import verify_installed_title
from kwce import photoprints_fixtures as fx

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true')
    ap.add_argument('--menu',action='store_true',help='start the Korean Wii Menu instead of the channel (same helper)')
    ap.add_argument('--wait',action='store_true',help=argparse.SUPPRESS);args=ap.parse_args();stopped();register()
    lock=json.loads((ROOT/'configs/photoprints-runtime.lock.json').read_text())
    if lock['profile']!=PROFILE or lock['title_id']!=TITLE or lock['capability_count']!=0 or lock['external_network_allowed']:raise ValueError('Photo Prints scope differs')
    for row in lock['files']:
        if sha256(ROOT/row['path'])!=row['sha256']:raise ValueError('Pinned Photo Prints artifact differs: '+row['path'])
    feed=BASE/'local-feed';fixture=json.loads((feed/'fixture-manifest.json').read_text())
    if not fixture.get('local_only') or not fixture.get('synthetic') or not fixture.get('read_only'):raise ValueError('Photo Prints fixture scope differs')
    if fixture.get('accepts_uploads') or fixture.get('accepts_orders'):raise ValueError('Fixture must not accept orders/uploads')
    allowed=set(fx.READ_ONLY_OPERATIONS)
    for row in fixture['operations']:
        if row['operation'] not in allowed:raise ValueError('Fixture serves a non-read-only operation')
        p=feed/row['file']
        if Path(row['file']).name!=row['file'] or not p.is_file() or sha256(p)!=row['sha256']:raise ValueError('Fixture payload differs')
    for op in fixture['refused_operations']:
        if (feed/f'op_{op}.bin').exists():raise ValueError('A refused operation has a response file: '+op)
    for p in BASE.rglob('*'):
        if p.is_symlink() or p.is_junction():raise ValueError('Indirect Photo Prints path')
    if not args.check:launcher.scrub_download_tasks(PROFILE)
    launcher.validate(PROFILE);cfg=configparser.ConfigParser(strict=False);cfg.read(BASE/'user/Config/Dolphin.ini',encoding='utf-8-sig')
    if cfg['Core'].get('DefaultISO') or cfg['Core'].getboolean('EnableWiiLink'):raise ValueError('Unexpected Photo Prints boot settings')
    for key in ['WiiSDCard','WiiSDCardEnableFolderSync','WiiSDCardAllowWrites']:
        if cfg['Core'].getboolean(key,fallback=False):raise ValueError('Photo Prints SD access refused')
    for section in cfg.sections():
        for key,value in cfg[section].items():
            if (key.lower().endswith(('path','pathoverride')) or key.lower() in('nandroot','dump','load')) and value.strip():
                if not Path(value).resolve().is_relative_to((BASE/'user').resolve()):raise ValueError('Photo Prints outside profile path')
    revision=json.loads((ROOT/'workspace/channels/photoprints/active-build.json').read_text())['revision']
    wad=ROOT/f'workspace/channels/photoprints/build-v{revision}/photoprints-ko-local-test.wad'
    if sha256(wad)!=lock['builds'].get(str(revision)):raise ValueError('Unapproved Photo Prints build')
    title=load_library().title.Title();title.load_wad(wad.read_bytes());verify_installed_title(BASE/'user/Wii',TITLE,title.tmd.dump())
    personal='no SPD'
    if 'personal_data' in lock:
        from kwce import photoprints_personal_data as pdata
        pdata.verify(BASE/'user/Wii',lock['personal_data'])
        personal='Korean SPD+IOS58'+(' + fictional pd.dat' if lock['personal_data'].get('pd_installed') else ', no pd.dat')
    reference=ROOT/'workspace/sandbox/votes-test-v1/user/Wii/title/00000001'
    for name in ['00000002','00000100','00000101']:
        folder=reference/name/'content'
        if folder.is_dir():
            for p in folder.glob('*'):
                if p.is_file() and sha256(p)!=sha256(BASE/'user/Wii/title/00000001'/name/'content'/p.name):raise ValueError('Photo Prints system contents changed')
    if args.check:print(f'PASS: Photo Prints build-v{revision}, 13 contents, Korean locale, SD/WiiLink off, read-only feed (no order/upload), {personal}, pinned runtime and preserved system');return
    number=1
    while(PRIVATE/f'photoprints-run-{number}.log').exists():number+=1
    env=launcher.proxy_environment();env['no_proxy']+=',127.0.0.2'
    if not args.wait:
        controller=1
        while(PRIVATE/f'photoprints-controller-{controller}.log').exists():controller+=1
        command=[sys.executable,str(Path(__file__).resolve()),'--wait']+(['--menu'] if args.menu else [])
        with(PRIVATE/f'photoprints-controller-{controller}.log').open('x') as logf:
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=logf,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        print('Photo Prints isolated local experiment controller started'+(' (Korean Wii Menu)' if args.menu else '')+'; PID',process.pid);return
    with(PRIVATE/f'photoprints-run-{number}.log').open('x') as logf:
        process=subprocess.Popen([str(HELPER/'PhotoPrintsRunner.exe'),str(BASE),'menu' if args.menu else 'channel',TITLE],cwd=ROOT,env=env,stdout=logf,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        code=process.wait()
    launcher.scrub_download_tasks(PROFILE)
    if code:raise SystemExit('Photo Prints experiment ended with a helper error; private diagnostics preserved')
    print('Photo Prints experiment stopped; local scheduled tasks normalized')
if __name__=='__main__':main()

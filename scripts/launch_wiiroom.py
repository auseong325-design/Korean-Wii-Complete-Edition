"""Only the separately pinned Wii Room local fixture experiment is allowed."""
import argparse,configparser,json,shutil,subprocess,sys
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_wiiroom_test import register,PROFILE,TITLE
import launch_dolphin as launcher
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.channel_validation import verify_installed_title
from kwce.dolphin_fst import inspect_fst

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');ap.add_argument('--menu',action='store_true');ap.add_argument('--probe',action='store_true');ap.add_argument('--diagnostic-original',action='store_true');ap.add_argument('--debugger',action='store_true');args=ap.parse_args()
    if args.probe and args.menu:raise SystemExit('Select one mode')
    stopped();register();root=launcher.user_path(PROFILE).parent;user=root/'user'
    for p in root.rglob('*'):
        if p.is_symlink()or p.is_junction()or p.lstat().st_file_attributes&0x400:raise SystemExit('Indirect Room path refused')
    lock=json.loads((ROOT/'configs/wiiroom-runtime.lock.json').read_text())
    if lock['capability_count']!=0 or lock['external_network_allowed']or lock['profile']!=PROFILE or lock['title_id']!=TITLE:raise SystemExit('Room scope changed')
    for row in lock['files']:
        if sha256(ROOT/row['path'])!=row['sha256']:raise SystemExit('Room pinned artifact changed')
    helper=ROOT/('tools/wiiroom-sandbox/v2/bin'if args.debugger else'tools/wiiroom-sandbox/v1/bin')
    if args.debugger and sha256(helper/'helper-build.json')!=lock.get('debug_helper_sha256'):raise SystemExit('Debug helper lock differs')
    helper_lock=json.loads((helper/'helper-build.json').read_text())
    for row in helper_lock['files']:
        if sha256(ROOT/row['path'])!=row['sha256']:raise SystemExit('Room helper/source changed')
    feed=root/'local-feed';fixture=json.loads((feed/'fixture-manifest.json').read_text())
    if not fixture['local_only']or not fixture['synthetic']:raise SystemExit('Only synthetic local fixtures allowed')
    for row in fixture['files']:
        if sha256(feed/row['path'])!=row['sha256']:raise SystemExit('Room fixture changed')
    cfg=configparser.ConfigParser(strict=False);cfg.read(user/'Config/Dolphin.ini',encoding='utf-8-sig');core=cfg['Core']
    if core.get('DefaultISO')or core.getboolean('EnableWiiLink')or not core.getboolean('OverrideRegionSettings'):raise SystemExit('Unexpected Room boot settings')
    for key in ['SerialPort1','SerialPort2']:
        if core.get(key,'255')!='255':raise SystemExit('GC network device refused')
    for key in ['WiiSDCard','WiiSDCardEnableFolderSync','WiiSDCardAllowWrites']:
        if core.get(key,'False').lower()!='false':raise SystemExit('SD access refused')
    for section in cfg.sections():
        for key,value in cfg[section].items():
            if(key.lower().endswith(('path','pathoverride'))or key.lower()in('nandroot','dump','load'))and value.strip():
                from pathlib import Path
                if not Path(value).resolve().is_relative_to(user.resolve()):raise SystemExit('Outside profile path refused')
    if not args.check:launcher.scrub_download_tasks(PROFILE)
    launcher.validate(PROFILE);inspect_fst((user/'Wii/fst.bin').read_bytes())
    if(user/'Wii/fst.bin.xxx').exists():raise SystemExit('Pending FST transaction')
    active=ROOT/'workspace/channels/wiiroom/active-build.json'
    active_record=json.loads(active.read_text())if active.exists()else dict(variant='korean-v1',revision=1)
    variant=active_record['variant'];revision=active_record.get('revision',1)
    if args.diagnostic_original!=(variant=='diagnostic-original'):raise SystemExit('Explicit original diagnostic mode must match installation')
    if not args.diagnostic_original and revision not in [*range(1,9),10,12,14,16,20,22,24,26,30,34,36,46,50,54,61]:raise SystemExit('Unapproved Room build')
    wad=ROOT/f'workspace/channels/wiiroom/build-v{revision}/wiiroom-ko-local-test.wad'
    if args.diagnostic_original:
        wad=ROOT/'workspace/channels/wiiroom/originals/wiiroom-english-wiilink-archive.wad'
        if sha256(wad)!='533ac68bc2b7267e52a18c48acf423c3f86c1e97641962d62a1991c630457d8c':raise SystemExit('Original diagnostic hash differs')
    else:
        meta=json.loads(wad.with_name('build-manifest.json').read_text())
        if sha256(wad)!=meta['wad_sha256']or meta['wad_sha256']!=lock.get('builds',{}).get(str(revision)):raise SystemExit('Room build lock differs')
    title=load_library().title.Title();title.load_wad(wad.read_bytes());verify_installed_title(user/'Wii',TITLE,title.tmd.dump())
    reference=ROOT/'workspace/sandbox/gc-v6/user/Wii/title/00000001'
    for name in ['00000002','00000100','00000101']:
        for p in(reference/name/'content').glob('*'):
            if p.is_file()and sha256(p)!=sha256(user/'Wii/title/00000001'/name/'content'/p.name):raise SystemExit('System contents changed')
    if args.check:print('PASS: Room 16 installed contents, Korean locale, sanitized credentials/tasks, local fixtures, pinned runtime/helper, preserved system');return
    env=launcher.proxy_environment();env['no_proxy']+=',127.0.0.2';run=1
    while(PRIVATE/f'wiiroom-helper-v1-run-{run}.log').exists():run+=1
    previous=user/'Logs/dolphin.log'
    launcher.archive_run_log(previous,PRIVATE/f'wiiroom-before-run-{run}-dolphin.log')
    with(PRIVATE/f'wiiroom-helper-v1-run-{run}.log').open('x',encoding='utf-8')as log:
        command=[str(helper/'WiiRoomRunner.exe'),str(root),'probe'if args.probe else'menu'if args.menu else'channel']
        if not args.probe:command.append(TITLE)
        process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    print('Wii Room capability-zero local experiment started; helper PID',process.pid)

if __name__=='__main__':main()

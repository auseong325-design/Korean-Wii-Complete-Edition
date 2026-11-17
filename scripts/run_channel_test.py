"""Launch a dedicated local-response test NAND with capability-zero networking."""
import argparse, configparser, json, subprocess, sys, struct,shutil
from urllib.parse import urlsplit,urlunsplit
from audit_sd import ROOT, PRIVATE, sha256
from prepare_channel_access import CHANNELS, register, stopped
import launch_dolphin as launcher
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.channel_validation import verify_installed_title
from kwce.dolphin_fst import inspect_fst
from kwce.channel_access import validate_fixtures

def own_task(row,title_id):
    return {int.from_bytes(row[8:12],'big'),int.from_bytes(row[12:16],'big')}=={int(title_id[:8],16),int(title_id[8:],16)}

def normalize_tasks(user,channel,title_id):
    # Only this new test profile is changed. Other channels' scheduled tasks
    # are disabled; this channel's public tasks are mapped to the local server.
    path=user/'Wii/shared2/wc24/nwc24dl.bin';old=path.read_bytes();data=normalized_tasks(old,channel,title_id)
    if data!=old:path.write_bytes(data)

def normalized_tasks(old,channel,title_id):
    from prepare_channel_access_v2 import HOSTS
    data=bytearray(old)
    if len(data)!=0xf800 or data[:8]!=bytes.fromhex('5763446c00000001'):raise SystemExit('Invalid task list')
    for i in range(120):
        at=2048+512*i;row=data[at:at+512]
        if not int.from_bytes(row[12:16],'big'):continue
        parsed=urlsplit(row[180:416].split(b'\0')[0].decode('ascii'))
        if own_task(row,title_id) and parsed.scheme=='http' and parsed.hostname in [*HOSTS[channel],'127.0.0.2']:
            url=urlunsplit(('http','127.0.0.2',parsed.path,parsed.query,'')).encode('ascii')
        else:
            struct.pack_into('>I',data,at+4,int.from_bytes(row[4:8],'big')|32)
            url=f'http://127.0.0.1:9/phase0-disabled/task-{i}'.encode()
        if len(url)>=236:raise SystemExit('Task URL capacity exceeded')
        data[at+180:at+416]=url+bytes(236-len(url))
    return bytes(data)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('channel',choices=CHANNELS)
    ap.add_argument('--check',action='store_true');ap.add_argument('--menu',action='store_true');ap.add_argument('--mii-setup',action='store_true');args=ap.parse_args()
    if args.mii_setup and(args.channel!='mii-contest'or args.menu):raise SystemExit('Mii setup is limited to the Mii test NAND')
    stopped();profile=register(args.channel);user=launcher.user_path(profile);root=user.parent
    revision,title_id,_=CHANNELS[args.channel]
    for p in root.rglob('*'):
        if p.is_symlink() or p.is_junction() or p.lstat().st_file_attributes & 0x400:raise SystemExit('Indirect experiment path refused')
    try:launcher.validate(profile)
    except SystemExit as e:
        if str(e)!='A scheduled task must be scrubbed before launch':raise
        # --check verifies the scrub the launch would apply, without writing.
        if not args.check:normalize_tasks(user,args.channel,title_id)
        data=(user/'Wii/shared2/wc24/nwc24dl.bin').read_bytes()
        if args.check:data=normalized_tasks(data,args.channel,title_id)
        for i in range(120):
            row=data[2048+512*i:2560+512*i]
            if not int.from_bytes(row[12:16],'big'):continue
            u=urlsplit(row[180:416].split(b'\0')[0].decode('ascii'))
            disabled=u.hostname=='127.0.0.1' and u.port==9 and int.from_bytes(row[4:8],'big')&32
            own=own_task(row,title_id)
            if not disabled and not(own and u.scheme=='http' and u.hostname=='127.0.0.2' and u.port in(None,80)):
                raise SystemExit('Unexpected scheduled task')
    lock=json.loads((ROOT/'configs/channel-access-runtime.lock.json').read_text())
    if lock['capability_count']!=0 or sha256(root/'Dolphin-x64/Dolphin.exe')!=lock['channels'][args.channel]['sha256']:raise SystemExit('Pinned experiment emulator changed')
    config=configparser.ConfigParser(strict=False);config.read(user/'Config/Dolphin.ini',encoding='utf-8-sig')
    if config['Core'].get('DefaultISO') or config['Core'].getboolean('EnableWiiLink'):raise SystemExit('Unexpected boot/URL settings')
    active_path=ROOT/f'workspace/channels/{args.channel}/active-access.json'
    access_revision=json.loads(active_path.read_text())['revision'] if active_path.exists() else 1
    if access_revision not in range(1,25):raise SystemExit('Unapproved access revision')
    build=ROOT/f'workspace/channels/{args.channel}/access-build-v{access_revision}';meta=json.loads((build/'build-manifest.json').read_text())
    wad=build/f'{args.channel}-local-test.wad'
    if sha256(wad)!=meta['wad_sha256']:raise SystemExit('Test WAD changed')
    if meta.get('network_patch_sha256') and sha256(user/f'GameSettings/{CHANNELS[args.channel][2][:3]}.ini')!=meta['network_patch_sha256']:raise SystemExit('Local network substitutions changed')
    title=load_library().title.Title();title.load_wad(wad.read_bytes())
    verify_installed_title(user/'Wii',title_id,title.tmd.dump());inspect_fst((user/'Wii/fst.bin').read_bytes())
    if args.mii_setup:
        reference=ROOT/'workspace/sandbox/gc-v6/user/Wii/title/00010002/48414341/content/title.tmd'
        verify_installed_title(user/'Wii','0001000248414341',reference.read_bytes())
    if(user/'Wii/fst.bin.xxx').exists():raise SystemExit('Pending filesystem transaction')
    baseline=ROOT/'workspace/sandbox/gc-v6/user/Wii/title/00000001'
    for name in ['00000002','00000100','00000101']:
        for p in(baseline/name/'content').glob('*'):
            if p.is_file() and sha256(p)!=sha256(user/'Wii/title/00000001'/name/'content'/p.name):raise SystemExit('System content changed')
    helper=ROOT/'tools/channel-access/v12/bin'
    for row in json.loads((helper/'helper-build.json').read_text())['files']:
        if sha256(ROOT/row['path'])!=row['sha256']:raise SystemExit('Access helper changed')
    validate_fixtures(root/'local-feed',args.channel)
    if args.check:print(f'PASS: {args.channel} test installation, locale, credentials, tasks, pinned runtime, helpers, system preservation');return
    env=launcher.proxy_environment();env['no_proxy']+=',127.0.0.2'
    n=1
    while(PRIVATE/f'{args.channel}-access-run-{n}.log').exists():n+=1
    previous=user/'Logs/dolphin.log'
    launcher.archive_run_log(previous,PRIVATE/f'{args.channel}-access-before-run-{n}-dolphin.log')
    with(PRIVATE/f'{args.channel}-access-run-{n}.log').open('x',encoding='utf-8')as log:
        p=subprocess.Popen([str(helper/'ChannelTestRunner.exe'),str(root),'avatar'if args.mii_setup else'menu'if args.menu else'channel','0001000248414341'if args.mii_setup else title_id],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    print(f'{args.channel} local test started in capability-zero AppContainer; helper PID {p.pid}')

if __name__=='__main__':main()

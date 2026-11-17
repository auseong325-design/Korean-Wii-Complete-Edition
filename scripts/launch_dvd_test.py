"""Boot the KWCE DVD player DOL in its emulator test bed (capability 0).

Allows preserved dvd-test-v1/v2 and channel-independent dvd-test-v3.
--menu starts the patched menu with a synthetic insertion fixture in v2/v3.
--check validates the profile without starting Dolphin.
"""
import argparse,configparser,json,subprocess
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
import launch_dolphin as launcher

PROFILE='dvd-test-v1-user';ROOT_DIR=ROOT/'workspace/sandbox/dvd-test-v1'
HELPER=ROOT/'tools/dvd-test/v1/bin/DvdTestRunner.exe'

def main():
    global PROFILE,ROOT_DIR,HELPER
    settings=json.loads((ROOT/'configs/emulator-launchers.json').read_text(encoding='utf-8'))
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');ap.add_argument('--menu',action='store_true');ap.add_argument('--profile',choices=['dvd-test-v1','dvd-test-v2','dvd-test-v3'],default=settings.get('dvd_test_profile','dvd-test-v1'));args=ap.parse_args()
    PROFILE=args.profile+'-user';ROOT_DIR=ROOT/'workspace/sandbox'/args.profile
    HELPER=ROOT/('tools/dvd-test/'+args.profile.removeprefix('dvd-test-')+'/bin/DvdTestRunner.exe')
    if args.menu and args.profile=='dvd-test-v1':raise SystemExit('DVD menu preview needs an integrated test bed')
    stopped()
    launcher.NATIVE_PROFILES[PROFILE]='workspace/sandbox/'+args.profile
    if PROFILE not in launcher.PROFILES:launcher.PROFILES=(*launcher.PROFILES,PROFILE)
    try:launcher.validate(PROFILE)
    except SystemExit as e:
        if str(e)!='A scheduled task must be scrubbed before launch':raise
        if args.check:print('NOTE: menu tasks would be scrubbed at launch')
        else:launcher.scrub_download_tasks(PROFILE)
    config=configparser.ConfigParser(strict=False);config.read(ROOT_DIR/'user/Config/Dolphin.ini',encoding='utf-8-sig')
    if config['Core'].getboolean('EnableWiiLink',fallback=False):raise SystemExit('Unexpected URL settings')
    if args.profile in ('dvd-test-v2','dvd-test-v3'):
        record=json.loads((ROOT_DIR/'test-bed-manifest.json').read_text(encoding='utf-8'));disc=ROOT_DIR/'disc/dvd-insertion.iso'
        if Path(config['Core'].get('DefaultISO','')).resolve()!=disc.resolve()or sha256(disc)!=record['insertion_fixture_sha256']:raise SystemExit('Unverified DVD insertion fixture')
        if sha256(ROOT_DIR/'Dolphin-x64/Dolphin.exe')!=record['runtime_sha256']or record['runtime_sha256']!=json.loads((ROOT/'configs/gc-fst-runtime.lock.json').read_text())['output_sha256']:raise SystemExit('DVD preview runtime differs')
        if sha256(HELPER)!=record['helper_sha256']:raise SystemExit('DVD preview helper differs')
        from kwce.channels import load_library
        from kwce.channel_validation import verify_installed_title
        lib=load_library();wad=ROOT/f'workspace/channels/dvd-player/wad-v{record["wad"]}/dvd-player.wad'
        if sha256(wad)!=record['wad_sha256']:raise SystemExit('DVD channel candidate differs')
        if args.profile=='dvd-test-v3':
            if not record.get('channel_independent'):raise SystemExit('Missing native test marker')
            for p in ('title/00010001/4b445644','ticket/00010001/4b445644.tik'):
                if (ROOT_DIR/'user/Wii'/p).exists():raise SystemExit('KDVD must be absent in native test')
            native=record['native_hook'];module=ROOT_DIR/'sd-sync/kwce/dvd'/('boot.ash' if 'module_sha256' in native else 'boot.dol')
            if sha256(module)!=native.get('module_sha256',native['player_sha256']):raise SystemExit('Native module differs')
            if 'banner_sha256' in native and sha256(ROOT_DIR/'sd-sync/kwce/dvd/menu.arc')!=native['banner_sha256']:raise SystemExit('Native banner differs')
            if 'icon_sha256' in native and sha256(ROOT_DIR/'sd-sync/kwce/dvd/icon.arc')!=native['icon_sha256']:raise SystemExit('Native icon differs')
        else:
            title=lib.title.Title();title.load_wad(wad.read_bytes());verify_installed_title(ROOT_DIR/'user/Wii',title.tmd.title_id,title.tmd.dump())
        content=ROOT_DIR/'user/Wii/title/00000001/00000002/content';tmd=(content/'title.tmd').read_bytes();found={}
        import struct
        for i in range(int.from_bytes(tmd[0x1de:0x1e0],'big')):
            cid,index=struct.unpack_from('>IH',tmd,0x1e4+36*i)
            if str(index)in record['system_menu_contents']:found[str(index)]=sha256(content/f'{cid:08x}.app')
        if found!=record['system_menu_contents']:raise SystemExit('DVD preview menu resources differ')
    elif config['Core'].get('DefaultISO'):raise SystemExit('Unexpected default disc')
    dol=ROOT_DIR/'sd-sync/apps/kwce-dvd/boot.dol'
    if not dol.exists()or not HELPER.exists():raise SystemExit('Run prepare_dvd_test.py --build <N> first')
    content=ROOT_DIR/'sd-sync/kwce/dvd'
    active=content/'active-player.json'
    if active.exists():
        record=json.loads(active.read_text(encoding='utf-8'));source=ROOT/f'workspace/channels/dvd-player/build-v{record["revision"]}/build-manifest.json';build=json.loads(source.read_text(encoding='utf-8'))
        if record['sha256']!=build['boot_dol_sha256']or sha256(dol)!=record['sha256']or record['css_decryption']!=build['css_decryption']:raise SystemExit('DVD test player differs from selected build')
    home=content/'active-home.json'
    if home.exists():
        record=json.loads(home.read_text(encoding='utf-8'));source=ROOT/f'workspace/channels/dvd-player/home-ui-v{record["revision"]}/home-ui-manifest.json'
        if record['sha256']!=json.loads(source.read_text(encoding='utf-8'))['sha256']or sha256(content/'home.arc')!=record['sha256']:raise SystemExit('DVD HOME resource differs from selected build')
    media=ROOT_DIR/'sd-sync/kwce/dvd/current-media.json'
    if media.exists():
        record=json.loads(media.read_text(encoding='utf-8'));iso=media.with_name('test-disc.iso')
        if record.get('kind')not in('synthetic','user-provided')or iso.stat().st_size!=record['size']or sha256(iso)!=record['sha256']:raise SystemExit('DVD test image differs from its selected media record')
    if args.check:print('PASS: DVD test bed profile, helper and player DOL');return
    print('DVD 배너 시험: 합성 삽입 상태에서 디스크 채널을 선택하세요.' if args.menu else '준비된 DVD ISO를 시험용 SD에서 자동 재생합니다. Dolphin의 열기/디스크 교체는 사용하지 않습니다.',flush=True)
    run=1
    while(PRIVATE/f'dvd-test-run-{run}.log').exists():run+=1
    launcher.archive_run_log(ROOT_DIR/'user/Logs/dolphin.log',PRIVATE/f'dvd-test-before-run-{run}-dolphin.log')
    with(PRIVATE/f'dvd-test-run-{run}.log').open('x',encoding='utf-8')as log:
        env=launcher.proxy_environment()
        p=subprocess.Popen([str(HELPER),str(ROOT_DIR),'menu' if args.menu else 'dol'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    print('DVD player test started in capability-zero AppContainer; helper PID',p.pid)

if __name__=='__main__':main()

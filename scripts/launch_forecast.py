"""Explicit project user, non-authenticated Korean NAND, capability 0 only."""
import argparse,configparser,json,subprocess
from audit_sd import ROOT,sha256
from prepare_forecast import register
from forecast_profile import validate_channel,scrub_channel
import launch_dolphin as launcher

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--menu',action='store_true');ap.add_argument('--check',action='store_true');ap.add_argument('--cache-preview',action='store_true',help='offline public-cache diagnostic only; not service verification');ap.add_argument('--manual-capture',action='store_true',help='separate 4:3 historical capture profile only');ap.add_argument('--review',action='store_true',help='separate local final-review profile');ap.add_argument('--current',action='store_true',help='current independent Korean weather test profile');ap.add_argument('--preserved-check',action='store_true',help='read-only check of preserved v22; never boots it');args=ap.parse_args()
    # A preserved profile has a read-only catalog entry and cannot be booted.
    if args.preserved_check:
        if any((args.review,args.manual_capture,args.current,args.menu,args.cache_preview)):raise SystemExit('Preserved profile permits a read-only check only')
        args.check=True
    if not any((args.review,args.manual_capture,args.current,args.preserved_check))and(ROOT/'workspace/sandbox/forecast-v2/current-profile.json').exists():args.current=True
    if sum((args.review,args.manual_capture,args.current))>1:raise SystemExit('Choose one isolated profile')
    if args.menu and args.cache_preview and not(args.review or args.current):raise SystemExit('Cached menu requires a dedicated current/review profile')
    if args.manual_capture and(not args.cache_preview or args.menu):raise SystemExit('Manual capture requires cache-preview mode')
    if 'dolphin.exe' in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin first')
    register();profile='forecast-v1-user'
    if args.current:
        launcher.NATIVE_PROFILES[profile]='workspace/sandbox/forecast-v2'
        meta=json.loads((ROOT/launcher.NATIVE_PROFILES[profile]/'current-profile.json').read_text())
        if meta.get('purpose')!='localized-forecast-current-cache'or meta.get('real_emulator_network')is not False:raise SystemExit('Unexpected current test profile')
    if args.review:
        launcher.NATIVE_PROFILES[profile]='workspace/sandbox/forecast-review-v1'
        review=json.loads((ROOT/launcher.NATIVE_PROFILES[profile]/'review-profile.json').read_text())
        if review.get('purpose')!='isolated-local-weather-review'or review.get('real_time_weather')is not False:raise SystemExit('Unexpected review profile')
    if args.manual_capture:
        launcher.NATIVE_PROFILES[profile]='workspace/sandbox/forecast-manual-v1'
        capture=json.loads((ROOT/launcher.NATIVE_PROFILES[profile]/'capture-profile.json').read_text())
        if capture.get('purpose')!='historical-4:3-manual-capture'or capture.get('real_time_weather')is not False:raise SystemExit('Unexpected manual capture profile')
    user=launcher.user_path(profile);runtime=user.parent
    review_dl=None
    if args.review or args.current:
        from forecast_review_tasks import review_tasks
        review_dl=review_tasks(check=args.check,profile=runtime.name)
    cache_binding=None
    if args.review or args.manual_capture:
        cache_binding=json.loads((ROOT/'configs/forecast-cache-profiles.lock.json').read_text())['profiles'][runtime.name]
    if args.current:cache_binding=json.loads((runtime/'cache-snapshot.json').read_text())
    for p in runtime.rglob('*'):
        if p.is_symlink()or p.is_junction():raise SystemExit('Indirect channel runtime refused')
    if not args.check:scrub_channel()
    validate_channel()
    expected=json.loads((ROOT/'configs/gc-fst-runtime.lock.json').read_text())['output_sha256']
    if sha256(runtime/'Dolphin-x64/Dolphin.exe')!=expected:raise SystemExit('Channel runtime hash mismatch')
    scenario=None
    if args.cache_preview and args.review and(runtime/'active-scenario.json').exists():
        active_scenario=json.loads((runtime/'active-scenario.json').read_text())
        if active_scenario.get('feed')not in('local-feed-v1','local-feed-v2'):raise SystemExit('Unknown review feed')
        feed=ROOT/'workspace/channels/forecast'/active_scenario['feed'];mf=feed/'manifest.json'
        if feed.is_symlink()or feed.is_junction()or sha256(mf)!=active_scenario['manifest_sha256']:raise SystemExit('Review feed identity changed')
        manifest=json.loads(mf.read_text());scenario=manifest['scenarios'][active_scenario['scenario']]
        if manifest['source_binding']!=cache_binding:raise SystemExit('Review source differs')
    if args.cache_preview:
        from kwce.forecast_replay import patch_cache_replay
        from kwce.channel_vff import VFF
        from forecast_profile import public_forecast_task
        derived,record=patch_cache_replay((runtime/'Dolphin-x64/Dolphin.exe').read_bytes())
        if record!=json.loads((ROOT/'configs/forecast-replay-runtime.lock.json').read_text())or(runtime/'Dolphin-replay-x64/Dolphin.exe').read_bytes()!=derived:raise SystemExit('Offline replay runtime changed')
        dl=review_dl if review_dl is not None else(user/'Wii/shared2/wc24/nwc24dl.bin').read_bytes();vff=VFF((user/'Wii/title/00010002/48414645/data/wc24dl.vff').read_bytes())
        for i in [3,4]:
            entry=dl[2048+512*i:2560+512*i]
            if not public_forecast_task(entry)or int.from_bytes(entry[4:8],'big')&8:raise SystemExit('Replay only permits the two public Forecast tasks')
            url=entry[180:416].split(b'\0')[0];kind='forecast'if url.endswith(b'/forecast.bin')else'short'
            if entry[416:480].split(b'\0')[0]!=f'{i}.bin'.encode():raise SystemExit('Replay task filename changed')
            from kwce.forecast_cache import public_source
            raw=public_source(kind,cache_binding).read_bytes()
            payload=raw[320:];mode=runtime/'cache-mode.json'if args.current else ROOT/'workspace/channels/forecast/cache-mode.json'
            if kind=='forecast'and mode.exists()and json.loads(mode.read_text()).get('localized'):
                from kwce.forecast_data import localize_forecast
                from kwce.forecast_data import forecast_mapping;payload,_=localize_forecast(payload,forecast_mapping())
            if scenario is not None:
                from kwce.forecast_scenarios import fixture,public_city_key
                missing_key=None
                if active_scenario['scenario']=='missing-location':
                    from kwce.forecast_data import localize_forecast,forecast_mapping
                    original,_=localize_forecast(public_source('forecast',cache_binding).read_bytes()[320:],forecast_mapping())
                    missing_key=public_city_key(original)
                payload=fixture(payload,kind,active_scenario['scenario'],missing_key=missing_key)
                info=scenario['files'][kind]
                if info['file']!=f'{active_scenario["scenario"]}-{kind}.bin'or sha256(feed/info['file'])!=info['sha256']or(feed/info['file']).read_bytes()!=payload:raise SystemExit('Review fixture differs from reproducible source')
            try:cached=vff.read(f'{i}.bin')
            except KeyError:raise SystemExit('Review cache was cleared by a previous failed run; prepare the selected scenario again')from None
            if cached!=payload:raise SystemExit('Replay cache differs from reproducible local fixture')
    config=configparser.ConfigParser(strict=False);config.read(user/'Config/Dolphin.ini',encoding='utf-8-sig')
    from kwce.dolphin_fst import inspect_fst
    inspect_fst((user/'Wii/fst.bin').read_bytes())
    if (user/'Wii/fst.bin.xxx').exists():raise SystemExit('Pending channel FST transaction requires diagnosis')
    if config['Core'].get('DefaultISO','')not in ['',str(runtime/'disc/GALJ01.iso')]:raise SystemExit('Channel default disc is outside its staged project copy')
    if args.cache_preview:
        import datetime
        from kwce.forecast_cache import inspect_public_download,public_source,valid_at
        instant=datetime.datetime.now(datetime.timezone.utc)
        if config['Core'].getboolean('EnableCustomRTC',fallback=False):instant=datetime.datetime.fromtimestamp(config['Core'].getint('CustomRTCValue'),datetime.timezone.utc)
        if scenario is not None:
            if int(instant.timestamp())!=scenario['rtc']:raise SystemExit('Review clock differs from selected fixture')
            print('Review fixture:',active_scenario['scenario'],'historical/synthetic; no live weather claim')
        else:
            for kind in ['forecast','short']:
                if not valid_at(inspect_public_download(public_source(kind,cache_binding).read_bytes(),kind),instant):raise SystemExit('Public weather cache expired: refresh_public_forecast.py, then seed_forecast_cache.py with a new attempt number')
    if config['Core'].get('OverrideRegionSettings','False').lower()!='true':raise SystemExit('Channel must preserve Korean runtime language and country')
    for key in ['WiiSDCard','WiiSDCardAllowWrites','WiiSDCardEnableFolderSync']:
        if config['Core'].get(key,'False').lower()!='false':raise SystemExit('Channel SD access refused')
    for key in ['SerialPort1','SerialPort2']:
        if config['Core'].get(key,'255')!='255':raise SystemExit('GC network device refused')
    for section in config.sections():
        for key,value in config[section].items():
            if value.strip()and(key.endswith(('path','pathoverride'))or key in ['nandroot','dump','load']):
                if not __import__('pathlib').Path(value).resolve().is_relative_to(user.resolve()):raise SystemExit('Channel outside path refused')
    from kwce.channels import load_library
    active=runtime/'active-build.json'if args.manual_capture or args.review or args.current else ROOT/'workspace/channels/forecast/active-build.json'
    revision=json.loads(active.read_text())['revision']if active.exists()else 1
    if not isinstance(revision,int)or revision<1 or revision>1000:raise SystemExit('Invalid active channel build')
    title=load_library().title.Title();wad=ROOT/f'workspace/channels/forecast/build-v{revision}/forecast-ko-personal-test.wad'
    meta=json.loads(wad.with_name('build-manifest.json').read_text(encoding='utf-8'))
    if sha256(wad)!=meta['wad_sha256']:raise SystemExit('Forecast build changed')
    title.load_wad(wad.read_bytes())
    from kwce.channel_validation import verify_installed_title
    verify_installed_title(user/'Wii','0001000248414645',title.tmd.dump())
    # Existing GC menu and BC/MIOS contents must remain byte-identical to v6.
    base=ROOT/'workspace/sandbox/gc-v6/user/Wii/title/00000001'
    for directory in ['00000002','00000100','00000101']:
        for p in (base/directory/'content').glob('*'):
            if p.is_file()and sha256(p)!=sha256(user/'Wii/title/00000001'/directory/'content'/p.name):raise SystemExit('Existing system title changed')
    bindir=ROOT/('tools/channel-sandbox/forecast-v2/bin'if args.current else'tools/channel-sandbox/review-v2/bin'if args.review else 'tools/channel-sandbox/manual-v1/bin'if args.manual_capture else 'tools/channel-sandbox/v1/bin');manifest=json.loads((bindir/'helper-build.json').read_text())
    if args.current and(manifest.get('capability_count')!=0 or manifest.get('current_only')is not True):raise SystemExit('Current helper policy differs')
    if args.review and(manifest.get('capability_count')!=0 or manifest.get('review_only')is not True):raise SystemExit('Review helper policy differs')
    if args.manual_capture and(manifest.get('capability_count')!=0 or manifest.get('capture_only')is not True):raise SystemExit('Capture helper policy differs')
    for row in manifest['files']:
        if sha256(ROOT/row['path'])!=row['sha256']:raise SystemExit('Channel helper hash mismatch')
    probe=next(r for r in manifest['files']if r['path']=='workspace/sandbox/forecast-v1/NetProbe.exe')
    if sha256(runtime/'NetProbe.exe')!=probe['sha256']:raise SystemExit('Channel profile probe hash mismatch')
    env=launcher.proxy_environment()
    if args.manual_capture:print('Historical 4:3 manual capture only; original Forecast profile and normal clock unchanged')
    if args.check:print('PASS: Korean non-authenticated channel profile, system titles, runtime and helper');return
    mode='menu-preview'if args.menu and args.cache_preview else'menu'if args.menu else'forecast-preview'if args.cache_preview else'forecast'
    # A long-lived helper must not inherit a caller's captured stdout pipe:
    # subprocess.run(..., capture_output=True) would otherwise wait for the
    # emulator to exit even after this launcher returned.
    logs=ROOT/'workspace/private/forecast-helper-runs';logs.mkdir(parents=True,exist_ok=True)
    number=1
    while(logs/f'run-{number}.log').exists():number+=1
    with(logs/f'run-{number}.log').open('xb')as stream:
        p=subprocess.Popen([str(bindir/'AppContainerRunner.exe'),str(runtime),mode],cwd=ROOT,env=env,
            stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,close_fds=True,
            creationflags=subprocess.CREATE_NO_WINDOW)
    print('Forecast capability 0 AppContainer started; mode',mode,'helper PID',p.pid)

if __name__=='__main__':main()

"""Launch only the pinned, isolated Food translation experiment.

--check performs the capability-0 static validation (pinned artifacts, Korean
locale, sanitized WC24/SD, synthetic feed, installed title, preserved system
contents) WITHOUT starting Dolphin. The lead runs the channel without --check.
--menu boots the profile's Korean Wii Menu instead of the channel (to see the
Food icon/banner); it is refused unless the System Menu files were compared
with the pinned Korean reference. `--menu --check` validates that path only.
"""
import argparse, configparser, json, subprocess, sys
from pathlib import Path
from audit_sd import ROOT, PRIVATE, sha256
from prepare_channel_access import stopped
from prepare_food_test import register, PROFILE, TITLE, BASE, HELPER
import launch_dolphin as launcher
from kwce.channels import load_library
from kwce.channel_validation import verify_installed_title


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--menu', action='store_true', help='start the verified Korean Wii Menu of the Food profile')
    parser.add_argument('--wait', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(); stopped(); register()
    lock = json.loads((ROOT / 'configs/food-runtime.lock.json').read_text())
    if lock['profile'] != PROFILE or lock['title_id'] != TITLE or lock['capability_count'] != 0 or lock['external_network_allowed']:
        raise ValueError('Food scope differs')
    for row in lock['files']:
        if sha256(ROOT / row['path']) != row['sha256']:
            raise ValueError('Pinned Food artifact differs: ' + row['path'])
    helper = ROOT / lock.get('helper', HELPER.relative_to(ROOT).as_posix())
    if not helper.resolve().is_relative_to((ROOT / 'tools/food-sandbox').resolve()):
        raise ValueError('Food helper outside tools/food-sandbox')
    for exe in ('FoodRunner.exe', 'FoodServer.exe'):
        if (helper / exe).relative_to(ROOT).as_posix() not in {row['path'] for row in lock['files']}:
            raise ValueError('Food helper is not pinned in the runtime lock: ' + exe)
    feed = BASE / 'local-feed'; fixture = json.loads((feed / 'fixture-manifest.json').read_text(encoding='utf-8'))
    if not fixture.get('local_only') or not fixture.get('synthetic'):
        raise ValueError('Food fixture scope differs')
    # Browse-only guarantee: no order/cart/auth action may have a served file.
    for action in fixture['blocked_actions']:
        if list((feed / 'nwapi').glob(action + '*.xml')):
            raise ValueError('Food fixture serves a blocked action: ' + action)
    for name in fixture['files']:
        p = feed / name
        if '..' in name or not p.is_file():
            raise ValueError('Food fixture payload missing: ' + name)
        if 'sha256' in fixture and sha256(p) != fixture['sha256'].get(name):
            raise ValueError('Food fixture payload differs from its manifest: ' + name)
    for p in BASE.rglob('*'):
        if p.is_symlink() or p.is_junction():
            raise ValueError('Indirect Food path')
    if not args.check:
        launcher.scrub_download_tasks(PROFILE)
    launcher.validate(PROFILE)
    cfg = configparser.ConfigParser(strict=False); cfg.read(BASE / 'user/Config/Dolphin.ini', encoding='utf-8-sig')
    if cfg['Core'].get('DefaultISO') or cfg['Core'].getboolean('EnableWiiLink'):
        raise ValueError('Unexpected Food boot settings')
    for key in ['WiiSDCard', 'WiiSDCardEnableFolderSync', 'WiiSDCardAllowWrites']:
        if cfg['Core'].getboolean(key, fallback=False):
            raise ValueError('Food SD access refused')
    for section in cfg.sections():
        for key, value in cfg[section].items():
            if (key.lower().endswith(('path', 'pathoverride')) or key.lower() in ('nandroot', 'dump', 'load')) and value.strip():
                if not Path(value).resolve().is_relative_to((BASE / 'user').resolve()):
                    raise ValueError('Food outside profile path')
    active = json.loads((ROOT / 'workspace/channels/food/active-build.json').read_text())
    revision, variant = active['revision'], active.get('variant')   # variant: WiiLink edition test build
    folder = f'{variant}-build-v{revision}' if variant else f'build-v{revision}'
    wad = ROOT / f'workspace/channels/food/{folder}/food-ko-local-test.wad'
    if sha256(wad) != lock['builds'].get(f'{variant}-{revision}' if variant else str(revision)):
        raise ValueError('Unapproved Food build')
    title = load_library().title.Title(); title.load_wad(wad.read_bytes())
    verify_installed_title(BASE / 'user/Wii', TITLE, title.tmd.dump())
    pd = lock.get('personal_data'); pd_note = 'no SPD/pd.dat seeded'
    if pd:
        from kwce import personal_data_format as fmt
        from kwce import food_personal_data as fpd
        spd = fpd.PD_CHANNEL / f"build-v{pd['spd_revision']}/personal-data-ko-local-test.wad"
        if sha256(spd) != pd['spd_wad_sha256']:
            raise ValueError('Food SPD build differs from lock')
        spd_title = load_library().title.Title(); spd_title.load_wad(spd.read_bytes())
        verify_installed_title(BASE / 'user/Wii', fpd.SPD_TITLE, spd_title.tmd.dump())
        target = BASE / 'user/Wii' / fpd.PD_PATH.lstrip('/')
        if pd.get('pd_installed'):
            if not target.is_file() or sha256(target) != pd['pd_sha256']:
                raise ValueError('Food fictional pd.dat differs from lock')
            fmt.check(fmt.decrypt(target.read_bytes(), fmt.DOLPHIN_DEFAULT_DEVICE_ID))
            pd_note = f"Korean SPD v{pd['spd_title_version']} + fictional pd.dat ({pd['pd_variant']})"
        else:
            if target.exists():
                raise ValueError('Unexpected pd.dat in Food profile')
            pd_note = f"Korean SPD v{pd['spd_title_version']}, no pd.dat"
    reference = ROOT / 'workspace/sandbox/votes-test-v1/user/Wii/title/00000001'
    compared = {}
    for name in ['00000002', '00000100', '00000101']:
        folder = reference / name / 'content'
        if folder.exists():
            for p in folder.glob('*'):
                if p.is_file() and sha256(p) != sha256(BASE / 'user/Wii/title/00000001' / name / 'content' / p.name):
                    raise ValueError('Food system contents changed')
                compared[name] = compared.get(name, 0) + p.is_file()
    if args.menu:
        # Booting the Wii Menu (--nand_title 0000000100000002) is safe only when the profile's System Menu was
        # actually compared with the pinned Korean reference, so a missing reference cannot pass silently.
        menu_tmd = BASE / 'user/Wii/title/00000001/00000002/content/title.tmd'
        if not menu_tmd.is_file() or not compared.get('00000002'):
            raise ValueError('Food Wii Menu start refused: System Menu not verified against the Korean reference')
    if args.check:
        mode = (' Wii Menu start verified (%d System Menu files match the reference);' % compared['00000002']) if args.menu else ''
        print('PASS: Food 10 contents, Korean locale, sanitized WC24/SD, pinned runtime/helper '
              + helper.parent.name + ', browse-only synthetic feed, preserved system;' + mode + ' ' + pd_note); return
    env = launcher.proxy_environment(); env['no_proxy'] += ',127.0.0.2'
    if not args.wait:
        controller = 1
        while (PRIVATE / f'food-controller-{controller}.log').exists():
            controller += 1
        command = [sys.executable, str(Path(__file__).resolve()), '--wait'] + (['--menu'] if args.menu else [])
        with (PRIVATE / f'food-controller-{controller}.log').open('x') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        print('Food isolated local experiment controller started; PID', process.pid); return
    number = 1
    while (PRIVATE / f'food-run-{number}.log').exists():
        number += 1
    with (PRIVATE / f'food-run-{number}.log').open('x') as log:
        process = subprocess.Popen([str(helper / 'FoodRunner.exe'), str(BASE), 'menu' if args.menu else 'channel', TITLE],
                                   cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        code = process.wait()
    launcher.scrub_download_tasks(PROFILE)
    if code:
        raise SystemExit('Food experiment ended with a helper error; private diagnostics preserved')
    print('Food experiment stopped; local scheduled tasks normalized')


if __name__ == '__main__':
    main()

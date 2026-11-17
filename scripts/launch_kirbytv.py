"""Launch only the pinned, isolated Kirby TV translation experiment.

--check validates the sandbox scope, pinned runtime/helper, Korean locale,
sanitized WC24, the local feed payload and preserved system contents without
starting Dolphin. Without --check it starts the capability-zero controller.
"""
import argparse
import configparser
import json
import subprocess
import sys
from pathlib import Path
from audit_sd import ROOT, PRIVATE, sha256
from prepare_channel_access import stopped
from prepare_kirbytv_test import register, PROFILE, TITLE, BASE, HELPER
import launch_dolphin as launcher
from kwce.channels import load_library
from kwce.channel_validation import verify_installed_title


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--wait', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    stopped()
    register()
    lock = json.loads((ROOT / 'configs/kirbytv-runtime.lock.json').read_text())
    if lock['profile'] != PROFILE or lock['title_id'] != TITLE or lock['capability_count'] != 0 or lock['external_network_allowed']:
        raise ValueError('Kirby TV scope differs')
    for row in lock['files']:
        if sha256(ROOT / row['path']) != row['sha256']:
            raise ValueError('Pinned Kirby TV artifact differs: ' + row['path'])
    feed = BASE / 'local-feed'
    fixture = json.loads((feed / 'fixture-manifest.json').read_text())
    if not fixture.get('local_only') or not fixture.get('synthetic'):
        raise ValueError('Kirby TV fixture scope differs')
    routes = (feed / 'routes.tsv').read_text()
    allowed_routes = {'GET /kctv2/xml/gb_config_en.xml\tgb_config_en.xml', 'GET /kctv2/test/sample.mo\tsample.mo'}
    if set(line for line in routes.splitlines() if line.strip()) - allowed_routes:
        raise ValueError('Kirby TV routes exceed the synthetic feed')
    for row in fixture['files']:
        p = feed / row['path']
        if Path(row['path']).name != row['path'] or not p.is_file() or sha256(p) != row['sha256']:
            raise ValueError('Kirby TV fixture payload differs')
    for p in BASE.rglob('*'):
        if p.is_symlink() or p.is_junction():
            raise ValueError('Indirect Kirby TV path')
    if not args.check:
        launcher.scrub_download_tasks(PROFILE)
    launcher.validate(PROFILE)
    cfg = configparser.ConfigParser(strict=False)
    cfg.read(BASE / 'user/Config/Dolphin.ini', encoding='utf-8-sig')
    if cfg['Core'].get('DefaultISO') or cfg['Core'].getboolean('EnableWiiLink'):
        raise ValueError('Unexpected Kirby TV boot settings')
    for key in ['WiiSDCard', 'WiiSDCardEnableFolderSync', 'WiiSDCardAllowWrites']:
        if cfg['Core'].getboolean(key, fallback=False):
            raise ValueError('Kirby TV SD access refused')
    for section in cfg.sections():
        for key, value in cfg[section].items():
            if (key.lower().endswith(('path', 'pathoverride')) or key.lower() in ('nandroot', 'dump', 'load')) and value.strip():
                if not Path(value).resolve().is_relative_to((BASE / 'user').resolve()):
                    raise ValueError('Kirby TV outside profile path')
    revision = json.loads((ROOT / 'workspace/channels/kirbytv/active-build.json').read_text())['revision']
    wad = ROOT / f'workspace/channels/kirbytv/build-v{revision}/kirbytv-ko-local-test.wad'
    if sha256(wad) != lock['builds'].get(str(revision)):
        raise ValueError('Unapproved Kirby TV build')
    title = load_library().title.Title()
    title.load_wad(wad.read_bytes())
    verify_installed_title(BASE / 'user/Wii', TITLE, title.tmd.dump())
    reference = ROOT / 'workspace/sandbox/votes-test-v1/user/Wii/title/00000001'
    for name in ['00000002', '00000100', '00000101']:
        for p in (reference / name / 'content').glob('*'):
            if p.is_file() and sha256(p) != sha256(BASE / 'user/Wii/title/00000001' / name / 'content' / p.name):
                raise ValueError('Kirby TV system contents changed')
    if args.check:
        print('PASS: Kirby TV 13 contents, Korean locale, sanitized WC24, pinned runtime/helper, synthetic local feed and preserved system')
        return
    number = 1
    while (PRIVATE / f'kirbytv-run-{number}.log').exists():
        number += 1
    env = launcher.proxy_environment()
    env['no_proxy'] += ',127.0.0.2'
    if not args.wait:
        controller = 1
        while (PRIVATE / f'kirbytv-controller-{controller}.log').exists():
            controller += 1
        command = [sys.executable, str(Path(__file__).resolve()), '--wait']
        with (PRIVATE / f'kirbytv-controller-{controller}.log').open('x') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        print('Kirby TV isolated local experiment controller started; PID', process.pid)
        return
    with (PRIVATE / f'kirbytv-run-{number}.log').open('x') as log:
        process = subprocess.Popen([str(HELPER / 'KirbyRunner.exe'), str(BASE), 'channel', TITLE], cwd=ROOT, env=env,
                                   stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        code = process.wait()
    launcher.scrub_download_tasks(PROFILE)
    if code:
        raise SystemExit('Kirby TV experiment ended with a helper error; private diagnostics preserved')
    print('Kirby TV experiment stopped; local scheduled tasks normalized')


if __name__ == '__main__':
    main()

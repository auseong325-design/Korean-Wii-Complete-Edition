"""Launch only the pinned, isolated Korean Internet Channel test (lead only).

  .venv\\Scripts\\python.exe scripts\\launch_internet.py --check    # verification, no Dolphin
  .venv\\Scripts\\python.exe scripts\\launch_internet.py [--menu]   # lead: start the experiment

The helper runs Dolphin and the page server (127.0.0.2:80) in one
zero-capability AppContainer; outside networks stay blocked.
"""
import argparse
import configparser
import json
import subprocess
import sys
from pathlib import Path

from audit_sd import ROOT, PRIVATE, sha256
from prepare_channel_access import stopped
from prepare_internet_test import register, PROFILE, TITLE, BASE, HELPER, LOCK, ACTIVE
import launch_dolphin as launcher
from kwce.channels import load_library
from kwce.channel_validation import verify_installed_title


def check():
    lock = json.loads(LOCK.read_text())
    if lock['profile'] != PROFILE or lock['title_id'] != TITLE or lock['capability_count'] != 0 or lock['external_network_allowed']:
        raise ValueError('Internet test scope differs')
    for row in lock['files']:
        if sha256(ROOT / row['path']) != row['sha256']:
            raise ValueError('Pinned Internet test artifact differs: ' + row['path'])
    feed = BASE / 'local-feed'
    fixture = json.loads((feed / 'fixture-manifest.json').read_text(encoding='utf-8'))
    if not (fixture.get('local_only') and fixture.get('synthetic') and fixture.get('fictional')) or fixture.get('accepts_orders_uploads_or_posts'):
        raise ValueError('Internet fixture scope differs')
    for row in fixture['files']:
        p = feed / row['path']
        if Path(row['path']).name != row['path'] or not p.is_file() or sha256(p) != row['sha256']:
            raise ValueError('Internet fixture payload differs')
    routes = (feed / 'routes.tsv').read_text(encoding='ascii').splitlines()
    if sha256(feed / 'routes.tsv') != fixture['routes_sha256'] or any(len(r.split('\t')) != 3 for r in routes):
        raise ValueError('Internet fixture routes differ')
    for p in BASE.rglob('*'):
        if p.is_symlink() or p.is_junction():
            raise ValueError('Indirect Internet test path')
    launcher.validate(PROFILE)
    cfg = configparser.ConfigParser(strict=False)
    cfg.read(BASE / 'user/Config/Dolphin.ini', encoding='utf-8-sig')
    if cfg['Core'].get('DefaultISO') or cfg['Core'].getboolean('EnableWiiLink'):
        raise ValueError('Unexpected Internet test boot settings')
    for key in ['WiiSDCard', 'WiiSDCardEnableFolderSync', 'WiiSDCardAllowWrites']:
        if cfg['Core'].getboolean(key, fallback=False):
            raise ValueError('Internet test SD access refused')
    for section in cfg.sections():
        for key, value in cfg[section].items():
            if (key.lower().endswith(('path', 'pathoverride')) or key.lower() in ('nandroot', 'dump', 'load')) and value.strip():
                if not Path(value).resolve().is_relative_to((BASE / 'user').resolve()):
                    raise ValueError('Internet test path outside the profile')
    revision = json.loads(ACTIVE.read_text())['revision']
    wad = ROOT / f'workspace/channels/internet/build-v{revision}/internet-ko-local-test.wad'
    if sha256(wad) != lock['builds'].get(str(revision)):
        raise ValueError('Unapproved Internet build')
    title = load_library().title.Title()
    title.load_wad(wad.read_bytes())
    count = verify_installed_title(BASE / 'user/Wii', TITLE, title.tmd.dump())
    reference = ROOT / 'workspace/sandbox/votes-test-v1/user/Wii/title/00000001'
    for name in ['00000002', '00000100', '00000101']:
        for p in (reference / name / 'content').glob('*'):
            if p.is_file() and sha256(p) != sha256(BASE / 'user/Wii/title/00000001' / name / 'content' / p.name):
                raise ValueError('Internet test system contents changed')
    helper = ROOT / lock.get('helper', HELPER.relative_to(ROOT).as_posix())
    pinned = {row['path'] for row in lock['files']}
    for exe in ('InternetRunner.exe', 'InternetServer.exe'):
        if (helper / exe).relative_to(ROOT).as_posix() not in pinned:
            raise ValueError('Internet helper is not pinned in the runtime lock: ' + exe)
    return revision, count, helper


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--menu', action='store_true')
    ap.add_argument('--wait', action='store_true', help=argparse.SUPPRESS)
    args = ap.parse_args()
    stopped()
    register()
    if not args.check:
        launcher.scrub_download_tasks(PROFILE)
    revision, count, helper = check()
    if args.check:
        print(f'PASS: Internet Channel build-v{revision} ({count} contents incl. shared fonts), Korean locale, sanitized WC24, '
              f'pinned runtime/helper {helper.relative_to(ROOT).as_posix()}, local page fixture and preserved system titles')
        return
    env = launcher.proxy_environment()
    env['no_proxy'] += ',127.0.0.2'
    if not args.wait:
        n = 1
        while (PRIVATE / f'internet-controller-{n}.log').exists():
            n += 1
        command = [sys.executable, str(Path(__file__).resolve()), '--wait'] + (['--menu'] if args.menu else [])
        with (PRIVATE / f'internet-controller-{n}.log').open('x') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        print('Internet Channel isolated local experiment controller started; PID', process.pid)
        return
    n = 1
    while (PRIVATE / f'internet-run-{n}.log').exists():
        n += 1
    with (PRIVATE / f'internet-run-{n}.log').open('x') as log:
        process = subprocess.Popen([str(helper / 'InternetRunner.exe'), str(BASE), 'menu' if args.menu else 'channel', TITLE],
                                   cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        code = process.wait()
    launcher.scrub_download_tasks(PROFILE)
    if code:
        raise SystemExit('Internet Channel experiment ended with a helper error; private diagnostics preserved')
    print('Internet Channel experiment stopped; local scheduled tasks normalized')


if __name__ == '__main__':
    main()

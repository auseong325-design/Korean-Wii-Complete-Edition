"""Launch (or --check) the isolated Wii Speak Channel boot test bed.

--check statically verifies the pinned runtime/helper, Korean locale, offline
WC24, SD/WiiLink off, panic dialogs visible, no USB/Bluetooth passthrough or
emulated microphone, the active approved build as installed, and preserved
system contents; it starts nothing. Without --check it starts the capability-0
controller (the lead's path): Dolphin boots the channel directly with
--nand_title, or the Korean Wii Menu with --menu. There is no local server.

  .venv\\Scripts\\python.exe scripts\\launch_wiispeak.py --check
  .venv\\Scripts\\python.exe scripts\\launch_wiispeak.py [--menu]   # lead only
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from audit_sd import ROOT, PRIVATE, sha256
from prepare_channel_access import stopped
from prepare_wiispeak_test import register, PROFILE, TITLE, BASE, HELPER, TEMPLATE, CHANNEL
import launch_dolphin as launcher
from kwce.channels import load_library
from kwce.channel_validation import verify_installed_title
from kwce import wiispeak_testbed as bed


def check():
    lock = json.loads((ROOT / bed.LOCK).read_text(encoding='utf-8'))
    if (lock['profile'] != PROFILE or lock['title_id'] != TITLE or lock['capability_count'] != 0
            or lock['external_network_allowed'] is not False or lock['microphone_allowed'] is not False or lock['local_server'] is not False):
        raise ValueError('Wii Speak bed scope differs')
    for row in lock['files']:
        if sha256(ROOT / row['path']) != row['sha256']:
            raise ValueError('Pinned Wii Speak bed artifact differs: ' + row['path'])
    if lock['builds'] != bed.pinned_builds(CHANNEL):
        raise ValueError('Wii Speak approved builds differ from their manifests')
    for p in BASE.rglob('*'):
        if p.is_symlink() or p.is_junction():
            raise ValueError('Indirect Wii Speak bed path')
    launcher.validate(PROFILE)
    bed.check_dolphin_ini(BASE / 'user/Config/Dolphin.ini', BASE / 'user')
    active = json.loads((ROOT / bed.ACTIVE).read_text(encoding='utf-8'))
    name = active['build']
    if name not in bed.BUILDS or lock['builds'][name] != active['wad_sha256']:
        raise ValueError('Unapproved Wii Speak build')
    wad = CHANNEL / bed.BUILDS[name]
    if sha256(wad) != active['wad_sha256']:
        raise ValueError('Wii Speak WAD differs from the active record')
    title = load_library().title.Title()
    title.load_wad(wad.read_bytes())
    count = verify_installed_title(BASE / 'user/Wii', TITLE, title.tmd.dump())
    for system in bed.SYSTEM_TITLES:
        folder = TEMPLATE / 'user/Wii/title/00000001' / system / 'content'
        if not folder.is_dir():
            raise ValueError('Template system title missing: ' + system)
        for p in folder.glob('*'):
            if p.is_file() and sha256(p) != sha256(BASE / 'user/Wii/title/00000001' / system / 'content' / p.name):
                raise ValueError('Wii Speak bed system contents changed')
    return name, count


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--menu', action='store_true', help='boot the Korean Wii Menu instead of the channel (same helper)')
    parser.add_argument('--wait', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    stopped()
    register()
    if not args.check:
        launcher.scrub_download_tasks(PROFILE)
    name, count = check()
    if args.check:
        print(f'PASS: Wii Speak bed {name} ({count} contents), Korean locale, offline WC24, SD/WiiLink off, panic dialogs on, '
              'no USB/Bluetooth passthrough or emulated microphone, pinned runtime/helper, preserved system')
        return
    env = launcher.proxy_environment()
    if not args.wait:
        controller = 1
        while (PRIVATE / f'wiispeak-controller-{controller}.log').exists():
            controller += 1
        command = [sys.executable, str(Path(__file__).resolve()), '--wait'] + (['--menu'] if args.menu else [])
        with (PRIVATE / f'wiispeak-controller-{controller}.log').open('x') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
        print(f'Wii Speak bed controller started ({name}' + (', Korean Wii Menu' if args.menu else '') + '); PID', process.pid)
        return
    number = 1
    while (PRIVATE / f'wiispeak-run-{number}.log').exists():
        number += 1
    with (PRIVATE / f'wiispeak-run-{number}.log').open('x') as log:
        process = subprocess.Popen([str(HELPER / (bed.RUNNER + '.exe')), str(BASE), 'menu' if args.menu else 'channel', TITLE],
                                   cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        code = process.wait()
    launcher.scrub_download_tasks(PROFILE)
    if code:
        raise SystemExit('Wii Speak bed run ended with a helper error; private diagnostics preserved')
    print('Wii Speak bed stopped; local scheduled tasks normalized')


if __name__ == '__main__':
    main()

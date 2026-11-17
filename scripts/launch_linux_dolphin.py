"""Prepare/check/launch only approved offline Linux experimental profiles."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kwce.linux_runtime import (BASE, PRIVATE, default_profile, isolation_probe, prepare, running,
                               runtime, sandbox, sources, stop, stopped, validate)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--prepare', choices=sorted(sources()))
    ap.add_argument('--with-gc-disc', action='store_true', help='copy only the privately cataloged staged GC test disc')
    ap.add_argument('--profile', default=default_profile())
    ap.add_argument('--menu', action='store_true')
    ap.add_argument('--gc-game', action='store_true', help='boot only the staged, catalog-verified GC test disc')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--stop', action='store_true')
    ap.add_argument('--list', action='store_true')
    args = ap.parse_args()
    if sys.platform != 'linux':
        raise ValueError('Use the original Windows launcher on Windows')
    if args.list:
        print('Sources: ' + ', '.join(sorted(sources())))
        print('Prepared: ' + ', '.join(p.parent.name for p in sorted(BASE.glob('*/profile.json'))))
        return
    if args.stop:
        stop(args.profile)
        return
    if args.with_gc_disc and args.prepare != 'menu':
        raise ValueError('--with-gc-disc requires --prepare menu')
    if args.gc_game and (args.menu or args.prepare):
        raise ValueError('--gc-game cannot be combined with --menu or --prepare')
    name = prepare(args.prepare, args.with_gc_disc) if args.prepare else args.profile
    if args.prepare and not args.check:
        return
    if running(name):
        raise ValueError('Selected Linux profile is already running')
    stopped()
    dest, meta, exe = validate(name, scrub_tasks=not args.check)
    if args.gc_game and (meta['source'] != 'menu' or not meta.get('disc_sha256')):
        raise ValueError('--gc-game requires a prepared menu profile with its verified staged disc')
    isolation_probe(dest)
    if args.check:
        print(f'PASS {name}: pinned Dolphin, Korean locale, synthetic credentials, offline profile')
        return
    # Batch mode creates the separate render window without the main/log UI.
    title = '0000000100000002' if args.menu else meta['title']
    boot = ['--exec', '/profile/disc/test.iso'] if args.gc_game else ['--nand_title', title]
    cmd = sandbox(dest, '/opt/dolphin/bin/dolphin-emu',
                  ['--batch', '--user', '/profile/user', *boot])
    PRIVATE.mkdir(parents=True, exist_ok=True)
    log = PRIVATE / f'{name}-startup.log'
    with log.open('wb') as output:
        child = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                 start_new_session=True)
    # bwrap execs Dolphin. Find its host PID by the exact isolated executable/user.
    for _ in range(100):
        if child.poll() is not None:
            raise ValueError('Dolphin exited during startup; diagnostics kept private')
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                command = proc.joinpath('cmdline').read_bytes().split(b'\0')
                if not os.path.samefile(proc / 'exe', exe) or not os.path.samefile(proc / 'root/profile', dest) or b'/profile/user' not in command:
                    continue
                ns = os.readlink(proc / 'ns/net')
                if ns == os.readlink('/proc/self/ns/net'):
                    continue
                row = {'pid': int(proc.name), 'start': proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19],
                       'executable': str(exe), 'net_namespace': ns}
                (dest / 'process.json').write_text(json.dumps(row))
                print(f'PASS launched {name}: isolated offline render window')
                return
            except (OSError, ValueError):
                pass
        time.sleep(.1)
    child.terminate()
    raise ValueError('Unable to verify isolated Dolphin identity')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        # Paths and emulator output remain in ignored private diagnostics.
        print(f'FAIL Linux runtime: {type(exc).__name__}: {exc}' if isinstance(exc, ValueError)
              else f'FAIL Linux runtime: {type(exc).__name__}; see private diagnostics')
        raise SystemExit(1)

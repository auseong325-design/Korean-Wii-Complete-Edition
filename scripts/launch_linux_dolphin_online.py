"""Online Linux Dolphin: a copy of the owner's console NAND with real network (WiiLink).

  --prepare ALIAS [--wiilink-wc24]   new workspace/online/ALIAS-vN from the imported console NAND
  --install PACKAGE --profile NAME   install the Korean channel WADs of kwce-rc-sd-vN
  --enable-wc24 --profile NAME       WiiConnect24 system setting on in the copy
  --uninstall TID... --profile NAME  remove titles from the copy to free space (512 MB NAND limit)
  --profile NAME --title TID | --menu   launch (render window only)
  --profile NAME --check | --stop | --list

Unplug the real console (or keep it offline) while an online profile runs: both carry the same
console identity. Offline profiles keep using scripts/launch_linux_dolphin.py.
"""
import argparse
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kwce import linux_online as online


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--prepare', metavar='ALIAS')
    ap.add_argument('--wiilink-wc24', action='store_true',
                    help="turn on Dolphin's own 'WiiConnect24 via WiiLink' (owner accepted the WiiLink terms)")
    ap.add_argument('--install', metavar='PACKAGE')
    ap.add_argument('--uninstall', nargs='+', metavar='TID', help='free space in the profile copy')
    ap.add_argument('--install-wad', nargs='+', metavar='PATH', help='project WADs under workspace/channels (testing)')
    ap.add_argument('--enable-wc24', action='store_true', help='WiiConnect24 system setting on (copy only)')
    ap.add_argument('--set-wiilink', choices=['on', 'off'], help='toggle WiiConnect24 via WiiLink in an existing profile')
    ap.add_argument('--pipe-input', action='store_true', help='exact pointer input through the profile FIFO')
    ap.add_argument('--console-mac', action='store_true', help='derive the console MAC from its Miis (Miis count as local)')
    ap.add_argument('--keep-locale', action='store_true', help='allow mismatched region settings and restore Korean SYSCONF locale')
    ap.add_argument('--fictional-address', action='store_true', help='fictional Korean pd.dat for the food channel')
    ap.add_argument('--profile')
    ap.add_argument('--title'); ap.add_argument('--menu', action='store_true')
    ap.add_argument('--check', action='store_true'); ap.add_argument('--stop', action='store_true')
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args()
    if sys.platform != 'linux':
        raise ValueError('Linux only')
    if a.list:
        print('Online profiles: ' + ', '.join(p.parent.name for p in sorted(online.BASE.glob('*/profile.json')))); return
    if a.prepare:
        online.prepare(a.prepare, a.wiilink_wc24); return
    if not a.profile:
        raise ValueError('--profile required')
    if a.stop:
        online.stop(a.profile); return
    if a.fictional_address:
        online.fictional_address(a.profile); return
    if a.keep_locale:
        online.keep_console_locale(a.profile); return
    if a.console_mac:
        online.set_console_mac(a.profile); return
    if a.pipe_input:
        online.use_pipe_input(a.profile); return
    if a.set_wiilink:
        online.set_wiilink(a.profile, a.set_wiilink == 'on'); return
    if a.enable_wc24:
        online.enable_wc24(a.profile); return
    if a.install_wad:
        if online.running():
            raise ValueError('Stop the online Dolphin first')
        online.install_wads(a.profile, a.install_wad); return
    if a.uninstall:
        if online.running():
            raise ValueError('Stop the online Dolphin first')
        online.uninstall(a.profile, a.uninstall); return
    if a.install:
        if online.running():
            raise ValueError('Stop the online Dolphin first')
        online.install(a.profile, a.install); return
    if a.check:
        dest, meta, _ = online.validate(a.profile); online.isolation_probe(dest)
        print(f'PASS online {a.profile}: pinned Dolphin, Korean locale, console NAND copy, WiiLink WC24 {"on" if meta["wiilink_kd"] else "off"}'); return
    if online.running():
        raise ValueError('An online Dolphin is already running')
    online.launch(a.profile, online.MENU if a.menu else (a.title or ''))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f'FAIL online runtime: {type(exc).__name__}: {exc}' if isinstance(exc, ValueError)
              else f'FAIL online runtime: {type(exc).__name__}; see private diagnostics')
        raise SystemExit(1)

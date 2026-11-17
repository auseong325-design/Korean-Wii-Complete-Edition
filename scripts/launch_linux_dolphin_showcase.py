"""Showcase recording profile (kwce/linux_showcase.py): online profile + pinned showcase Dolphin.

  --prepare [ALIAS]                    new workspace/online/showcase-vN (copy of the imported NAND, WiiLink on)
  --strip --profile NAME               keep only system/official Korean titles + Homebrew Channel
  --anonymize --profile NAME           Mii names -> symbols/digits, creators cleared, nickname -> Wii
  --sd PACKAGE --profile NAME          profile-local SD sync folder from workspace/hardware/PACKAGE
  --configure [--no-record] --profile NAME   pipe input, SD on, 1x frame/audio dumps
  --menu-resource --profile NAME       the console's KWCE GC menu resource (copy only)
  --stage-disc | --disc in|out --profile NAME   GameCube test disc
  --profile NAME --menu | --title TID | --dol apps/NAME/boot.dol | --stop | --check

Unplug the real console while a showcase profile runs: it carries the same console identity.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kwce import linux_online as online, linux_showcase as show


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--prepare', nargs='?', const='showcase', metavar='ALIAS')
    ap.add_argument('--strip', action='store_true'); ap.add_argument('--anonymize', action='store_true')
    ap.add_argument('--sd', metavar='PACKAGE'); ap.add_argument('--configure', action='store_true')
    ap.add_argument('--no-record', action='store_true')
    ap.add_argument('--stage-disc', action='store_true'); ap.add_argument('--menu-resource', action='store_true'); ap.add_argument('--disc', choices=['in', 'out'])
    ap.add_argument('--profile'); ap.add_argument('--title'); ap.add_argument('--dol', metavar='apps/NAME/boot.dol'); ap.add_argument('--menu', action='store_true')
    ap.add_argument('--stop', action='store_true'); ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    if sys.platform != 'linux':
        raise ValueError('Linux only')
    if a.prepare:
        show.prepare(a.prepare); return
    if not a.profile:
        raise ValueError('--profile required')
    if a.stop:
        online.stop(a.profile); return
    if a.strip:
        show.strip_titles(a.profile); return
    if a.anonymize:
        show.anonymize(a.profile); show.clear_birthdays(a.profile); return
    if a.sd:
        show.make_sd(a.profile, a.sd); return
    if a.menu_resource:
        show.console_menu_resource(a.profile); return
    if a.stage_disc:
        show.stage_disc(a.profile); return
    if a.disc:
        show.set_disc(a.profile, a.disc == 'in'); return
    if a.configure:
        show.configure(a.profile, record=not a.no_record); return
    if a.check:
        show.validate(a.profile); print(f'PASS showcase {a.profile} checks'); return
    if a.dol:
        show.launch(a.profile, dol=a.dol); return
    if a.menu or a.title:
        show.launch(a.profile, online.MENU if a.menu else a.title.lower()); return
    ap.error('nothing to do')


if __name__ == '__main__':
    main()

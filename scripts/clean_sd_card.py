"""Tidy the KWCE leftovers on the Wii SD card (explicit removable drive only).

User authorization 2026-10-30: unneeded / conflict-prone KWCE files on the real Wii SD card may be
removed. This tool still keeps every removed byte: each item is first COPIED to the PC
(workspace/private/sd-cleanup-N/, hash-verified file by file), and only then deleted from the card.
Anything not on the explicit KEEP-EVERYTHING-ELSE rule below (user games, saves, WADs, BootMii,
nand.bin, keys.bin, other homebrew) is never touched.

What it removes (all KWCE-made):
  apps/kwce-installer, apps/kwce-dvd-installer, apps/kwce-wiiroom-installer
        -> three older installer apps that would show next to the new one in the Homebrew Channel
  kwce/, kwce-wiiroom/, kwce-dvd-test/   -> data folders of those older apps (older channel builds)
  kwce/menu is kept on the PC as the only copy of the System Menu resource backup
  WAD/KWCE-remaining-v1                  -> older KWCE WADs that a WAD manager could install by mistake
  KWCE-*.json / KWCE-*.txt / package-manifest.json at the card root (manifests/READMEs of older packages)
Before deleting kwce/, the pre-KWCE restore records (kwce/state, kwce-wiiroom/state, kwce-dvd-test/state)
are merged into kwce-rc/state, the oldest record per channel winning, so "Restore" returns to the
state before the FIRST KWCE change instead of to an older KWCE build.

    python scripts/clean_sd_card.py --drive G:            # dry-run: prints the plan, writes nothing
    python scripts/clean_sd_card.py --drive G: --apply    # back up to the PC, verify, then delete
"""
import argparse
import ctypes
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

APPS = ('kwce-installer', 'kwce-dvd-installer', 'kwce-wiiroom-installer')
FOLDERS = ('kwce', 'kwce-wiiroom', 'kwce-dvd-test', 'WAD/KWCE-remaining-v1')
ROOT_FILES = re.compile(r'^(KWCE-[A-Za-z0-9-]+\.(json|txt)|package-manifest\.json)$')
KEEP_ROOT_FILES = {'KWCE-RC-README-ko.txt', 'KWCE-RC-package-manifest.json'}   # current package; deploy replaces them
STATE_FOLDERS = ('kwce/state', 'kwce-wiiroom/state', 'kwce-dvd-test/state')
RC_STATE = 'kwce-rc/state'


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def drive_ok(drive):
    letter = drive.rstrip('\\/')
    if not re.fullmatch(r'[D-Zd-z]:', letter):
        raise SystemExit('Explicit removable drive letter required')
    card = Path(letter + '\\')
    if card.resolve().is_relative_to(ROOT) or ctypes.windll.kernel32.GetDriveTypeW(str(card)) != 2:
        raise SystemExit(f'{letter} is not a removable drive')
    if not (card / 'apps').is_dir():
        raise SystemExit('Not the Wii SD card (apps/ missing)')
    return card


def targets(card):
    items = []
    for name in APPS:
        if (card / 'apps' / name).is_dir():
            items.append(('apps/' + name, card / 'apps' / name))
    for name in FOLDERS:
        if (card / name).is_dir():
            items.append((name, card / name))
    for p in sorted(card.iterdir()):
        if p.is_file() and ROOT_FILES.fullmatch(p.name) and p.name not in KEEP_ROOT_FILES:
            items.append((p.name, p))
    return items


def files_of(path):
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob('*') if p.is_file())


def parse_state(path):
    m = re.search(r'before=(-?\d+)\s+version=(-?\d+)', path.read_text(encoding='latin1'))
    return (int(m.group(1)), int(m.group(2))) if m else None


def pristine_records(card):
    """Oldest record per channel among the older folders (mtime decides)."""
    best = {}
    for folder in STATE_FOLDERS:
        d = card / folder
        if not d.is_dir():
            continue
        for p in d.glob('*.txt'):
            rec = parse_state(p)
            if rec and (p.stem not in best or p.stat().st_mtime < best[p.stem][0]):
                best[p.stem] = (p.stat().st_mtime, rec, p)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--drive', required=True)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    card = drive_ok(args.drive)

    items = targets(card)
    plan_files = {label: files_of(p) for label, p in items}
    total = sum(f.stat().st_size for fs in plan_files.values() for f in fs)
    print(f'card {args.drive}: {len(items)} item(s), {sum(len(v) for v in plan_files.values())} file(s), '
          f'{total / 2**20:.1f} MB to move to the PC and remove')
    for label, fs in plan_files.items():
        print(f'  {label:<34} {len(fs):>4} files {sum(f.stat().st_size for f in fs) / 2**20:>8.1f} MB')

    pristine = pristine_records(card)
    rc_state = card / RC_STATE
    merge = []
    for channel, (_, rec, path) in sorted(pristine.items()):
        current = parse_state(rc_state / f'{channel}.txt') if (rc_state / f'{channel}.txt').is_file() else None
        if current != rec:
            merge.append((channel, current, rec, path))
    print(f'  pristine restore records to merge into {RC_STATE}: {len(merge)}')
    for channel, current, rec, _ in merge:
        print(f'    {channel:<14} {current} -> {rec}')
    if not args.apply:
        print('DRY-RUN: nothing written. Re-run with --apply to back up, verify and delete.')
        return

    n = 1
    while (ROOT / f'workspace/private/sd-cleanup-{n}').exists():
        n += 1
    backup = ROOT / f'workspace/private/sd-cleanup-{n}'
    backup.mkdir(parents=True)
    free = shutil.disk_usage(backup).free
    if total * 2 > free:
        raise SystemExit('Not enough PC disk space for the backup')

    # 1) Back up everything that will be removed, verify every file by hash.
    manifest = []
    for label, p in items:
        for f in plan_files[label]:
            rel = f.relative_to(card)
            dest = backup / 'card' / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            if sha(dest) != sha(f):
                raise SystemExit(f'Backup hash mismatch: {rel}; nothing was deleted')
            manifest.append(dict(path=rel.as_posix(), bytes=f.stat().st_size, sha256=sha(dest)))
    # restore records that are replaced in kwce-rc/state are backed up too
    for channel, current, rec, _ in merge:
        cur = rc_state / f'{channel}.txt'
        if cur.is_file():
            dest = backup / 'card' / RC_STATE / cur.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cur, dest)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    print(f'backup verified: {len(manifest)} file(s) in {backup.relative_to(ROOT).as_posix()}')

    # 2) Merge the pristine restore records (tiny text files).
    rc_state.mkdir(parents=True, exist_ok=True)
    for channel, current, rec, path in merge:
        (rc_state / f'{channel}.txt').write_text(f'before={rec[0]} version={rec[1]}\n', encoding='ascii', newline='\n')
        print(f'  state {channel}: {current} -> {rec}')

    # 3) Delete from the card only what was just backed up.
    for label, p in items:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        print(f'  removed {label}')
    left = [label for label, p in items if p.exists()]
    if left:
        raise SystemExit('Not removed: ' + ', '.join(left))
    print(f'PASS: cleanup done; PC backup {backup.relative_to(ROOT).as_posix()} ({len(manifest)} files)')


if __name__ == '__main__':
    sys.exit(main())

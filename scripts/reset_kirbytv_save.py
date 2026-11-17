"""Reset or restore the Kirby TV channel save in the isolated kirbytv-test-v1 NAND.

The first-run guide (intro pages, late-start pages, notification opt-in) only
plays when the channel finds no saved state (DataController.pds_onLoadError ->
createDefaultPersistentData, firstRun=true). Without arguments this moves the
channel's data/ files (shrdobjs.vff = Flash SharedObjects, banner.bin = save
banner) into a new numbered workspace/private/kirbytv-save-backup-N after a
hash-checked copy. --restore N puts backup N back into an empty save folder.
Dolphin must be stopped. File contents are never printed. The real console,
SD card and other profiles are not touched.
"""
import argparse
import json
import shutil
from pathlib import Path
from audit_sd import PRIVATE, sha256
from prepare_channel_access import stopped
from prepare_kirbytv_test import BASE, TITLE

DATA = BASE / 'user/Wii/title' / TITLE[:8] / TITLE[8:] / 'data'
NAMES = ('shrdobjs.vff', 'banner.bin')


def _check_folder(data):
    if not data.is_dir():
        raise ValueError('Kirby TV save folder missing (is the channel installed?)')
    unexpected = sorted(p.name for p in data.iterdir() if p.name not in NAMES)
    if unexpected:
        raise ValueError('Unexpected entries in the Kirby TV save folder: ' + ', '.join(unexpected))


def move_save(data, private):
    """Back up and remove the save files; returns (backup folder or None, rows)."""
    _check_folder(data)
    present = [data / n for n in NAMES if (data / n).is_file()]
    if not present:
        return None, []
    number = 1
    while (private / f'kirbytv-save-backup-{number}').exists():
        number += 1
    backup = private / f'kirbytv-save-backup-{number}'
    backup.mkdir(parents=True)
    rows = []
    for path in present:
        digest = sha256(path)
        shutil.copy2(path, backup / path.name)
        if sha256(backup / path.name) != digest:
            raise ValueError('Save backup copy differs: ' + path.name)
        rows.append(dict(path=path.name, sha256=digest, bytes=path.stat().st_size))
    (backup / 'manifest.json').write_text(json.dumps(dict(
        title_id=TITLE, profile='kirbytv-test-v1', reason='first-run guide review', files=rows), indent=2))
    for path in present:
        path.unlink()
    return backup, rows


def restore_save(data, private, number):
    backup = private / f'kirbytv-save-backup-{number}'
    manifest = json.loads((backup / 'manifest.json').read_text())
    if manifest.get('title_id') != TITLE:
        raise ValueError('Backup belongs to another title')
    _check_folder(data)
    if any((data / n).exists() for n in NAMES):
        raise SystemExit('A current save exists; run the reset first (it backs that save up), then restore')
    for row in manifest['files']:
        if row['path'] not in NAMES or sha256(backup / row['path']) != row['sha256']:
            raise ValueError('Backup file differs from its manifest: ' + row['path'])
    for row in manifest['files']:
        shutil.copy2(backup / row['path'], data / row['path'])
        if sha256(data / row['path']) != row['sha256']:
            raise ValueError('Restored file differs: ' + row['path'])
    return manifest['files']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--restore', type=int, metavar='N', help='put workspace/private/kirbytv-save-backup-N back')
    args = parser.parse_args()
    stopped()
    if args.restore:
        rows = restore_save(DATA, PRIVATE, args.restore)
        print(f'Restored {len(rows)} Kirby TV save file(s) from kirbytv-save-backup-{args.restore}')
        return
    backup, rows = move_save(DATA, PRIVATE)
    if backup is None:
        print('Kirby TV save already empty; the next launch shows the first-run guide')
        return
    print(f'Moved {len(rows)} Kirby TV save file(s) to workspace/private/{Path(backup).name} (hash-checked); '
          'the next launch shows the first-run guide')


if __name__ == '__main__':
    main()

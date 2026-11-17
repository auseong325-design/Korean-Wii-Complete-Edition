"""Add one independently verified recovered VMC; never overwrite card/config.

Only invoked through deploy_to_sd.py with an explicit removable Linux mount.
The complete pre-existing small GCMCE SD contents are backed up privately first.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .gc_card import inspect_card

ROOT = Path(__file__).resolve().parents[1]
FOLDER = 'KWCE-GALJ-R-JPN'
RAW = f'MemoryCards/GC/{FOLDER}/{FOLDER}-1.raw'
INI = f'MemoryCards/GC/{FOLDER}/{FOLDER}.ini'
README = 'KWCE-GCMCE-RECOVERY-ko.txt'
CONFIG = '[Settings]\nMaxChannels=1\nCardSize=64\n\n'
PATHS = {RAW, INI, README}


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(4*1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def direct(path, root):
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Recovery path escaped approved root')
    for p in (path, *path.parents):
        if p.is_symlink():
            raise ValueError('Indirect recovery path refused')
        if p == root:
            break
    return path


def package_files(package):
    meta = json.loads((package/'package-manifest.json').read_text())
    if meta.get('kind') != 'gcmce-add-recovered-card-v1' or set(meta.get('files', {})) != PATHS:
        raise ValueError('Unapproved recovery package kind/paths')
    files = []
    for rel in sorted(PATHS):
        p = direct(package/rel, package)
        if sha(p) != meta['files'][rel]:
            raise ValueError('Recovery package hash mismatch')
        files.append((p, rel))
    if (package/INI).read_text() != CONFIG:
        raise ValueError('Recovery per-card config differs')
    card = inspect_card((package/RAW).read_bytes())
    if not (card['encoding'] == 1 and len(card['entries']) == 1 and
            card['allocated_blocks'] == 11 and card['free_blocks'] == 1008):
        raise ValueError('Recovered card layout differs from reviewed 11-block candidate')
    return files


def removable_mount(card):
    if sys.platform != 'linux' or not os.path.ismount(card):
        raise ValueError('Explicit removable Linux mount required')
    rows = json.loads(subprocess.check_output(
        ['lsblk', '--json', '--output', 'TYPE,RM,FSTYPE,MOUNTPOINTS'], text=True))
    matches = []
    def walk(items):
        for row in items:
            if any(p and Path(p).resolve() == card for p in row.get('mountpoints') or []):
                matches.append(row)
            walk(row.get('children') or [])
    walk(rows['blockdevices'])
    if len(matches) != 1 or not matches[0]['rm'] or matches[0]['fstype'] != 'vfat':
        raise ValueError('Recovery destination is not a unique removable FAT mount')
    if not (card/'.flippermce/settings.ini').is_file() or not (card/'MemoryCards/GC').is_dir():
        raise ValueError('GCMCE prerequisites missing')
    if (card/'apps/Priiloader/hacks_hash.ini').exists():
        raise ValueError('Wii SD refused as recovery destination')


def inventory(card):
    result = {}
    for p in sorted(card.rglob('*')):
        direct(p, card)
        if p.is_file():
            st = p.stat()
            result[p.relative_to(card).as_posix()] = dict(size=st.st_size,
                mtime_ns=st.st_mtime_ns, sha256=sha(p))
    return result


def deploy(package, drive, dry_run=False):
    package, card = Path(package).resolve(), Path(drive).resolve()
    if card == ROOT/'sd' or card.is_relative_to(ROOT/'sd'):
        raise ValueError('Original project SD is read-only')
    removable_mount(card)
    files = package_files(package)
    for _, rel in files:
        target = direct(card/rel, card)
        if target.exists() or target.with_name(target.name+'.kwce-new').exists():
            raise ValueError('Existing recovery target retained; use a new reviewed package')
    if dry_run:
        print('PASS GCMCE recovery plan: 3 additions, no replacements, settings/old VMCs untouched')
        return
    if os.statvfs(card).f_flag & os.ST_RDONLY:
        raise ValueError('SD is mounted read-only')
    if shutil.disk_usage(card).free < 32*1024*1024:
        raise ValueError('SD free space insufficient')
    before = inventory(card)
    if sum(x['size'] for x in before.values()) > 256*1024*1024:
        raise ValueError('Unexpected large GCMCE source; inspect before deploying')
    private = ROOT/'workspace/private/gc-card-investigation'
    private.mkdir(parents=True, exist_ok=True)
    n = 1
    while (private/f'sd-addition-{n}').exists():
        n += 1
    evidence = private/f'sd-addition-{n}'
    backup = evidence/'original-files'
    backup.mkdir(parents=True)
    for rel in before:
        dest = direct(backup/rel, backup)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(card/rel, dest)
        if sha(dest) != before[rel]['sha256']:
            raise ValueError('Complete pre-write GCMCE backup differs')
    (evidence/'before.json').write_text(json.dumps(before, indent=2))
    for src, rel in files:
        target = direct(card/rel, card)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation is intentional: recovery never replaces anything.
        with target.open('xb') as f:
            f.write(src.read_bytes())
            f.flush()
            os.fsync(f.fileno())
        if sha(target) != sha(src):
            raise ValueError('Recovery SD read-back differs')
    after = inventory(card)
    if any(after.get(k) != v for k, v in before.items()) or set(after)-set(before) != PATHS:
        raise ValueError('Unexpected SD change; all evidence retained privately')
    result = dict(additions=3, replacements=0, original_files_preserved=len(before),
        originals_missing=0, unexpected_changes=0, readback_verified=3,
        hardware_run=False, firmware_changed=False, global_settings_changed=False)
    (evidence/'after.json').write_text(json.dumps(after, indent=2))
    (evidence/'result.json').write_text(json.dumps(result, indent=2))
    print('PASS GCMCE: 3 additions verified; all original files unchanged; hardware untested')

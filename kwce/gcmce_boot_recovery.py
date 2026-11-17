"""Set a known empty Card1 to a recovery copy and disable last-card restore.

No format, firmware, GameID change or Wii file is included. Both replacements
require exact pre-reviewed input hashes and the entire source SD is backed up.
"""
import json
import configparser
import os
from pathlib import Path
import re
import shutil

from .gcmce_recovery import direct, inventory, removable_mount, sha
from .gc_card import inspect_card

ROOT = Path(__file__).resolve().parents[1]
RAW = 'MemoryCards/GC/Card1/Card1-1.raw'
SETTINGS = '.flippermce/settings.ini'
INI = 'MemoryCards/GC/Card1/Card1.ini'
README = 'KWCE-GCMCE-BOOT-ko.txt'
PATHS = {RAW, SETTINGS, INI, README}
CONFIG = '[ChannelName]\n1=DX recovered\n[Settings]\nMaxChannels=1\nCardSize=64\n\n'


def disable_restore(data):
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_string(data.decode('utf-8-sig'))
    if cfg.get('GC', 'CardRestore', fallback='') != 'ON':
        raise ValueError('GC CardRestore must be ON before the reviewed transition')
    pattern = rb'(?m)^(CardRestore[ \t]*=[ \t]*)ON([ \t]*\r?)$'
    if len(re.findall(pattern, data)) != 1:
        raise ValueError('Expected exactly one enabled CardRestore setting')
    return re.sub(pattern, rb'\1OFF\2', data)


def verify(package, card):
    meta = json.loads((package/'package-manifest.json').read_text())
    if meta.get('kind') != 'gcmce-empty-card1-recovery-v1' or set(meta.get('files', {})) != PATHS:
        raise ValueError('Unapproved fixed-start recovery package')
    if set(meta.get('expected_inputs', {})) != {RAW, SETTINGS}:
        raise ValueError('Missing exact replacement preconditions')
    for rel in PATHS:
        src = direct(package/rel, package)
        if sha(src) != meta['files'][rel]:
            raise ValueError('Fixed-start package hash mismatch')
        target = direct(card/rel, card)
        if target.with_name(target.name+'.kwce-new').exists():
            raise ValueError('Existing SD staging file retained')
    for rel in (RAW, SETTINGS):
        if sha(card/rel) != meta['expected_inputs'][rel]:
            raise ValueError('SD changed since review; refusing replacement')
    old_data = (card/RAW).read_bytes()
    old = inspect_card(old_data)
    if old['entries'] or old['allocated_blocks'] or old['free_blocks'] != 1019:
        raise ValueError('Only an empty, valid 1019-block Card1 may be replaced')
    blank = (bytes(8192), b'\xff'*8192)
    if any(old_data[i:i+8192] not in blank for i in range(5*8192, len(old_data), 8192)):
        raise ValueError('Card1 contains retained data; preserve it for investigation')
    recovered = inspect_card((package/RAW).read_bytes())
    if (recovered['encoding'] != 1 or len(recovered['entries']) != 1 or
            recovered['allocated_blocks'] != 11 or recovered['free_blocks'] != 1008):
        raise ValueError('Recovered Card1 differs from the reviewed layout')
    if (package/SETTINGS).read_bytes() != disable_restore((card/SETTINGS).read_bytes()):
        raise ValueError('Settings change is not limited to CardRestore ON to OFF')
    if (package/INI).read_text() != CONFIG:
        raise ValueError('Unexpected fixed-start per-card config')
    for rel in (INI, README):
        if (card/rel).exists():
            raise ValueError('Existing added target retained; review a new package')


def deploy(package, drive, dry_run=False):
    package, card = Path(package).resolve(), Path(drive).resolve()
    if card.is_relative_to(ROOT/'sd'):
        raise ValueError('Original project SD is read-only')
    removable_mount(card)
    verify(package, card)
    if dry_run:
        print('PASS fixed-start plan: 2 backed-up replacements + 2 additions; empty Card1 only')
        return
    if os.statvfs(card).f_flag & os.ST_RDONLY:
        raise ValueError('Fixed-start destination is read-only')
    if shutil.disk_usage(card).free < 32*1024*1024:
        raise ValueError('Insufficient SD free space')
    before = inventory(card)
    if sum(x['size'] for x in before.values()) > 256*1024*1024:
        raise ValueError('Unexpected large GCMCE SD; inspect before replacing')
    private = ROOT/'workspace/private/gc-card-investigation'
    n = 1
    while (private/f'sd-fixed-start-{n}').exists():
        n += 1
    evidence = private/f'sd-fixed-start-{n}'
    backup = evidence/'original-files'
    backup.mkdir(parents=True)
    for rel, info in before.items():
        dest = direct(backup/rel, backup)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(card/rel, dest)
        if sha(dest) != info['sha256']:
            raise ValueError('Complete pre-write backup differs')
    (evidence/'before.json').write_text(json.dumps(before, indent=2))
    if inventory(card) != before:
        raise ValueError('SD changed during backup; no writes performed')
    # Activate the startup preference last, after the complete VMC is durable.
    for rel in (RAW, INI, README, SETTINGS):
        src, target = package/rel, card/rel
        temp = target.with_name(target.name+'.kwce-new')
        with temp.open('xb') as f:
            f.write(src.read_bytes());f.flush();os.fsync(f.fileno())
        if sha(temp) != sha(src):
            raise ValueError('Staged replacement differs; original retained')
        os.replace(temp, target)
        if sha(target) != sha(src):
            raise ValueError('Fixed-start read-back differs')
    after = inventory(card)
    if (set(after)-set(before) != {INI, README} or set(before)-set(after) or
            any(after[k] != v for k, v in before.items() if k not in {RAW, SETTINGS})):
        raise ValueError('Unexpected SD change; evidence retained')
    result = dict(replacements=2, additions=2, readback_verified=4,
        original_files_backed_up=len(before), non_target_originals_unchanged=len(before)-2,
        missing=0, unplanned_changes=0, card_restore=False, gameid_changed=False,
        firmware_changed=False, wii_sd_changed=False, hardware_verified=False)
    (evidence/'after.json').write_text(json.dumps(after, indent=2))
    (evidence/'result.json').write_text(json.dumps(result, indent=2))
    print('PASS GCMCE fixed start: 2 backed-up replacements + 2 additions, 4 verified; others unchanged')

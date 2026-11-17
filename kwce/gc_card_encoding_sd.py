"""Deliver per-card read validation as Priiloader RAM hacks, never a menu WAD.

The old encoding section's name/order is kept for installed legacy tooling.
Its CARDInit format default is unchanged; the added VerifyID thunk accepts only
validated ANSI/SJIS headers. Every other section stays byte-identical.
"""
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

from .gc_card_encoding import patch_card_encodings
from .gc_native import patch_gc_native
from .gcmce_recovery import direct, inventory, sha
from .priiloader_hacks import hacks, _runs, _unique_hash, _words
from .priiloader_legacy import checked_ini, parse, apply_streaming

ROOT = Path(__file__).resolve().parents[1]
NAME = 'KWCE GC: Japanese memory card encoding'
DEFINITIONS = {
    'apps/Priiloader/hacks_hash.ini',
    'kwce-rc/priiloader/gc-only.ini',
    'kwce-rc/priiloader/gc-dvd.ini',
    'kwce-rc/priiloader/fragment-gc-only.ini',
    'kwce-rc/priiloader/fragment-gc-dvd.ini',
}
README = 'KWCE-GC-CARD-ENCODING-ko.txt'
PATHS = DEFINITIONS | {README}


def upgrade_definition(raw, menu):
    entries = parse(raw)
    target = [x for x in entries if x['name'] == NAME]
    if len(target) != 1:
        raise ValueError('Expected one existing GC encoding section')
    base = patch_gc_native(menu, japanese_cards=True, japanese_comments=True)[0]
    new, _ = patch_card_encodings(base)
    old_entry = hacks(menu)[1]
    expected_old = parse(checked_ini(menu, [old_entry], packed=True))[0]
    if target[0] != expected_old:
        raise ValueError('Existing encoding definition differs from the frozen SJIS-only patch')
    extra = [(_unique_hash(menu, a, (b-a)//4), _words(new, a, b))
             for a, b in _runs(base, new)]
    replacement = dict(name=NAME, pairs=old_entry['pairs'] + extra)
    section = checked_ini(menu, [replacement], packed=True)
    pattern = rb'(?m)^\[' + re.escape(NAME.encode('ascii')) + rb'\]\r\n.*?(?=^\[|\Z)'
    matches = list(re.finditer(pattern, raw, re.S))
    if len(matches) != 1:
        raise ValueError('Ambiguous original encoding block')
    match = matches[0]
    result = raw[:match.start()] + section + raw[match.end():]
    updated = parse(result)
    if [x['name'] for x in updated] != [x['name'] for x in entries]:
        raise ValueError('Hack section names/order changed')
    for before, after in zip(entries, updated):
        if before['name'] != NAME and before != after:
            raise ValueError('Unrelated hack modified')
    kw = lambda rows: [x for x in rows if x['name'].startswith(('KWCE GC:', 'KWCE DVD:'))]
    old_menu = apply_streaming(menu, kw(entries))
    expected = patch_card_encodings(old_menu)[0]
    if apply_streaming(menu, kw(updated)) != expected:
        raise ValueError('Legacy streaming result differs from the reviewed per-card patch')
    return result


def verify_package(package, card):
    meta = json.loads((package/'package-manifest.json').read_text())
    if (meta.get('kind') != 'gc-per-card-priiloader-v1' or set(meta.get('files', {})) != PATHS
            or set(meta.get('expected_inputs', {})) != DEFINITIONS):
        raise ValueError('Unapproved encoding package kind/paths')
    menu = (ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    for rel in PATHS:
        src = direct(package/rel, package)
        if sha(src) != meta['files'][rel]:
            raise ValueError('Encoding package hash mismatch')
        target = direct(card/rel, card)
        if target.with_name(target.name+'.kwce-new').exists():
            raise ValueError('Existing SD staging file retained')
        if rel in DEFINITIONS:
            if sha(target) != meta['expected_inputs'][rel]:
                raise ValueError('Priiloader definition changed since review')
            if src.read_bytes() != upgrade_definition(target.read_bytes(), menu):
                raise ValueError('Package changes more than the reviewed encoding section')
        elif target.exists():
            raise ValueError('Existing encoding instructions retained')


def wii_mount(card):
    if sys.platform != 'linux' or not os.path.ismount(card):
        raise ValueError('Explicit removable Linux Wii SD mount required')
    rows = json.loads(subprocess.check_output(
        ['lsblk', '--json', '--output', 'RM,FSTYPE,MOUNTPOINTS'], text=True))
    matches = []
    def walk(items):
        for row in items:
            if any(p and Path(p).resolve() == card for p in row.get('mountpoints') or []):
                matches.append(row)
            walk(row.get('children') or [])
    walk(rows['blockdevices'])
    if len(matches) != 1 or not matches[0]['rm'] or matches[0]['fstype'] != 'vfat':
        raise ValueError('Wii SD is not a unique removable FAT mount')
    if not (card/'apps/Priiloader/hacks_hash.ini').is_file() or not (card/'kwce-rc').is_dir():
        raise ValueError('Reviewed Wii SD prerequisites missing')
    if (card/'.flippermce/settings.ini').exists():
        raise ValueError('GCMCE SD refused as Priiloader destination')


def metadata_inventory(card):
    result = {}
    for p in sorted(card.rglob('*')):
        direct(p, card)
        if p.is_file():
            st = p.stat()
            result[p.relative_to(card).as_posix()] = dict(size=st.st_size, mtime_ns=st.st_mtime_ns)
    return result


def deploy(package, drive, dry_run=False):
    package, card = Path(package).resolve(), Path(drive).resolve()
    if card.is_relative_to(ROOT/'sd'):
        raise ValueError('Original project SD is read-only')
    wii_mount(card)
    verify_package(package, card)
    if dry_run:
        print('PASS GC encoding plan: 5 definition updates + 1 instruction file; Priiloader RAM only')
        return
    if os.statvfs(card).f_flag & os.ST_RDONLY:
        raise ValueError('Wii SD is mounted read-only')
    if shutil.disk_usage(card).free < 32*1024*1024:
        raise ValueError('Insufficient SD free space')
    before = inventory(card)
    private = ROOT/'workspace/private/gc-card-investigation'
    n = 1
    while (private/f'encoding-sd-{n}').exists():
        n += 1
    evidence = private/f'encoding-sd-{n}'
    backup = evidence/'original-definitions';backup.mkdir(parents=True)
    original_hashes = {}
    for rel in DEFINITIONS:
        dst = direct(backup/rel, backup);dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(card/rel, dst)
        original_hashes[rel] = sha(card/rel)
        if sha(dst) != original_hashes[rel]:
            raise ValueError('Priiloader SD backup differs; no changes made')
    (evidence/'before.json').write_text(json.dumps(before, indent=2))
    (evidence/'input-hashes.json').write_text(json.dumps(original_hashes, indent=2))
    if inventory(card) != before:
        raise ValueError('Wii SD changed during backup')
    # Future mode files first, currently active definition last.
    ordered = sorted(DEFINITIONS-{'apps/Priiloader/hacks_hash.ini'}) + [README, 'apps/Priiloader/hacks_hash.ini']
    for rel in ordered:
        src, target = package/rel, card/rel
        temp = target.with_name(target.name+'.kwce-new')
        with temp.open('xb') as f:
            f.write(src.read_bytes());f.flush();os.fsync(f.fileno())
        if sha(temp) != sha(src):
            raise ValueError('Staged definition differs; original target retained')
        os.replace(temp, target)
        if sha(target) != sha(src):
            raise ValueError('Priiloader SD read-back differs')
    after = inventory(card)
    if (set(after)-set(before) != {README} or set(before)-set(after) or
            any(after[k] != v for k, v in before.items() if k not in DEFINITIONS)):
        raise ValueError('Unexpected Wii SD change; evidence retained')
    result = dict(definitions_updated=5, instruction_files_added=1, readback_verified=6,
        definitions_backed_up=5, section_names_and_order_preserved=True,
        unrelated_hack_sections_unchanged=True, nand_written=False, ios_written=False,
        firmware_written=False, gcmce_card_changed=False, hardware_verified=False,
        missing=0, unplanned_changes=0)
    (evidence/'after.json').write_text(json.dumps(after, indent=2))
    (evidence/'result.json').write_text(json.dumps(result, indent=2))
    print('PASS GC encoding SD: 5 backed-up definitions + 1 addition, 6 verified; NAND untouched')

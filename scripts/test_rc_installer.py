"""Emulator test of the RC installer: version detection, delete/restore paths and reports.

Uses the existing Dolphin bed workspace/sandbox/hardware-test-v1 (scripts/prepare_hardware_test.py):
1. compiles a TEST-ONLY installer DOL (-DKWCE_TEST_SCRIPT: keys come from sd:/kwce-rc/test-keys.txt;
   never shipped in a package) and runs the forbidden-symbol gate on it;
2. stages known builds into the bed's emulated NAND and a header-only copy of an RC package on the
   bed's SD sync folder (each WAD cut right after its TMD, so detection reads the real TMDs while the
   SD image stays small);
3. predicts every channel's state in Python (kwce/rc_hardware.py), runs a scripted session through
   launch_hardware_test.py, stops Dolphin and compares the installer's own log with the prediction;
4. restores the bed: exactly the NAND files the test changed, the SD sync folder and the bed's DOL.

Evidence goes to workspace/private/rc-installer-test-N/. Dolphin's windows and logs are not read.
Dolphin's ES checks signatures, so installing the fakesigned WADs fails there with -2011 by design;
the install code path itself is the one RC1-RC3 used on the real console. Needs Dolphin stopped.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from audit_sd import ROOT, PRIVATE
from prepare_channel_access import stopped

sys.path.insert(0, str(ROOT))
from kwce import rc_hardware  # noqa: E402
from kwce.channels import load_library  # noqa: E402
from export_rc_hardware import compile_installer, SRC  # noqa: E402

BED = ROOT / 'workspace/sandbox/hardware-test-v1'
WII = BED / 'user/Wii'
SD = BED / 'sd-sync'
DOL = SD / 'apps/kwce-installer/boot.dol'
NAND_TREES = ('title/00010001', 'title/00010002', 'title/00010008',
              'ticket/00010001', 'ticket/00010002', 'ticket/00010008', 'shared1', 'sys')
REGION = {0: 'JPN', 1: 'USA', 2: 'EUR', 3: 'any', 4: 'KOR'}
AREA_REGION = {'JPN': 0, 'USA': 1, 'BRA': 1, 'LTN': 1, 'EUR': 2, 'AUS': 2, 'KOR': 4}
PY = str(ROOT / '.venv/Scripts/python.exe')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def snapshot():
    files, dirs = {}, set()
    for tree in NAND_TREES:
        base = WII / tree
        if not base.exists():
            continue
        dirs.add(tree)
        for p in base.rglob('*'):
            rel = p.relative_to(WII).as_posix()
            if p.is_dir():
                dirs.add(rel)
            else:
                files[rel] = sha(p)
    return files, dirs


def restore_nand(before, backup):
    files, dirs = snapshot()
    for rel in sorted(set(files) - set(before[0])):
        (WII / rel).unlink()
    for rel, digest in before[0].items():
        if files.get(rel) != digest:
            (WII / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup / rel, WII / rel)
    for rel in sorted(dirs - before[1], key=lambda r: -r.count('/')):
        p = WII / rel
        if p.is_dir() and not any(p.iterdir()):
            p.rmdir()
    return snapshot() == before


def bed_area():
    """AREA of the bed's (sanitized emulator) setting.txt; no other field is kept."""
    raw = (WII / 'title/00000001/00000002/data/setting.txt').read_bytes()[:1024]
    key, plain = 0x73B5DBFA, bytearray()
    for b in raw:
        plain.append(b ^ (key & 0xFF))
        key = ((key << 1) | (key >> 31)) & 0xFFFFFFFF
    m = re.search(rb'AREA=([A-Z]{1,7})', bytes(plain))
    plain[:] = bytes(len(plain))
    return m.group(1).decode() if m else ''


def head_of(path):
    with open(path, 'rb') as f:
        head = f.read(0x10000)
    h = [int.from_bytes(head[i:i + 4], 'big') for i in range(0, 32, 4)]
    a64 = lambda x: (x + 63) & ~63
    end = a64(h[0]) + a64(h[2]) + a64(h[3]) + a64(h[4]) + h[5]
    if end > len(head):
        raise ValueError(f'{path}: TMD beyond the first 64 KiB')
    return head[:end]


def parse_versions(raw):
    builds, marks = {}, set()
    for line in raw.decode('ascii').splitlines()[1:]:
        p = line.split('|')
        if p[0] == 'build':
            builds[(p[1], int(p[2], 16))] = (p[3], int(p[4]), p[5])
        elif p[0] == 'mark':
            marks.add((p[1], p[2]))
    return builds, marks


def predict(pkg, area, release):
    data = pkg / 'kwce-rc'
    chans = [l.split('|') for l in (data / 'packages.txt').read_text(encoding='ascii').splitlines()
             if l and not l.startswith('#')]
    builds, marks = parse_versions((data / 'versions.txt').read_bytes())
    want = AREA_REGION.get(area, -1)
    files, states = {}, {}
    editions = {}   # RC9+: channel id -> [(key, label, fingerprint)]
    if (data / 'editions.txt').is_file():
        for line in (data / 'editions.txt').read_text(encoding='ascii').splitlines():
            if line and not line.startswith('#'):
                ecid, key, label = line.split('|')
                ident = rc_hardware.tmd_identity(rc_hardware.read_wad_tmd(data / ecid / f'korean-{key}.wad'))
                editions.setdefault(ecid, []).append((key, label, ident[0]))
    for row in chans:
        cid, tid, _name, _exp, _gc = row[:5]
        k = data / cid / 'korean.wad'
        o = data / cid / 'original.wad'
        kid = rc_hardware.tmd_identity(rc_hardware.read_wad_tmd(k)) if k.exists() else None
        oid = rc_hardware.tmd_identity(rc_hardware.read_wad_tmd(o)) if o.exists() else None
        files[cid] = (kid, oid)
        tmdp = WII / 'title' / tid[:8] / tid[8:] / 'content/title.tmd'
        tmd = tmdp.read_bytes() if tmdp.exists() else None
        ident = rc_hardware.tmd_identity(tmd) if tmd else None
        if ident:
            boot = int.from_bytes(tmd[0x1E0:0x1E2], 'big')
            cid_boot = next((r[0:4].hex() for r in rc_hardware.tmd_records(tmd)
                             if int.from_bytes(r[4:6], 'big') == boot), None)
            if cid_boot is None or not (tmdp.parent / f'{cid_boot}.app').exists():
                ident = None          # a deleted channel keeps only its TMD
        if not ident or ident[1] != tid:
            states[cid] = ('not installed', None)
            continue
        fp, _, ver, reg = ident
        n_marks = sum((cid, r[16:24].hex()) in marks for r in rc_hardware.tmd_records(tmd))
        known = builds.get((cid, fp))
        ed = next((key for key, _label, efp in editions.get(cid, []) if efp == fp), None)
        if kid and fp == kid[0]:
            s = 'Korean, up to date'
        elif ed:
            s = f'Korean {ed[:10]}, latest'
        elif oid and fp == oid[0]:
            s = 'original'
        elif known and known[0] == 'O':
            s = 'original'
        elif known:
            if known[1] >= release:
                s = f'Korean, newer (RC{known[1]})'
            else:
                s = f'UPDATE: RC{known[1]} -> RC{release}' if known[1] > 0 else f'UPDATE: test build -> RC{release}'
        else:
            s = 'Korean, unlisted build' if n_marks else f'other version v{ver}'
        states[cid] = (s, dict(fp=fp, ver=ver, region=REGION.get(reg, '?'),
                               region_ok=None if want < 0 else (reg == 3 or reg == want)))
    return [c[0] for c in chans], files, states, editions


def parse_log(text):
    run = text[text.rfind('--- KWCE '):]
    files, scans = {}, []
    section = None
    for line in run.splitlines():
        if line.startswith('  Package files:'):
            section = 'files'
            continue
        m = re.match(r'  Channel scan \((.+)\):', line)
        if m:
            section = 'scan'
            scans.append((m.group(1), {}))
            continue
        if not line.startswith('    '):
            section = None
            continue
        if section == 'files':
            m = re.match(r'^\s{4}(\S+)\s+korean (\S+)\s+original (\S+)', line)
            if m:
                files[m.group(1)] = (m.group(2), m.group(3))
            m = re.match(r'^\s{4}(\S+)\s+edition (\S+) (\S+)$', line)
            if m:
                files[(m.group(1), m.group(2))] = m.group(3)
        elif section == 'scan':
            m = re.match(r'^\s{4}(\S+)\s+(.+?)\s+v(\d+) (\S+) fp ([0-9a-f]{16})(.*)$', line)
            if m:
                scans[-1][1][m.group(1)] = (m.group(2), int(m.group(5), 16), int(m.group(3)), m.group(4),
                                            'will not start' in m.group(6))
            else:
                m = re.match(r'^\s{4}(\S+)\s+(.+?)\s*$', line)
                if m:
                    scans[-1][1][m.group(1)] = (m.group(2), None, None, None, False)
    return run, files, scans


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--package', default=None, help='RC package (default: newest kwce-rc-sd-vN)')
    ap.add_argument('--wait', type=int, default=150, help='seconds to let the scripted session run')
    args = ap.parse_args()
    stopped()
    hw = ROOT / 'workspace/hardware'
    name = args.package or max((p.name for p in hw.glob('kwce-rc-sd-v*')), key=lambda n: int(n.rsplit('-v', 1)[1]))
    pkg = hw / name
    rec = json.loads((pkg / 'package-manifest.json').read_text(encoding='utf-8'))
    head_version = re.search(r'#define VERSION "([^"]+)"', (SRC / 'main.c').read_text(encoding='utf-8')).group(1)
    release = rc_hardware.release_of(head_version)     # the test DOL is built from the head source
    if not (pkg / 'kwce-rc/versions.txt').is_file():
        raise SystemExit(f'{name} has no version list (RC4+ only)')
    if (SD / 'kwce-rc').exists():
        raise SystemExit('The bed SD folder already has kwce-rc/; inspect it before testing')
    n = 1
    while (PRIVATE / f'rc-installer-test-{n}').exists():
        n += 1
    run = PRIVATE / f'rc-installer-test-{n}'
    (run / 'build').mkdir(parents=True)

    # 1) test-only DOL from the head source (keys from a file), same compiler gate as a package build
    dol = compile_installer(run / 'build', SRC, defines=('-DKWCE_TEST_SCRIPT',))

    # 2) backups first, then staging (inside try: any failure restores the bed)
    before = snapshot()
    backup = run / 'nand-backup'
    for tree in NAND_TREES:
        if (WII / tree).exists():
            shutil.copytree(WII / tree, backup / tree)
    shutil.copy2(DOL, run / 'bed-boot.dol')
    dol_sha = sha(DOL)
    area = bed_area()
    old_rc = hw / 'kwce-rc-sd-v1/kwce-rc'
    stage = [('personal-data', pkg / 'kwce-rc/personal-data/korean.wad'),
             ('nintendo', old_rc / 'nintendo/korean.wad'),
             ('photoprints', ROOT / 'workspace/channels/photoprints/originals/digicam-japan-v1024.wad')]
    data = SD / 'kwce-rc'
    result = dict(package=name, release=release, area=area, staged=[(c, str(p.relative_to(ROOT))) for c, p in stage],
                  test_dol_sha256=hashlib.sha256(dol).hexdigest(), checks={})
    try:
        lib = load_library()
        nand = lib.nand.EmuNAND(WII)
        for _cid, path in stage:
            title = lib.title.Title()
            title.load_wad(path.read_bytes())
            nand.install_title(title)
        data.mkdir()
        for f in ('packages.txt', 'versions.txt', 'editions.txt'):
            if f != 'editions.txt' or (pkg / 'kwce-rc' / f).is_file():   # editions.txt: RC9+ only
                shutil.copy2(pkg / 'kwce-rc' / f, data / f)
        for wad in sorted((pkg / 'kwce-rc').glob('*/*.wad')):
            (data / wad.parent.name).mkdir(exist_ok=True)
            (data / wad.parent.name / wad.name).write_bytes(head_of(wad))
        (data / 'allow-current-ios.txt').write_text('emulator test\n', encoding='ascii')
        (data / 'wiilink-skip.txt').write_text('', encoding='ascii')

        # 3) prediction and key script
        order, files, states, editions = predict(pkg, area, release)
        target = 'personal-data'
        updates = [c for c in order if states[c][0].startswith('UPDATE')]
        keys = ['# updates only', 'PLUS', 'A']
        if updates:
            keys.append('A')
            for c in updates:
                if states[c][1]['ver'] > files[c][0][2]:
                    keys.append('B')      # keep the newer installed version (prepare_overwrite prompt)
        keys.append('A')                  # summary / nothing to do
        keys += ['# channel menu: delete, then restore', *['DOWN'] * order.index(target), 'A',
                 'DOWN', 'DOWN', 'A', 'A', 'MINUS', 'A', '2', 'A', 'A', 'B',
                 '# tools: channel status report', 'B', 'PLUS', 'A']
        ed_cid = next(iter(editions), None)
        if ed_cid:
            # RC9+: channel menu -> RIGHT picks the first edition -> 1 installs it (A confirms). The staged
            # WADs are heads only, so the attempt stops at the content data; the bed is restored after.
            steps = (order.index(ed_cid) - order.index(target)) % len(order)
            keys += [f'# edition: {ed_cid}/{editions[ed_cid][0][0]}', *['DOWN'] * steps, 'A', 'RIGHT', '1', 'A', 'A', 'B']
        legacy = [c['id'] for c in rec['config']['channels'] if c.get('remove_only')]
        cursor = ed_cid or target
        for cid in legacy:
            steps = (order.index(cid) - order.index(cursor)) % len(order)
            keys += ['# legacy title must refuse installation', *['DOWN'] * steps, 'A', '1', 'A', 'B']
            cursor = cid
        (data / 'test-keys.txt').write_text('\n'.join(keys) + '\n', encoding='ascii')
        shutil.copy2(run / 'build/boot.dol', DOL)

        # 4) run (helper detaches Dolphin; nothing here waits on its output)
        chk = subprocess.run([PY, str(ROOT / 'scripts/launch_hardware_test.py'), '--check'], cwd=ROOT,
                             capture_output=True, text=True, timeout=120)
        if chk.returncode:
            raise SystemExit('bed check failed: ' + (chk.stdout + chk.stderr)[-400:])
        with open(run / 'launch.txt', 'w', encoding='utf-8') as out:
            subprocess.run([PY, str(ROOT / 'scripts/launch_hardware_test.py')], cwd=ROOT, stdout=out,
                           stderr=subprocess.STDOUT, timeout=120, check=True)
        time.sleep(args.wait)
        with open(run / 'stop.txt', 'w', encoding='utf-8') as out:
            subprocess.run([PY, str(ROOT / 'scripts/dolphin_ui.py'), 'stop'], cwd=ROOT, stdout=out,
                           stderr=subprocess.STDOUT, timeout=120)
        for _ in range(30):
            try:
                stopped()
                break
            except SystemExit:
                time.sleep(2)
        stopped()

        # 5) compare
        log = (data / 'log.txt').read_text(encoding='ascii', errors='replace') if (data / 'log.txt').exists() else ''
        (run / 'installer-log.txt').write_text(log, encoding='utf-8')
        text, cfiles, scans = parse_log(log)
        c = result['checks']
        c['log_written'] = bool(text)
        if legacy:
            c['legacy_install_refused'] = text.count('This legacy channel is not needed.') == len(legacy)
        c['exit_reached'] = '--- exit:' in text
        c['package_fp_match'] = all(cfiles.get(cid) == (f'{k[0]:016x}' if k else 'missing',
                                                        f'{o[0]:016x}' if o else 'none')
                                    for cid, (k, o) in files.items())
        start = dict(scans).get('start', {})
        rows = []
        for cid in order:
            want_s, info = states[cid]
            got = start.get(cid)
            ok = got is not None and got[0] == want_s and (info is None or (got[1] == info['fp'] and
                                                                          got[4] == (info['region_ok'] is False)))
            rows.append((cid, want_s, got[0] if got else None, ok))
        c['scan_matches_prediction'] = all(r[3] for r in rows)
        c['delete_verified'] = 'Verified on the console: the channel is deleted.' in text
        restore_part = text.split('== Restore: Set Personal Data', 1)[-1]
        c['restore_attempted'] = ('Reinstall the original channel?' in restore_part
                                  and ('Installing 000100084843434a' in restore_part or 'Required IOS' in restore_part))
        c['signature_hint_shown'] = 'Hint: the signature check failed' in text if 'failed: -2011' in text else True
        status = sorted(data.glob('status-*.txt'))
        c['status_report'] = bool(status) and len(status[0].read_text(encoding='ascii').splitlines()) == 5 + len(order)
        if status:
            shutil.copy2(status[0], run / status[0].name)
        if ed_cid:
            key, label, _fp = editions[ed_cid][0]
            c['editions_logged'] = all(cfiles.get((ecid, k)) == f'{efp:016x}'
                                       for ecid, eds in editions.items() for k, _l, efp in eds)
            part = text.rsplit('== Install Korean:', 1)[-1]
            c['edition_install_attempted'] = (f'Edition: {label}' in part and f'korean-{key}.wad' in part
                                              and ('Installing ' in part or 'Required IOS' in part))
            result['edition_tried'] = f'{ed_cid}/{key}'
        result['rows'] = rows
        result['updates_attempted'] = updates
    finally:
        # 6) restore the bed exactly
        try:
            stopped()
            shutil.copy2(run / 'bed-boot.dol', DOL)
            if data.exists():
                shutil.move(str(data), str(run / 'sd-kwce-rc'))
            result['bed_restored'] = restore_nand(before, backup) and sha(DOL) == dol_sha and not (SD / 'kwce-rc').exists()
        except SystemExit:
            result['bed_restored'] = False
            result['note'] = 'Dolphin still running: bed NOT restored; stop it and rerun the restore'
        (run / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    for cid, want_s, got_s, ok in result.get('rows', []):
        print(f"  {'ok ' if ok else 'BAD'} {cid:<14} expected {want_s!r:<30} log {got_s!r}")
    for k, v in result['checks'].items():
        print(f'  {k:<24} {v}')
    print('  bed_restored            ', result.get('bed_restored'))
    good = all(result['checks'].values()) and result.get('bed_restored')
    print(('PASS' if good else 'FAIL') + f': {run.relative_to(ROOT)}')
    if not good:
        sys.exit(1)


if __name__ == '__main__':
    main()

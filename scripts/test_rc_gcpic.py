"""Emulator test of the installer's optional GameCube pictures (1.0.10+, gcpic.c).

Uses the Dolphin bed workspace/sandbox/hardware-test-v1 (a copy of the owner NAND: 4.3K Korean menu
with the original 0000009d.app and Priiloader's renamed boot content 1000009e.app). Three scripted
runs of a TEST-ONLY installer DOL (-DKWCE_TEST_SCRIPT, keys from sd:/kwce-rc/test-keys.txt):
  1. Priiloader hidden (1000009e.app moved aside): install must refuse, resource unchanged;
  2. install: resource becomes the KWCE file, SD backup equals the original;
  3. restore: resource is the original again.
After each run the emulated NAND file is hashed directly. The bed (content files, /tmp, SD folder,
DOL) is restored at the end. Evidence: workspace/private/rc-gcpic-test-N/. Needs Dolphin stopped.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from audit_sd import ROOT, PRIVATE
from prepare_channel_access import stopped

sys.path.insert(0, str(ROOT))
from export_rc_hardware import compile_installer, SRC  # noqa: E402
from test_rc_installer import head_of  # noqa: E402

BED = ROOT / 'workspace/sandbox/hardware-test-v1'
WII = BED / 'user/Wii'
CONTENT = WII / 'title/00000001/00000002/content'
SD = BED / 'sd-sync'
DOL = SD / 'apps/kwce-installer/boot.dol'
PY = str(ROOT / '.venv/Scripts/python.exe')


def sha1(p):
    return hashlib.sha1(Path(p).read_bytes()).hexdigest() if Path(p).is_file() else None


def run_session(run, tag, keys, wait):
    data = SD / 'kwce-rc'
    (data / 'test-keys.txt').write_text('\n'.join(keys) + '\n', encoding='ascii')
    log = data / 'log.txt'
    if log.exists():
        log.unlink()
    chk = subprocess.run([PY, str(ROOT / 'scripts/launch_hardware_test.py'), '--check'], cwd=ROOT,
                         capture_output=True, text=True, timeout=120)
    if chk.returncode:
        raise SystemExit('bed check failed: ' + (chk.stdout + chk.stderr)[-400:])
    with open(run / f'launch-{tag}.txt', 'w', encoding='utf-8') as out:
        subprocess.run([PY, str(ROOT / 'scripts/launch_hardware_test.py')], cwd=ROOT, stdout=out,
                       stderr=subprocess.STDOUT, timeout=120, check=True)
    deadline = time.time() + wait
    while time.time() < deadline:                 # the script ends with the exit line in the log
        if log.exists() and '--- exit:' in log.read_text(encoding='ascii', errors='replace'):
            time.sleep(3)
            break
        time.sleep(2)
    with open(run / f'stop-{tag}.txt', 'w', encoding='utf-8') as out:
        subprocess.run([PY, str(ROOT / 'scripts/dolphin_ui.py'), 'stop'], cwd=ROOT, stdout=out,
                       stderr=subprocess.STDOUT, timeout=120)
    for _ in range(30):
        try:
            stopped()
            break
        except SystemExit:
            time.sleep(2)
    stopped()
    text = log.read_text(encoding='ascii', errors='replace') if log.exists() else ''
    (run / f'installer-log-{tag}.txt').write_text(text, encoding='utf-8')
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--package', required=True, help='RC package with kwce-rc/menu (1.0.10+)')
    ap.add_argument('--wait', type=int, default=150)
    args = ap.parse_args()
    stopped()
    pkg = ROOT / 'workspace/hardware' / args.package
    rec = json.loads((pkg / 'package-manifest.json').read_text(encoding='utf-8'))
    g = rec['gc_pictures']
    if sha1(CONTENT / '0000009d.app') != g['original_sha1'] or not (CONTENT / '1000009e.app').is_file():
        raise SystemExit('Bed is not the expected original 4.3K menu with Priiloader')
    n = 1
    while (PRIVATE / f'rc-gcpic-test-{n}').exists():
        n += 1
    run = PRIVATE / f'rc-gcpic-test-{n}'
    (run / 'build').mkdir(parents=True)
    dol = compile_installer(run / 'build', SRC, defines=('-DKWCE_TEST_SCRIPT',), nand_writer='gcpic.c')

    keep = {name: (CONTENT / name).read_bytes() for name in ('0000009d.app', '1000009e.app')}
    tmp_before = sorted(p.name for p in (WII / 'tmp').iterdir()) if (WII / 'tmp').exists() else None
    shutil.copy2(DOL, run / 'bed-boot.dol')
    prior = run / 'bed-sd-kwce-rc-before'          # earlier tests' report files: moved aside, put back
    if (SD / 'kwce-rc').exists():
        shutil.move(str(SD / 'kwce-rc'), str(prior))
    dol_sha = hashlib.sha256(DOL.read_bytes()).hexdigest()
    data = SD / 'kwce-rc'
    result = dict(package=args.package, test_dol_sha256=hashlib.sha256(dol).hexdigest(), checks={},
                  prior_sd_files=sorted(p.name for p in prior.iterdir()) if prior.exists() else [])
    c = result['checks']
    try:
        data.mkdir()
        for f in ('packages.txt', 'versions.txt', 'editions.txt'):
            if (pkg / 'kwce-rc' / f).is_file():
                shutil.copy2(pkg / 'kwce-rc' / f, data / f)
        for wad in sorted((pkg / 'kwce-rc').glob('*/*.wad')):
            (data / wad.parent.name).mkdir(exist_ok=True)
            (data / wad.parent.name / wad.name).write_bytes(head_of(wad))
        shutil.copytree(pkg / 'kwce-rc/menu', data / 'menu')
        (data / 'allow-current-ios.txt').write_text('emulator test\n', encoding='ascii')
        (data / 'wiilink-skip.txt').write_text('', encoding='ascii')
        shutil.copy2(run / 'build/boot.dol', DOL)
        go = ['MINUS', 'PLUS']

        # 1) Priiloader hidden: refused, nothing written
        (CONTENT / '1000009e.app').rename(run / '1000009e.app.aside')
        try:
            t1 = run_session(run, '1-no-priiloader', ['# no priiloader', *go, '1', 'A'], args.wait)
        finally:
            (run / '1000009e.app.aside').rename(CONTENT / '1000009e.app')
        c['1_priiloader_not_found'] = 'Priiloader: NOT FOUND' in t1 and 'Not installed: Priiloader was not found' in t1
        c['1_resource_unchanged'] = sha1(CONTENT / '0000009d.app') == g['original_sha1']
        c['1_no_backup'] = not (data / 'menu/backup-0000009d.app').exists()

        # 2) install
        t2 = run_session(run, '2-install', ['# install', *go, '1', 'A', 'A'], args.wait)
        c['2_state_original'] = 'Resource: original' in t2 and 'Priiloader: installed' in t2
        c['2_verified'] = 'Verified.' in t2
        c['2_resource_kwce'] = sha1(CONTENT / '0000009d.app') == g['patched_sha1']
        c['2_backup_original'] = sha1(data / 'menu/backup-0000009d.app') == g['original_sha1']

        # 3) restore
        t3 = run_session(run, '3-restore', ['# restore', *go, '2', 'A', 'A'], args.wait)
        c['3_state_kwce'] = 'Resource: KWCE' in t3
        c['3_from_backup'] = 'Original from sd:/kwce-rc/menu/backup-0000009d.app' in t3
        c['3_verified'] = 'Verified.' in t3
        c['3_resource_original'] = sha1(CONTENT / '0000009d.app') == g['original_sha1']
        c['tmp_clean'] = not (WII / 'tmp/0000009d.app').exists()
    finally:
        try:
            stopped()
            for name, raw in keep.items():
                if not (CONTENT / name).is_file() or (CONTENT / name).read_bytes() != raw:
                    (CONTENT / name).write_bytes(raw)
            if (WII / 'tmp/0000009d.app').exists():
                (WII / 'tmp/0000009d.app').unlink()
            shutil.copy2(run / 'bed-boot.dol', DOL)
            if data.exists():
                shutil.move(str(data), str(run / 'sd-kwce-rc'))
            if prior.exists():
                shutil.move(str(prior), str(data))
            tmp_after = sorted(p.name for p in (WII / 'tmp').iterdir()) if (WII / 'tmp').exists() else None
            result['bed_restored'] = (all((CONTENT / k).read_bytes() == v for k, v in keep.items())
                                      and hashlib.sha256(DOL.read_bytes()).hexdigest() == dol_sha
                                      and (SD / 'kwce-rc').exists() == bool(result.get('prior_sd_files'))
                                      and tmp_after == tmp_before)
        except SystemExit:
            result['bed_restored'] = False
            result['note'] = 'Dolphin still running: bed NOT restored'
        (run / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    for k, v in c.items():
        print(f'  {k:<26} {v}')
    print('  bed_restored              ', result.get('bed_restored'))
    good = c and all(c.values()) and result.get('bed_restored')
    print(('PASS' if good else 'FAIL') + f': {run.relative_to(ROOT)}')
    if not good:
        sys.exit(1)


if __name__ == '__main__':
    main()

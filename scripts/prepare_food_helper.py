"""Build a new numbered Food sandbox helper and pin it in the runtime lock.

  .venv\\Scripts\\python.exe scripts\\prepare_food_helper.py --revision 2

Creates tools/food-sandbox/vN/bin once. FoodRunner.cs/.exe are copied
byte-for-byte from the pinned v1 helper (hashes checked against the lock
first). FoodServer is compiled from scripts/FoodServer.cs; revision 2 reads the
plain `action` name the way the pinned WiiLink food-server does, answers a POST
without `action` (the channel's error report) with the document template, and
logs parameter names only. Replaces the helper rows in
configs/food-runtime.lock.json and records lock['helper']. Never starts
Dolphin; the profile and the earlier helper folders stay unchanged.
"""
import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from audit_sd import ROOT, sha256
from prepare_channel_access import stopped

LOCK = ROOT / 'configs/food-runtime.lock.json'
V1 = ROOT / 'tools/food-sandbox/v1/bin'
REVISIONS = (2,)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--revision', type=int, choices=REVISIONS, default=REVISIONS[-1])
    args = ap.parse_args()
    stopped()
    out = ROOT / f'tools/food-sandbox/v{args.revision}/bin'
    if out.exists():
        raise SystemExit('Existing Food helper preserved: ' + str(out))
    lock = json.loads(LOCK.read_text())
    if lock.get('helper', V1.relative_to(ROOT).as_posix()) != V1.relative_to(ROOT).as_posix():
        raise SystemExit('Runtime lock no longer points at helper v1; refusing to rebuild')
    pinned = {row['path']: row['sha256'] for row in lock['files']}
    for name in ('FoodRunner.cs', 'FoodRunner.exe'):
        if pinned.get((V1 / name).relative_to(ROOT).as_posix()) != sha256(V1 / name):
            raise SystemExit('Pinned v1 Food runner differs: ' + name)
    out.mkdir(parents=True)
    for name in ('FoodRunner.cs', 'FoodRunner.exe'):
        shutil.copy2(V1 / name, out / name)
    shutil.copy2(ROOT / 'scripts/FoodServer.cs', out / 'FoodServer.cs')
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    result = subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x64',
                             '/out:' + str(out / 'FoodServer.exe'), str(out / 'FoodServer.cs')],
                            capture_output=True, text=True)
    if result.returncode:
        raise SystemExit('FoodServer compile failed:\n' + result.stdout[-2000:])
    rows = [dict(path=p.relative_to(ROOT).as_posix(), sha256=sha256(p))
            for p in sorted(out.iterdir()) if p.suffix in ('.cs', '.exe')]
    lock['files'] = [r for r in lock['files'] if not r['path'].startswith('tools/food-sandbox/')] + rows
    lock['helper'] = out.relative_to(ROOT).as_posix()
    lock['helper_revision'] = args.revision
    LOCK.write_text(json.dumps(lock, indent=2) + '\n')
    print(f'Built Food helper v{args.revision} ({len(rows)} files) and pinned it in the runtime lock; v1 preserved')


if __name__ == '__main__':
    main()

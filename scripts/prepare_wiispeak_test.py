"""Isolated Wii Speak Channel boot test bed (official Korean original first).

Clones the sanitized votes-test-v1 profile into workspace/sandbox/wiispeak-test-v1,
keeps the Korean locale with SD/WiiLink off and no USB/Bluetooth passthrough or
emulated microphone (kwce.wiispeak_testbed), installs the OFFICIAL Korean v512
WAD into its EmuNAND, and compiles a capability-0 runner derived from
scripts/FeedRunner.cs without its feed server. Writes
configs/wiispeak-runtime.lock.json and workspace/channels/wiispeak/active-build.json.
Never starts Dolphin; the template is snapshot-checked unchanged.

  .venv\\Scripts\\python.exe scripts\\prepare_wiispeak_test.py
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from audit_sd import ROOT, PRIVATE, sha256
from prepare_channel_access import stopped
from prepare_gc_v6 import snapshot
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library  # noqa: E402
from kwce import wiispeak_testbed as bed  # noqa: E402
import launch_dolphin as launcher  # noqa: E402

PROFILE, TITLE = bed.PROFILE, bed.TITLE
BASE, HELPER, TEMPLATE, CHANNEL = ROOT / bed.SANDBOX, ROOT / bed.HELPER, ROOT / bed.TEMPLATE, ROOT / bed.CHANNEL


def register():
    launcher.NATIVE_PROFILES[PROFILE] = bed.SANDBOX
    if PROFILE not in launcher.PROFILES:
        launcher.PROFILES = (*launcher.PROFILES, PROFILE)


def install(name, pinned):
    """Install one approved build into the bed's EmuNAND and mark it active; returns its sha256."""
    data = (CHANNEL / bed.BUILDS[name]).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != pinned[name]:
        raise ValueError('Wii Speak build differs from its pinned hash: ' + name)
    lib = load_library()
    title = lib.title.Title()
    title.load_wad(data)
    if title.tmd.title_id != TITLE or title.tmd.title_version != 512:
        raise ValueError('Wii Speak title identity differs')
    lib.nand.EmuNAND(BASE / 'user/Wii').install_title(title)
    (ROOT / bed.ACTIVE).write_text(json.dumps(dict(build=name, wad_sha256=digest), indent=2) + '\n', encoding='utf-8')
    return digest


def main():
    stopped()
    if BASE.exists() or HELPER.exists() or (ROOT / bed.LOCK).exists():
        raise SystemExit('Existing Wii Speak bed/helper/lock preserved')
    pinned = bed.pinned_builds(CHANNEL)
    before = snapshot(TEMPLATE)
    (PRIVATE / 'wiispeak-template-before-v1.json').write_text(json.dumps(before, indent=2))
    BASE.mkdir(parents=True)
    for name in ['user', 'Dolphin-x64']:
        shutil.copytree(TEMPLATE / name, BASE / name, ignore=shutil.ignore_patterns('Logs', 'Cache', 'ScreenShots', 'StateSaves'))
    shutil.copy2(TEMPLATE / 'NetProbe.exe', BASE / 'NetProbe.exe')
    ini = BASE / 'user/Config/Dolphin.ini'
    ini.write_text(bed.sanitized_dolphin_ini(ini.read_text(encoding='utf-8-sig'), TEMPLATE, BASE), encoding='utf-8')
    bed.check_dolphin_ini(ini, BASE / 'user')
    install(bed.BASELINE, pinned)
    register()
    launcher.scrub_download_tasks(PROFILE)
    launcher.validate(PROFILE)
    HELPER.mkdir(parents=True)
    source = HELPER / (bed.RUNNER + '.cs')
    source.write_text(bed.derive_runner((ROOT / 'scripts/FeedRunner.cs').read_text()), encoding='utf-8')
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x64', '/out:' + str(source.with_suffix('.exe')), str(source)],
                   check=True, capture_output=True)
    locked = [BASE / 'Dolphin-x64/Dolphin.exe', BASE / 'NetProbe.exe', source, source.with_suffix('.exe')]
    (ROOT / bed.LOCK).write_text(json.dumps(dict(
        profile=PROFILE, title_id=TITLE, capability_count=0, external_network_allowed=False, microphone_allowed=False,
        local_server=False, files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha256(p)) for p in locked],
        builds=pinned), indent=2) + '\n', encoding='utf-8')
    if snapshot(TEMPLATE) != before:
        raise ValueError('Wii Speak template changed')
    print('Prepared Wii Speak bed: official Korean v512 active in an isolated Korean profile; '
          'capability-0 runner without feed server; template preserved; Dolphin not started')


if __name__ == '__main__':
    main()

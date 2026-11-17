"""Separate Korean-locale Food NAND profile + capability-0 fixture helper.

Clones the sanitized votes test template, installs the pinned Food local-test
WAD into its EmuNAND, generates the synthetic browse feed, and compiles the
zero-capability FoodRunner/FoodServer helper. Does not run Dolphin and does not
touch configs/channels.catalog.json (a standalone catalog-entry.json is written
under the channel folder instead).
"""
import configparser, json, os, shutil, subprocess, sys
from pathlib import Path
from audit_sd import ROOT, PRIVATE, sha256
from prepare_channel_access import stopped
from prepare_gc_v6 import snapshot
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.food_fixtures import write_feed
import launch_dolphin as launcher

PROFILE = 'food-test-v1-user'
TITLE = '000100014843484a'
BASE = ROOT / 'workspace/sandbox/food-test-v1'
HELPER = ROOT / 'tools/food-sandbox/v1/bin'
TEMPLATE = ROOT / 'workspace/sandbox/votes-test-v1'


def register():
    launcher.NATIVE_PROFILES[PROFILE] = 'workspace/sandbox/food-test-v1'
    if PROFILE not in launcher.PROFILES:
        launcher.PROFILES = (*launcher.PROFILES, PROFILE)


def main():
    stopped()
    if BASE.exists() or HELPER.exists():
        raise SystemExit('Existing Food profile/helper preserved')
    before = snapshot(TEMPLATE)
    (PRIVATE / 'food-template-before-v1.json').write_text(json.dumps(before, indent=2))
    BASE.mkdir(parents=True)
    for name in ['user', 'Dolphin-x64']:
        shutil.copytree(TEMPLATE / name, BASE / name, ignore=shutil.ignore_patterns('Logs', 'Cache', 'ScreenShots', 'StateSaves'))
    shutil.copy2(TEMPLATE / 'NetProbe.exe', BASE / 'NetProbe.exe')
    path = BASE / 'user/Config/Dolphin.ini'
    cfg = configparser.ConfigParser(strict=False); cfg.optionxform = str; cfg.read(path, encoding='utf-8-sig')
    for section in cfg.sections():
        for key, value in cfg[section].items():
            cfg[section][key] = value.replace(str(TEMPLATE), str(BASE)).replace(TEMPLATE.as_posix(), BASE.as_posix())
    cfg['Core']['DefaultISO'] = ''; cfg['Core']['EnableWiiLink'] = 'False'; cfg['Core']['OverrideRegionSettings'] = 'True'
    for key in ['WiiSDCard', 'WiiSDCardEnableFolderSync', 'WiiSDCardAllowWrites']:
        cfg['Core'][key] = 'False'
    with path.open('w', encoding='utf-8') as f:
        cfg.write(f)
    lib = load_library(); title = lib.title.Title()
    wad = ROOT / 'workspace/channels/food/build-v1/food-ko-local-test.wad'
    meta = json.loads(wad.with_name('build-manifest.json').read_text(encoding='utf-8'))
    if not meta.get('local_only') or sha256(wad) != meta['wad_sha256']:
        raise ValueError('Food build identity/scope')
    title.load_wad(wad.read_bytes()); lib.nand.EmuNAND(BASE / 'user/Wii').install_title(title)
    register(); launcher.scrub_download_tasks(PROFILE); launcher.validate(PROFILE)
    fixture = write_feed(BASE / 'local-feed')
    # Capability-0 helper: adapt the shared runner, use the Food server as-is.
    runner = (ROOT / 'scripts/FeedRunner.cs').read_text()
    old = 'bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","news-v1"),StringComparison.OrdinalIgnoreCase);'
    if runner.count(old) != 1:
        raise ValueError('Food runner source guard')
    runner = (runner.replace(old, 'bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","food-test-v1"),StringComparison.OrdinalIgnoreCase);')
              .replace('0001000248414745', TITLE).replace('class FeedRunner', 'class FoodRunner').replace('FeedServer.exe', 'FoodServer.exe'))
    server = (ROOT / 'scripts/FoodServer.cs').read_text()
    HELPER.mkdir(parents=True)
    (HELPER / 'FoodRunner.cs').write_text(runner, encoding='utf-8')
    (HELPER / 'FoodServer.cs').write_text(server, encoding='utf-8')
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    for sourcefile in HELPER.glob('*.cs'):
        subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x64', '/out:' + str(sourcefile.with_suffix('.exe')), str(sourcefile)], check=True, capture_output=True)
    locked = [BASE / 'Dolphin-x64/Dolphin.exe', BASE / 'NetProbe.exe',
              *(p for p in sorted(HELPER.iterdir()) if p.suffix in ('.cs', '.exe')),
              BASE / 'local-feed/fixture-manifest.json']
    (ROOT / 'configs/food-runtime.lock.json').write_text(json.dumps(dict(
        profile=PROFILE, title_id=TITLE, capability_count=0, external_network_allowed=False,
        files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha256(p)) for p in locked],
        builds={'1': meta['wad_sha256']}), indent=2))
    (ROOT / 'workspace/channels/food/active-build.json').write_text(json.dumps(dict(revision=1, wad_sha256=meta['wad_sha256']), indent=2))
    if snapshot(TEMPLATE) != before:
        raise ValueError('Food template changed')
    print('Installed Food v1 in a separate sanitized Korean profile; template preserved; capability-0 helper + synthetic feed ready;',
          len(fixture['files']), 'feed files')


if __name__ == '__main__':
    main()

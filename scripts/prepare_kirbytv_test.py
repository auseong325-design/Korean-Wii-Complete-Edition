"""Separate Korean-locale Kirby TV NAND and zero-capability fixture helper.

Clones the votes test profile, installs build-v1 into its EmuNAND, compiles a
capability-zero AppContainer helper (Dolphin + a local static file server on
127.0.0.2), and stages the synthetic local feed. The original/template are
preserved; nothing touches the real SD or console.
"""
import configparser
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
from kwce.channels import load_library
import launch_dolphin as launcher

PROFILE = 'kirbytv-test-v1-user'
TITLE = '0001000148434d50'
BASE = ROOT / 'workspace/sandbox/kirbytv-test-v1'
HELPER = ROOT / 'tools/kirbytv-sandbox/v1/bin'
FEED_SOURCE = ROOT / 'workspace/channels/kirbytv/local-feed-v1'


def register():
    launcher.NATIVE_PROFILES[PROFILE] = 'workspace/sandbox/kirbytv-test-v1'
    if PROFILE not in launcher.PROFILES:
        launcher.PROFILES = (*launcher.PROFILES, PROFILE)


def main():
    stopped()
    if BASE.exists() or HELPER.exists():
        raise SystemExit('Existing Kirby TV profile/helper preserved')
    source = ROOT / 'workspace/sandbox/votes-test-v1'
    before = snapshot(source)
    (PRIVATE / 'kirbytv-template-before-v1.json').write_text(json.dumps(before, indent=2))
    BASE.mkdir(parents=True)
    for name in ['user', 'Dolphin-x64']:
        shutil.copytree(source / name, BASE / name, ignore=shutil.ignore_patterns('Logs', 'Cache', 'ScreenShots', 'StateSaves'))
    shutil.copy2(source / 'NetProbe.exe', BASE / 'NetProbe.exe')
    path = BASE / 'user/Config/Dolphin.ini'
    cfg = configparser.ConfigParser(strict=False)
    cfg.optionxform = str
    cfg.read(path, encoding='utf-8-sig')
    for section in cfg.sections():
        for key, value in cfg[section].items():
            cfg[section][key] = value.replace(str(source), str(BASE)).replace(source.as_posix(), BASE.as_posix())
    cfg['Core']['DefaultISO'] = ''
    cfg['Core']['EnableWiiLink'] = 'False'
    cfg['Core']['OverrideRegionSettings'] = 'True'
    for key in ['WiiSDCard', 'WiiSDCardEnableFolderSync', 'WiiSDCardAllowWrites']:
        cfg['Core'][key] = 'False'
    with path.open('w', encoding='utf-8') as f:
        cfg.write(f)
    lib = load_library()
    title = lib.title.Title()
    wad = ROOT / 'workspace/channels/kirbytv/build-v1/kirbytv-ko-local-test.wad'
    title.load_wad(wad.read_bytes())
    lib.nand.EmuNAND(BASE / 'user/Wii').install_title(title)
    register()
    launcher.scrub_download_tasks(PROFILE)
    launcher.validate(PROFILE)
    # Local feed: copy the synthetic responses into the sandbox server root.
    feed = BASE / 'local-feed'
    feed.mkdir()
    fixture = json.loads((FEED_SOURCE / 'fixture-manifest.json').read_text(encoding='utf-8'))
    files = []
    for row in fixture['files']:
        shutil.copy2(FEED_SOURCE / row['path'], feed / row['path'])
        if sha256(feed / row['path']) != row['sha256']:
            raise ValueError('Feed copy mismatch: ' + row['path'])
        files.append(row)
    (feed / 'fixture-manifest.json').write_text(json.dumps(dict(revision=1, local_only=True, synthetic=True, files=files), indent=2))
    # Capability-zero helper derived from the News runner + static server.
    text = (ROOT / 'scripts/FeedRunner.cs').read_text()
    old = 'bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","news-v1"),StringComparison.OrdinalIgnoreCase);'
    if text.count(old) != 1:
        raise ValueError('Kirby helper source guard')
    text = (text.replace(old, 'bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","kirbytv-test-v1"),StringComparison.OrdinalIgnoreCase);')
            .replace('0001000248414745', TITLE).replace('class FeedRunner', 'class KirbyRunner')
            .replace('FeedServer.exe', 'KirbyServer.exe'))
    server = ((ROOT / 'scripts/ChannelTestServer.cs').read_text()
              .replace('class ChannelTestServer', 'class KirbyServer')
              .replace('bool nas=path=="/ac"||path=="/pr";', 'bool nas=false;'))
    HELPER.mkdir(parents=True)
    (HELPER / 'KirbyRunner.cs').write_text(text, encoding='utf-8')
    (HELPER / 'KirbyServer.cs').write_text(server, encoding='utf-8')
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    for sourcefile in HELPER.glob('*.cs'):
        subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x64', '/out:' + str(sourcefile.with_suffix('.exe')), str(sourcefile)], check=True, capture_output=True)
    locked = [BASE / 'Dolphin-x64/Dolphin.exe', BASE / 'NetProbe.exe',
              *(p for p in sorted(HELPER.iterdir()) if p.suffix in ('.cs', '.exe')),
              feed / 'fixture-manifest.json', *(feed / r['path'] for r in files)]
    manifest = json.loads(wad.with_name('build-manifest.json').read_text(encoding='utf-8'))
    (ROOT / 'configs/kirbytv-runtime.lock.json').write_text(json.dumps(dict(
        profile=PROFILE, title_id=TITLE, capability_count=0, external_network_allowed=False,
        files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha256(p)) for p in locked],
        builds={'1': manifest['wad_sha256']}), indent=2))
    (ROOT / 'workspace/channels/kirbytv/active-build.json').write_text(json.dumps(dict(revision=1, wad_sha256=manifest['wad_sha256']), indent=2))
    # The catalog row is added by the lead from workspace/channels/kirbytv/catalog-entry.json;
    # this worker never edits configs/channels.catalog.json.
    if snapshot(source) != before:
        raise ValueError('Kirby TV template changed')
    print('Installed Kirby TV v1 in a separate sanitized Korean profile; template preserved; capability-zero helper ready')


if __name__ == '__main__':
    main()

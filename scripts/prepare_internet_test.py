"""Separate Korean-locale Internet Channel NAND profile and zero-capability page server.

  .venv\\Scripts\\python.exe scripts\\prepare_internet_test.py

Creates once: workspace/sandbox/internet-test-v1 (cloned from the
votes-test-v1 template, which stays unchanged), installs build-v1, copies
local-feed-v1 into the profile, derives and compiles the helper in
tools/internet-sandbox/v1/bin from scripts/FeedRunner.cs and
scripts/ChannelTestServer.cs (adds a Content-Type column; the NAS emulation is
disabled), and writes configs/internet-runtime.lock.json plus
workspace/channels/internet/active-build.json. Never starts Dolphin and never
edits the shared channel catalog (see workspace/channels/internet/catalog-entry.json).
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
from kwce.channels import load_library  # noqa: E402
import launch_dolphin as launcher  # noqa: E402

PROFILE = 'internet-test-v1-user'
TITLE = '0001000148414445'
BASE = ROOT / 'workspace/sandbox/internet-test-v1'
HELPER = ROOT / 'tools/internet-sandbox/v1/bin'
TEMPLATE = ROOT / 'workspace/sandbox/votes-test-v1'
FEED = ROOT / 'workspace/channels/internet/local-feed-v2'
LOCK = ROOT / 'configs/internet-runtime.lock.json'
ACTIVE = ROOT / 'workspace/channels/internet/active-build.json'


def register():
    launcher.NATIVE_PROFILES[PROFILE] = 'workspace/sandbox/internet-test-v1'
    if PROFILE not in launcher.PROFILES:
        launcher.PROFILES = (*launcher.PROFILES, PROFILE)


def _replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError(f'Helper source guard: {old[:60]!r} found {text.count(old)} times')
    return text.replace(old, new)


def runner_source():
    text = (ROOT / 'scripts/FeedRunner.cs').read_text(encoding='utf-8')
    text = _replace(text, 'bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","news-v1"),StringComparison.OrdinalIgnoreCase);',
                    'bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","internet-test-v1"),StringComparison.OrdinalIgnoreCase);')
    text = _replace(text, '0001000248414745', TITLE)
    text = _replace(text, 'class FeedRunner', 'class InternetRunner')
    return _replace(text, 'FeedServer.exe', 'InternetServer.exe')


def server_source():
    text = (ROOT / 'scripts/ChannelTestServer.cs').read_text(encoding='utf-8')
    text = _replace(text, 'class ChannelTestServer', 'class InternetServer')
    text = _replace(text, 'static Dictionary<string,string> routes=new Dictionary<string,string>();',
                    'static Dictionary<string,string> routes=new Dictionary<string,string>();\n static Dictionary<string,string> types=new Dictionary<string,string>();')
    text = _replace(text, 'static void Reply(NetworkStream s,int status,byte[] data,bool head) {',
                    'static void Reply(NetworkStream s,int status,byte[] data,bool head,string type) {')
    text = _replace(text, r'\r\nContent-Type: application/octet-stream\r\nContent-Length: ', r'\r\nContent-Type: "+type+"\r\nContent-Length: ')
    text = _replace(text, 'bool nas=path=="/ac"||path=="/pr";', 'bool nas=false;')
    text = _replace(text, 'Reply(s,reply==null?404:200,reply??new byte[0],false);', 'Reply(s,reply==null?404:200,reply??new byte[0],false,"application/octet-stream");')
    text = _replace(text, 'string mapped;bool found=routes.TryGetValue(req[0]+" "+path,out mapped)||routes.TryGetValue("* "+path,out mapped);',
                    'string mapped;bool found=routes.TryGetValue(req[0]+" "+path,out mapped)||routes.TryGetValue("* "+path,out mapped);'
                    'string key=routes.ContainsKey(req[0]+" "+path)?req[0]+" "+path:"* "+path;')
    text = _replace(text, 'Reply(s,exists?200:404,data,req[0]=="HEAD");', 'Reply(s,exists?200:404,data,req[0]=="HEAD",exists?types[key]:"text/plain");')
    return _replace(text, 'if(r.Length!=2)throw new Exception("Route format");routes.Add(r[0],r[1]);',
                    'if(r.Length!=3)throw new Exception("Route format");routes.Add(r[0],r[1]);types.Add(r[0],r[2]);')


def feed_manifest():
    data = json.loads((FEED / 'fixture-manifest.json').read_text(encoding='utf-8'))
    if not (data.get('local_only') and data.get('synthetic') and data.get('fictional')) or data.get('accepts_orders_uploads_or_posts'):
        raise ValueError('Internet local feed scope differs')
    for row in data['files']:
        if Path(row['path']).name != row['path'] or sha256(FEED / row['path']) != row['sha256']:
            raise ValueError('Internet local feed file differs')
    if sha256(FEED / 'routes.tsv') != data['routes_sha256']:
        raise ValueError('Internet local feed routes differ')
    return data


def main():
    stopped()
    if BASE.exists() or HELPER.exists() or LOCK.exists():
        raise SystemExit('Existing Internet Channel profile/helper/lock preserved')
    feed = feed_manifest()
    wad = ROOT / 'workspace/channels/internet/build-v1/internet-ko-local-test.wad'
    manifest = json.loads(wad.with_name('build-manifest.json').read_text(encoding='utf-8'))
    if not manifest.get('local_only') or sha256(wad) != manifest['wad_sha256']:
        raise ValueError('Internet build identity/scope')
    before = snapshot(TEMPLATE)
    (PRIVATE / 'internet-template-before-v1.json').write_text(json.dumps(before, indent=2))
    BASE.mkdir(parents=True)
    for name in ['user', 'Dolphin-x64']:
        shutil.copytree(TEMPLATE / name, BASE / name, ignore=shutil.ignore_patterns('Logs', 'Cache', 'ScreenShots', 'StateSaves'))
    shutil.copy2(TEMPLATE / 'NetProbe.exe', BASE / 'NetProbe.exe')
    path = BASE / 'user/Config/Dolphin.ini'
    cfg = configparser.ConfigParser(strict=False)
    cfg.optionxform = str
    cfg.read(path, encoding='utf-8-sig')
    for section in cfg.sections():
        for key, value in cfg[section].items():
            cfg[section][key] = value.replace(str(TEMPLATE), str(BASE)).replace(TEMPLATE.as_posix(), BASE.as_posix())
    cfg['Core']['DefaultISO'] = ''
    cfg['Core']['EnableWiiLink'] = 'False'
    cfg['Core']['OverrideRegionSettings'] = 'True'
    for key in ['WiiSDCard', 'WiiSDCardEnableFolderSync', 'WiiSDCardAllowWrites']:
        cfg['Core'][key] = 'False'
    with path.open('w', encoding='utf-8') as f:
        cfg.write(f)
    lib = load_library()
    title = lib.title.Title()
    title.load_wad(wad.read_bytes())
    lib.nand.EmuNAND(BASE / 'user/Wii').install_title(title)
    register()
    launcher.scrub_download_tasks(PROFILE)
    launcher.validate(PROFILE)
    target = BASE / 'local-feed'
    target.mkdir()
    for name in [r['path'] for r in feed['files']] + ['routes.tsv', 'fixture-manifest.json']:
        shutil.copy2(FEED / name, target / name)
    HELPER.mkdir(parents=True)
    (HELPER / 'InternetRunner.cs').write_text(runner_source(), encoding='utf-8')
    (HELPER / 'InternetServer.cs').write_text(server_source(), encoding='utf-8')
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    for source in sorted(HELPER.glob('*.cs')):
        subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x64', '/out:' + str(source.with_suffix('.exe')), str(source)],
                       check=True, capture_output=True)
    locked = [BASE / 'Dolphin-x64/Dolphin.exe', BASE / 'NetProbe.exe', *(p for p in sorted(HELPER.iterdir()) if p.suffix in ('.cs', '.exe')),
              *(target / n for n in sorted(os.listdir(target)))]
    LOCK.write_text(json.dumps(dict(profile=PROFILE, title_id=TITLE, capability_count=0, external_network_allowed=False,
                                    page_server='127.0.0.2:80 inside the same AppContainer', feed_revision=feed['revision'],
                                    files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha256(p)) for p in locked],
                                    builds={'1': manifest['wad_sha256']}), indent=2) + '\n')
    ACTIVE.write_text(json.dumps(dict(revision=1, wad_sha256=manifest['wad_sha256']), indent=2) + '\n')
    if snapshot(TEMPLATE) != before:
        raise ValueError('Template profile changed')
    print('Prepared internet-test-v1: build-v1 installed in a separate Korean profile, local-feed-v1 copied, '
          'zero-capability helper compiled, runtime lock written; template preserved')


if __name__ == '__main__':
    main()

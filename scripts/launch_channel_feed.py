"""Run the verified News personal build with capability-zero HTTP replay.

The original News guards verify installation, system content, credentials,
locale and the pinned runtime. This adds an exact task allowlist, a hashed
24-file local feed and separately locked helper processes.
"""
import argparse
import configparser
import json
import shutil
import subprocess
import sys
from audit_sd import ROOT, PRIVATE, sha256
import launch_dolphin as launcher
from prepare_news import register
sys.path.insert(0, str(ROOT))
from kwce.channel_feed import validate_news_tasks, validate_feed, validate_location_glyphs, patch_text

HELPER = ROOT / 'tools/feed-sandbox/v3/bin'


def configure(user):
    # NAND titles use their four-character title code as Dolphin GameID.
    patch = user / 'GameSettings/HAGE.ini'
    expected = patch_text()
    if patch.exists() and patch.read_text(encoding='utf-8') != expected:
        raise SystemExit('Existing per-game settings differ; preserve and review first')
    ini = user / 'Config/Dolphin.ini'
    cfg = configparser.ConfigParser(strict=False)
    cfg.optionxform = str
    cfg.read(ini, encoding='utf-8-sig')
    # 2609a loads Sys defaults when True and the user's WC24Patch when False.
    # A local replay must use the latter even though the public source is WiiLink.
    if cfg['Core'].get('EnableWiiLink') != 'False':
        backup = PRIVATE / 'news-before-local-feed-v3-Dolphin.ini'
        if backup.exists():
            raise SystemExit('Existing feed configuration snapshot preserved')
        shutil.copy2(ini, backup)
        cfg['Core']['EnableWiiLink'] = 'False'
        with ini.open('w', encoding='utf-8') as stream:
            cfg.write(stream)
    patch.parent.mkdir(exist_ok=True)
    if not patch.exists():
        patch.write_text(expected, encoding='ascii')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('channel', choices=['news'])
    ap.add_argument('--menu', action='store_true')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--country-candidate', action='store_true', help='local-only v22 country fallback diagnostic')
    args = ap.parse_args()
    running = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Dolphin.exe', '/FO', 'CSV', '/NH'], capture_output=True, text=True)
    if 'dolphin.exe' in running.stdout.lower():
        raise SystemExit('Close Dolphin first')
    register()
    user = launcher.user_path('news-v1-user')
    root = user.parent
    active = json.loads((ROOT / 'workspace/channels/news/active-build.json').read_text())
    if active.get('revision') == 22:
        args.country_candidate = True
    if active.get('variant') != 'personal':
        raise SystemExit('Install the personal News build; obsolete file:// test-feed is refused')
    for p in root.rglob('*'):
        if p.is_symlink() or p.is_junction() or p.lstat().st_file_attributes & 0x400:
            raise SystemExit('Indirect sandbox path refused')
    if not args.check:
        # The Korean menu may recreate other channels' scheduled jobs. Disable
        # them in this stopped experiment; the read-only check never writes.
        subprocess.run([sys.executable,str(ROOT/'scripts/prepare_news_feed_tasks.py')],check=True)
    subprocess.run([sys.executable, str(ROOT / 'scripts/launch_news.py'), '--cache-preview', '--check'], check=True)
    validate_news_tasks((user / 'Wii/shared2/wc24/nwc24dl.bin').read_bytes())
    files = validate_feed(root / 'local-feed')
    meta = json.loads((ROOT / f"workspace/channels/news/build-v{active['revision']}/build-manifest.json").read_text(encoding='utf-8'))
    glyphs = validate_location_glyphs(root / 'local-feed', meta.get('location_characters', ''))
    runtime_lock = json.loads((ROOT / 'configs/channel-feed-runtime.lock.json').read_text())
    reference = ROOT / 'workspace/channels/news/references/local-http-v1/WC24PatchEngine.cpp'
    if (runtime_lock.get('runtime_version') != '2609a' or runtime_lock.get('helper_revision') != 3
            or runtime_lock.get('EnableWiiLink') is not False or runtime_lock.get('capability_count') != 0
            or sha256(reference) != runtime_lock['reference_sha256']):
        raise SystemExit('Local feed runtime/reference lock differs')
    helper = ROOT / 'tools/feed-sandbox/v4/bin' if args.country_candidate else HELPER
    if args.country_candidate and (active['revision']!=22 or json.loads((root/'local-feed/feed-manifest.json').read_text()).get('alternate_country')!=49):
        raise SystemExit('Country diagnostic requires v22 and the local-only fixture')
    lock = json.loads((helper / 'helper-build.json').read_text())
    helper_version='v4' if args.country_candidate else 'v3'
    server_source='tools/feed-sandbox/v4/bin/FeedServer-country.cs' if args.country_candidate else 'scripts/FeedServer.cs'
    expected = {'scripts/FeedRunner.cs', server_source,
                f'tools/feed-sandbox/{helper_version}/bin/FeedRunner.exe', f'tools/feed-sandbox/{helper_version}/bin/FeedServer.exe',
                'workspace/sandbox/news-v1/NetProbe.exe'}
    if {r['path'] for r in lock['files']} != expected:
        raise SystemExit('Unexpected feed helper lock entries')
    for row in lock['files']:
        if sha256(ROOT / row['path']) != row['sha256']:
            raise SystemExit('Feed helper changed')
    if args.check:
        print(f'PASS: News installation/runtime/locale/credentials/system, one approved task, {files} feed files, {glyphs} location glyphs, helper {helper_version}; read-only check')
        return
    configure(user)
    env = launcher.proxy_environment()
    env['no_proxy'] += ',127.0.0.2'
    run = 1
    while (PRIVATE / f'news-feed-helper-v3-run-{run}.log').exists():
        run += 1
    with (PRIVATE / f'news-feed-helper-v3-run-{run}.log').open('x', encoding='utf-8') as log:
        p = subprocess.Popen([str(helper / 'FeedRunner.exe'), str(root),
                              'menu' if args.menu else 'channel', '0001000248414745'],
                             cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    print('News capability 0 AppContainer + local HTTP replay started; helper PID', p.pid)


if __name__ == '__main__':
    main()


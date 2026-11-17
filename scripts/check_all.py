"""One-command project check with one line per step (token-light).

Refreshes only the generated Emulator_BAT collection, then runs the unit tests,
every channel launcher's read-only --check, the catalog
installation review and the full SD audit. Each step's output is reduced to
PASS/FAIL plus its last line; the full output of failed steps goes to
workspace/private/check-all/. Dolphin must be stopped (the checks refuse to
inspect a running profile). --quick skips the SD rehash, the unit tests and
the GC prototype hash verification.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable]
STEPS = [
    ('emulator BAT', PY + ['scripts/sync_emulator_bats.py'], True),
    ('unit tests', PY + ['-m', 'unittest', 'discover', '-s', 'tests'], False),
    ('installs', PY + ['scripts/review_channel_installations.py'], True),
    ('gc v6', PY + ['scripts/launch_dolphin.py', '--profile', 'gc-native-v6-user', '--check'], True),
    ('gc v7', PY + ['scripts/launch_dolphin.py', '--profile', 'gc-native-v7-user', '--check'], True),
    ('gc v8 dvd hook', PY + ['scripts/launch_dolphin.py', '--profile', 'gc-native-v8-user', '--check'], True),
    ('dvd test bed', PY + ['scripts/launch_dvd_test.py', '--check'], True),
    ('dvd native menu', PY + ['scripts/launch_dvd_test.py', '--profile', 'dvd-test-v3', '--menu', '--check'], True),
    ('dvd preserved', PY + ['scripts/launch_dvd_test.py', '--profile', 'dvd-test-v2', '--menu', '--check'], True),
    ('gc native', PY + ['scripts/verify_gc_native.py', '--skip-unit-tests'], False),
    ('forecast', PY + ['scripts/launch_forecast.py', '--check'], True),
    ('forecast v22', PY + ['scripts/launch_forecast.py', '--preserved-check'], True),
    ('forecast cache', PY + ['scripts/launch_forecast.py', '--current', '--cache-preview', '--check'], True),
    ('forecast manual', PY + ['scripts/launch_forecast.py', '--manual-capture', '--cache-preview', '--check'], True),
    ('forecast review', PY + ['scripts/launch_forecast.py', '--review', '--cache-preview', '--check'], True),
    ('news', PY + ['scripts/launch_channel_feed.py', 'news', '--check'], True),
    ('votes', PY + ['scripts/run_channel_test.py', 'votes', '--check'], True),
    ('nintendo', PY + ['scripts/run_channel_test.py', 'nintendo', '--check'], True),
    ('mii-contest', PY + ['scripts/run_channel_test.py', 'mii-contest', '--check'], True),
    ('wiiroom', PY + ['scripts/launch_wiiroom.py', '--check'], True),
    ('hardware bed', PY + ['scripts/launch_hardware_test.py', '--check'], True),
    ('dvd hardware', PY + ['scripts/export_dvd_hardware_package.py', '--check'], True),
    ('channel package', PY + ['scripts/export_channel_hardware_package.py', '--check'], True),
    ('news update ZIP', PY + ['scripts/export_news_update_zip.py', '--check'], True),
    ('room update ZIP', PY + ['scripts/export_wiiroom_update.py', '--check'], True),
    ('loading update ZIP', PY + ['scripts/export_loading_update.py', '--check'], True),
    ('vWii package', PY + ['scripts/export_vwii_hardware_package.py', '--check'], True),
    ('mail protocol', PY + ['scripts/check_wii_mail.py'], False),
    ('mail preview', PY + ['scripts/launch_wii_mail_preview.py', '--check'], True),
    ('mail package', PY + ['scripts/package_wii_mail_tool.py', '--check'], True),
    ('tvguide', PY + ['scripts/launch_tvguide.py', '--check'], True),
    ('personal-data', PY + ['scripts/launch_personal_data.py', '--check'], True),
    ('internet', PY + ['scripts/launch_internet.py', '--check'], True),
    ('kirbytv', PY + ['scripts/launch_kirbytv.py', '--check'], True),
    ('photoprints', PY + ['scripts/launch_photoprints.py', '--check'], True),
    ('food', PY + ['scripts/launch_food.py', '--check'], True),
    ('wiispeak hw', PY + ['scripts/build_wiispeak.py', '--verify'], False),
    ('wiispeak bed', PY + ['scripts/launch_wiispeak.py', '--check'], True),
    ('sd audit', PY + ['scripts/audit_sd.py', '--verify'], False),
]


def main():
    if sys.platform == 'linux':
        from check_linux_environment import main as linux_main
        raise SystemExit(linux_main())
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', action='store_true', help='skip unit tests, GC hash verification and the SD rehash')
    args = parser.parse_args()
    running = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Dolphin.exe', '/FO', 'CSV', '/NH'], capture_output=True).stdout or b''
    if b'dolphin.exe' in running.lower():
        raise SystemExit('Close Dolphin first')
    logs = ROOT / 'workspace/private/check-all'
    logs.mkdir(parents=True, exist_ok=True)
    failed = 0
    for name, command, quick in STEPS:
        if args.quick and not quick:
            continue
        start = time.time()
        done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
        text = (done.stdout + done.stderr).strip()
        last = text.splitlines()[-1][:110] if text else ''
        ok = done.returncode == 0
        failed += not ok
        if not ok:
            (logs / f"{name.replace(' ', '-')}.log").write_text(text, encoding='utf-8')
        print(f"{'PASS' if ok else 'FAIL'} {name:<12} {time.time() - start:5.1f}s  {last}", flush=True)
    print('ALL PASS' if not failed else f'{failed} FAILED (logs: workspace/private/check-all/)')
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()

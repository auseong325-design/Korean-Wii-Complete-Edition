"""Refresh public weather and open the isolated Korean forecast preview."""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script, *args):
    subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *args],
                   cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--menu', action='store_true', help='Wii menu/banner inspection only')
    parser.add_argument('--offline', action='store_true',help='reuse a verified saved snapshot with a historical test clock; no host network')
    args = parser.parse_args()
    current=(ROOT/'workspace/sandbox/forecast-v2/current-profile.json').exists()
    options=['--current']if current else[]
    if args.offline and not current:raise SystemExit('Prepare the current Korean weather profile before offline testing')
    if args.menu and not args.offline:
        run('launch_forecast.py',*options,'--menu')
        return
    running = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Dolphin.exe',
                              '/FO', 'CSV', '/NH'], capture_output=True, text=True)
    if running.returncode:
        raise SystemExit('Could not check running Dolphin processes')
    if 'dolphin.exe' in running.stdout.lower():
        raise SystemExit('Close Dolphin before refreshing the forecast test')
    attempt = next((i for i in range(2, 101) if not
                    (ROOT / f'workspace/private/forecast-{"current-"if current else""}before-sdk-replay-{i}').exists()), None)
    if attempt is None:
        raise SystemExit('No unused forecast snapshot number remains')
    if not args.offline:run('refresh_public_forecast.py')
    offline=['--offline']if args.offline else[]
    menu=['--menu']if args.menu else[]
    run('seed_forecast_cache.py',*options,*offline,'--attempt', str(attempt), '--localized')
    if args.offline:print('Historical public snapshot test only; not current weather or emulator online success',flush=True)
    run('launch_forecast.py',*options,*menu,'--cache-preview', '--check')
    run('launch_forecast.py',*options,*menu,'--cache-preview')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode)

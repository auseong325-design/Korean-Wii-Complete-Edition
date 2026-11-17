"""Resolve one generated BAT action to the current approved project launcher."""
import argparse,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.emulator_shortcuts import load_plans,synchronize


def main():
    ap=argparse.ArgumentParser();ap.add_argument('shortcut');ap.add_argument('--dry-run',action='store_true');args=ap.parse_args()
    entries=load_plans(ROOT)
    if args.shortcut not in entries:raise SystemExit('Shortcut is no longer active; run Update_BAT.bat')
    row=entries[args.shortcut];argv=row['argv']
    if argv and not(ROOT/argv[0]).is_file():raise SystemExit('Approved project launcher is missing')
    print(row['label']+' | '+row.get('profile','project')+' | '+row.get('artifact',''),flush=True)
    if row.get('blocked'):print('주의: 최신 시험본이지만 내부 진입 오류로 보류 중입니다.',flush=True)
    if args.dry_run or os.environ.get('KWCE_BAT_DRY_RUN')=='1':
        print('DRY RUN: '+(' '.join(argv)if argv else'synchronize BAT collection'));return 0
    synchronize(ROOT)
    if not argv:print('BAT collection is up to date.');return 0
    # No shell, raw Dolphin.exe, WAD installation or SD deployment here.
    return subprocess.run([sys.executable,'-X','utf8',str(ROOT/argv[0]),*argv[1:]],cwd=ROOT,
        env=dict(os.environ,PYTHONUTF8='1')).returncode


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,KeyError):raise SystemExit('Shortcut refused: check the active catalog and project launchers')from None

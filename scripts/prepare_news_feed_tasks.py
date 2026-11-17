"""Disable non-News jobs recreated by the stopped test menu; preserve News."""
import subprocess
import shutil
import sys
from audit_sd import ROOT, PRIVATE
sys.path.insert(0, str(ROOT))
from kwce.channel_feed import normalize_news_tasks
from prepare_news import register
import launch_dolphin as launcher


def main():
    running = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Dolphin.exe', '/FO', 'CSV', '/NH'], capture_output=True, text=True)
    if 'dolphin.exe' in running.stdout.lower():
        raise SystemExit('Close Dolphin first')
    register();user=launcher.user_path('news-v1-user')
    path = user / 'Wii/shared2/wc24/nwc24dl.bin'
    for part in [path,*path.parents]:
        if part.is_symlink()or part.is_junction():raise SystemExit('Indirect News task path refused')
        if part==user:break
    data,count=normalize_news_tasks(path.read_bytes())
    if count:
        attempt=1
        while(PRIVATE/f'news-before-menu-task-normalization-{attempt}.bin').exists():attempt+=1
        backup = PRIVATE / f'news-before-menu-task-normalization-{attempt}.bin'
        shutil.copy2(path, backup)
        path.write_bytes(data)
    print(f'Disabled {count} non-News tasks; exactly one approved public News task remains')


if __name__ == '__main__':
    main()

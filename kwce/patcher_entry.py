"""KWCE 패처 — Windows 꾸러미 진입점 (꾸러미 안에서는 app/run.py). 꾸러미 v5부터.

WiiLink Patcher처럼 단계별로 묻는다: ① 내보낼 위치(SD 카드 / USB 드라이브 자동 인식, 또는 이 폴더)
② 다운로드·패치(진행 막대) ③ 완료 화면(다음 할 일, 폴더 열기). 결과는 언제나 꾸러미 폴더의
"SD카드에 복사할 파일"에 먼저 만들고, 모든 파일의 해시가 맞을 때만 SD에 복사한다. SD에서는 아무것도
지우지 않고, 같은 이름의 파일만 새 것으로 바꾼다. 이 도구는 아무것도 업로드하지 않는다.
옵션: --sd <드라이브|none> --yes (묻지 않고 기본값), --bundle --out --cache.
"""
import argparse
import hashlib
import json
import os
import shutil
import string
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent
PKG = APP.parent
OUT_NAME = 'SD카드에 복사할 파일'
CACHE_NAME = '받은 원본'
WORK_NAME = '.작업 중 (지워도 됨)'
LINE = '=' * 56

CHANNELS = {
    'forecast': '날씨 채널', 'news': '뉴스 채널', 'votes': '모두의 투표 채널', 'mii-contest': 'Mii 콘테스트 채널',
    'wiiroom': 'Wii의 방', 'nintendo': '닌텐도 채널', 'food': '음식 배달 채널', 'kirbytv': '커비 TV 채널',
    'internet': '인터넷 채널', 'photoprints': '사진 프린트 채널', 'wiispeak': 'Wii 스피크 채널',
    'tvguide': 'TV 가이드 채널', 'personal-data': '주소 설정 채널', 'dvd-player': 'DVD 재생',
}


class Quit(Exception):
    pass


# ------------------------------------------------------------------ console
def _utf8_console():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def ask(prompt, choices, default, auto):
    """Number menu like WiiLink Patcher. auto=True (or no console) takes the default."""
    if auto:
        print(f'{prompt} {default} (자동)')
        return default
    while True:
        try:
            a = input(f'{prompt} [기본 {default}] ').strip()
        except EOFError:
            return default
        if not a:
            return default
        if a in choices:
            return a
        print(f'  {"/".join(choices)} 중에서 고르세요.')


def gb(n): return f'{n / 1e9:.1f}GB'


# ------------------------------------------------------------------ drives
def find_drives():
    """SD 카드 / USB 드라이브 후보(Windows). 이동식이거나, 루트에 apps 폴더가 있거나, 이름에 WII가 든 드라이브.
    시스템 드라이브는 뺀다. 일부 카드 리더는 이동식으로 보고하지 않아 apps 폴더·이름으로도 찾는다."""
    if sys.platform != 'win32':
        return []
    import ctypes
    k = ctypes.windll.kernel32
    sysdrive = os.environ.get('SystemDrive', 'C:').upper().rstrip('\\') + '\\'
    mask, out = k.GetLogicalDrives(), []
    for i, letter in enumerate(string.ascii_uppercase):
        if not mask >> i & 1:
            continue
        root = f'{letter}:\\'
        kind = k.GetDriveTypeW(root)
        if root == sysdrive or kind not in (2, 3):          # 2 removable, 3 fixed
            continue
        label, fs = ctypes.create_unicode_buffer(261), ctypes.create_unicode_buffer(261)
        if not k.GetVolumeInformationW(root, label, 261, None, None, None, fs, 261):
            continue                                          # no media in the reader
        free = ctypes.c_ulonglong(0)
        k.GetDiskFreeSpaceExW(root, ctypes.byref(free), None, None)
        has_apps = os.path.isdir(root + 'apps')
        if kind == 2 or has_apps or 'WII' in label.value.upper():
            out.append(dict(path=root, label=label.value, fs=fs.value, free=free.value,
                            removable=kind == 2, has_apps=has_apps))
    return sorted(out, key=lambda d: (not d['has_apps'], not d['removable'], d['path']))


def describe(d):
    bits = [d['label'] or '이름 없음', d['fs'], f"{gb(d['free'])} 남음"]
    if d['has_apps']:
        bits.append('apps 폴더 있음')
    return f"{d['path']}  ({', '.join(bits)})"


def choose_target(drives, sd_arg, auto):
    """'none' (이 폴더만) 또는 드라이브 루트 경로."""
    if sd_arg:
        if sd_arg.lower() == 'none':
            return None
        p = sd_arg if sd_arg.endswith(('\\', '/')) else (sd_arg + '\\' if len(sd_arg) == 2 else sd_arg)
        if not os.path.isdir(p):
            raise Quit(f'드라이브를 찾지 못했습니다: {sd_arg}')
        return p
    print('[1단계] 내보낼 위치 선택')
    if drives:
        print('  SD 카드 / USB 드라이브를 찾았습니다. 만든 파일을 바로 복사할 수 있습니다.')
    else:
        print('  SD 카드를 찾지 못했습니다. 카드를 꽂고 이 창을 다시 열거나, 이 폴더에 저장하세요.')
    options = {}
    for n, d in enumerate(drives, 1):
        options[str(n)] = d['path']
        print(f"  {n}. {describe(d)}" + ('   ← 권장' if n == 1 else ''))
    local = str(len(drives) + 1)
    options[local] = None
    print(f'  {local}. 이 폴더에만 저장 (나중에 직접 SD 카드에 복사)')
    pick = ask('  번호를 고르고 Enter:', list(options), '1', auto)
    return options[pick]


# ------------------------------------------------------------------ build
def manifest(bundle):
    return json.loads((Path(bundle) / 'manifest.json').read_bytes())


def output_ok(out, m):
    """Existing output is reusable only if every file is present with the expected hash."""
    out = Path(out)
    for rel, rec in m['files'].items():
        p = out / rel
        if not p.is_file() or p.stat().st_size != rec['size'] or hashlib.sha256(p.read_bytes()).hexdigest() != rec['sha256']:
            return False
    return True


class Progress:
    """apply_bundle log lines -> one progress bar + download lines."""

    def __init__(self, total):
        self.total = total; self.t0 = time.time()

    def __call__(self, line):
        s = line.strip()
        if s.startswith('받는 중:'):
            print(f'\r  {s[len("받는 중:"):].strip()} 다운로드 중...' + ' ' * 20)
        elif s.startswith('[') and '/' in s and ']' in s:
            done = int(s[1:s.index('/')]); rel = s[s.index(']') + 1:].strip()
            part = rel.split('/')
            name = CHANNELS.get(part[1], '') if len(part) > 2 and part[0] == 'kwce-rc' else ''
            label = f'{name} 패치 중' if name else '파일 만드는 중'
            bar = '#' * (done * 30 // self.total)
            print(f'\r  [{bar:<30}] {done * 100 // self.total:3d}%  {label:<24}', end='', flush=True)
            if done == self.total:
                print()
        elif s:
            print('  ' + s)


def is_network_error(e):
    names = {type(x).__name__ for x in (e, e.__cause__, e.__context__) if x is not None}
    return bool(names & {'URLError', 'ConnectionError', 'Timeout', 'ConnectTimeout', 'ReadTimeout',
                         'SSLError', 'gaierror', 'TimeoutError', 'ConnectionResetError', 'HTTPError'})


def build(bundle, out, cache, m, auto, apply=None):
    """Make out/ (reusing a complete earlier result). Returns True when out/ is ready."""
    if apply is None:
        from kwce import public_patch as pp
        apply = pp.apply_bundle
    print('[2단계] 다운로드·패치')
    if out.exists() and any(out.iterdir()):
        print('  이 폴더에 이미 만든 파일이 있어 확인하는 중...')
        if output_ok(out, m):
            print('  이전에 만든 파일이 그대로 맞습니다. 다시 만들지 않습니다.')
            return True
        print(f'  "{out.name}" 폴더가 이번 묶음과 다릅니다(다른 판이거나 바뀐 파일).')
        if ask('  1. 지우고 새로 만들기  2. 그만두기:', ['1', '2'], '1', auto) != '1':
            raise Quit('그만뒀습니다. 아무것도 바꾸지 않았습니다.')
        shutil.rmtree(out)
    work = out.parent / WORK_NAME
    if work.exists():
        shutil.rmtree(work)                       # 이전에 실패한 실행의 임시 폴더(이 도구가 만든 것)
    print('  닌텐도 업데이트 서버와 WiiLink 서버에서 원본을 받아 패치합니다.')
    print('  처음에는 약 430MB를 받아 몇 분 걸립니다. 받은 원본은 다음에 다시 쓰입니다.')
    try:
        apply(bundle, work, cache, Progress(len(m['files'])))
    except Exception as e:
        print()
        shutil.rmtree(work, ignore_errors=True)
        if is_network_error(e):
            raise Quit(f'서버에 연결하지 못했습니다({type(e).__name__}). 인터넷 연결을 확인하고 다시 실행하세요. '
                       '이미 받은 원본은 남아 있어 다시 받지 않습니다.')
        raise Quit(str(e))
    if out.exists():
        out.rmdir()
    work.rename(out)
    print(f'  모든 파일({len(m["files"])}개)의 해시가 맞습니다.')
    return True


# ------------------------------------------------------------------ copy to SD
def copy_to(out, target, m, auto):
    """Add/replace files on the SD card. Never deletes. Re-reads every written file."""
    print(f'[3단계] SD 카드에 복사: {target}')
    out, target = Path(out), Path(target)
    print('  SD 카드에 이미 있는 파일을 확인하는 중...')
    todo, same = [], 0
    for rel, rec in sorted(m['files'].items()):
        dst = target / rel
        if dst.is_file() and dst.stat().st_size == rec['size'] and hashlib.sha256(dst.read_bytes()).hexdigest() == rec['sha256']:
            same += 1
        else:
            todo.append((rel, rec, dst.exists()))
    need = sum(rec['size'] for _, rec, _ in todo)
    free = shutil.disk_usage(target).free
    replace = sum(1 for *_, exists in todo if exists)
    print(f'  새로 쓸 파일 {len(todo)}개({gb(need)}), 이미 같은 파일 {same}개' + (f', 새 판으로 바꿀 파일 {replace}개' if replace else ''))
    print('  SD 카드의 다른 파일은 지우지 않습니다.')
    if need > free:
        raise Quit(f'SD 카드 공간이 부족합니다(필요 {gb(need)}, 남음 {gb(free)}). 공간을 비운 뒤 다시 실행하세요. '
                   f'만든 파일은 "{out}"에 있습니다.')
    if todo and ask('  1. 복사하기  2. 복사하지 않기:', ['1', '2'], '1', auto) != '1':
        return False
    for n, (rel, rec, _) in enumerate(todo, 1):
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out / rel, dst)
        if hashlib.sha256(dst.read_bytes()).hexdigest() != rec['sha256']:
            raise Quit(f'SD 카드에 쓴 파일을 다시 읽었더니 다릅니다: {rel}. 카드 상태를 확인하세요.')
        print(f'\r  [{"#" * (n * 30 // len(todo)):<30}] {n * 100 // len(todo):3d}%', end='', flush=True)
    if todo:
        print()
    print('  복사한 파일을 모두 다시 읽어 확인했습니다.')
    return True


# ------------------------------------------------------------------ main
def finish(out, target, copied, auto):
    print()
    print(LINE)
    print('  패치 완료되었습니다!')
    print(LINE)
    if target and copied:
        print(f'  SD 카드({target})에 모두 복사했습니다. 작업 표시줄의 "하드웨어 안전 제거"로 카드를 꺼내세요.')
    else:
        print(f'  "{out.name}" 폴더 안의 내용(apps, kwce, kwce-rc 등)을 SD 카드 맨 위에 복사하세요.')
    print('  다음 할 일 (Wii):')
    print('    1. SD 카드를 Wii에 꽂고 홈브류 채널을 엽니다.')
    print('    2. KWCE Channel Installer → +(START) → 1 = 전체 설치')
    print('    3. 게임큐브·DVD 기능은 -(GC L) 버튼으로 디스크 채널 모드를 고릅니다.')
    print('  자세한 설명: README-ko.txt')
    if sys.platform == 'win32' and not auto:
        if ask('  1. 폴더 열고 닫기  2. 그냥 닫기:', ['1', '2'], '2', auto) == '1':
            os.startfile(target if target and copied else out)


def main(argv=None):
    _utf8_console()
    sys.dont_write_bytecode = True
    ap = argparse.ArgumentParser(description='KWCE 패처: 한국판 Wii용 KWCE 파일을 만든다.')
    ap.add_argument('--bundle', default=str(PKG / 'bundle'))
    ap.add_argument('--out', default=str(PKG / OUT_NAME))
    ap.add_argument('--cache', default=str(PKG / CACHE_NAME))
    ap.add_argument('--sd', help='SD 카드 드라이브(예: E:) 또는 none(이 폴더에만 저장)')
    ap.add_argument('--yes', action='store_true', help='묻지 않고 기본값으로 진행')
    a = ap.parse_args(argv)
    auto = a.yes or not sys.stdin or not sys.stdin.isatty()
    try:
        info = json.loads((APP / 'build-info.json').read_bytes())
        ver = f" — {info.get('patcher', '')}"
    except (OSError, ValueError):
        ver = ''
    print(LINE)
    print(f'  KWCE 패처 (베타){ver}')
    print('  Korean Wii Complete Edition — 한국판 Wii(시스템 메뉴 4.3K)용')
    print(LINE)
    print('  한국어 WiiConnect24 채널과 게임큐브·DVD 기능을 설치할 파일을 만듭니다.')
    print('  온라인 기능은 WiiLink 서비스를 이용합니다. WiiLink 팀에 감사드립니다.')
    print()
    out, bundle, cache = Path(a.out), Path(a.bundle), Path(a.cache)
    try:
        if not (bundle / 'manifest.json').is_file():
            raise Quit(f'패치 묶음을 찾지 못했습니다: {bundle}. zip의 압축을 모두 푼 뒤 실행하세요.')
        m = manifest(bundle)
        target = choose_target(find_drives(), a.sd, auto)
        print()
        build(bundle, out, cache, m, auto)
        print()
        copied = copy_to(out, target, m, auto) if target else False
        finish(out, target, copied, auto)
        return 0
    except Quit as e:
        print()
        print(f'  중단: {e}')
        return 1                                   # KWCE-Patcher.bat pauses on any non-zero exit
    except KeyboardInterrupt:
        print('\n  중단했습니다.')
        return 1
    except Exception as e:                         # unexpected: show it instead of a vanishing window
        import traceback
        traceback.print_exc()
        print(f'\n  예상하지 못한 오류: {e}')
        return 2


if __name__ == '__main__':
    if str(APP) not in sys.path:
        sys.path.insert(0, str(APP))
    raise SystemExit(main())

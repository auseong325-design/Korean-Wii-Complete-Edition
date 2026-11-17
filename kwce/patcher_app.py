"""KWCE 패처 — Windows 꾸러미 진입점 (꾸러미 안에서는 app/run.py). 꾸러미 v6부터.

WiiLink Patcher처럼 단계별로 묻는다.
  ① 설치 구성: 빠른 설정(채널 전체 + 게임큐브·DVD) / 게임큐브·DVD만(채널 없이, 받는 양 약 20MB)
  ② 내보낼 위치: SD 카드 / USB 드라이브 자동 인식, 또는 이 폴더
  ③ 다운로드·패치(진행 막대)  ④ SD 카드에 복사  ⑤ 완료 화면(Wii에서 할 일)
결과는 먼저 꾸러미 폴더에 만들고, 모든 파일의 해시가 맞을 때만 SD에 복사한다. SD에서는 아무것도 지우지
않고 같은 이름의 파일만 새 것으로 바꾼다. SD에 복사할 때 그 카드의 Priiloader 핵 파일
(apps/priiloader/hacks_hash.ini)에 KWCE 항목을 더한 디스크 채널 모드 파일 두 개를 만든다
(kwce/priiloader_profile.py: Priiloader 0.8.2·0.10 모두 같은 바이트로 읽는 형식, 기존 핵은 그대로).
옵션: --mode full|gc  --sd <드라이브|none>  --yes(묻지 않고 기본값)  --bundle --out --cache.
이 도구는 아무것도 업로드하지 않는다.
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
OUT_NAMES = {'full': 'SD카드에 복사할 파일', 'gc': 'SD카드에 복사할 파일 (게임큐브·DVD)'}
CACHE_NAME = '받은 원본'
WORK_NAME = '.작업 중 (지워도 됨)'
LINE = '=' * 56
PRII_CARD = 'apps/priiloader/hacks_hash.ini'
PROFILES = {'gc-only': 'kwce-rc/priiloader/gc-only.ini', 'gc-dvd': 'kwce-rc/priiloader/gc-dvd.ini'}

CHANNELS = {
    'forecast': '날씨 채널', 'news': '뉴스 채널', 'votes': '모두의 투표 채널', 'mii-contest': 'Mii 콘테스트 채널',
    'wiiroom': 'Wii의 방', 'nintendo': '닌텐도 채널', 'food': '음식 배달 채널', 'kirbytv': '커비 TV 채널',
    'internet': '인터넷 채널', 'photoprints': '사진 프린트 채널', 'wiispeak': 'Wii 스피크 채널',
    'tvguide': 'TV 가이드 채널', 'personal-data': '주소 설정 채널', 'dvd-player': 'DVD 재생',
}
GC_PREFIXES = ('apps/kwce-installer-rc/', 'kwce/dvd/', 'kwce-rc/priiloader/')
GC_FILES = ('kwce-rc/versions.txt', 'kwce-rc/editions.txt', 'KWCE-RC-README-ko.txt')
GC_SKIP = b'KWCE WiiLink question answered: GameCube/DVD only package. Delete this file to be asked again.\n'


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


def gb(n): return f'{n / 1e9:.1f}GB' if n >= 1e8 else f'{n / 1e6:.0f}MB'


def sha(b): return hashlib.sha256(b).hexdigest()


# ------------------------------------------------------------------ plan
class Plan:
    """What to make: the bundle files of one mode + generated extras (rel -> bytes)."""

    def __init__(self, m, mode):
        self.mode = mode
        if mode == 'full':
            self.files = dict(m['files'])
        else:
            self.files = {k: v for k, v in m['files'].items() if k.startswith(GC_PREFIXES) or k in GC_FILES}
        self.extras = {}
        if mode == 'gc':  # installer needs one package line; the legacy DVD line is remove-only
            pk = [l for l in packages_lines(m) if l.startswith('#') or l.startswith('dvd-player|')]
            self.extras['kwce-rc/packages.txt'] = ('\n'.join(pk) + '\n').encode()
        self.size = sum(r['size'] for r in self.files.values())


def packages_lines(m):
    return [l for l in m.get('_packages', '').splitlines() if l]


def choose_mode(mode_arg, auto):
    if mode_arg:
        return mode_arg
    print('[1단계] 설치 구성 선택')
    print('  1. 빠른 설정 (권장) — 한국어 채널 전체 + 게임큐브·DVD 기능')
    print('  2. 게임큐브·DVD만 — 채널은 받지 않습니다 (받는 양 약 20MB)')
    return {'1': 'full', '2': 'gc'}[ask('  번호를 고르고 Enter:', ['1', '2'], '1', auto)]


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
    if d['fs'] and d['fs'].upper() not in ('FAT32', 'FAT'):
        bits.append('⚠ Wii는 FAT32만 읽음')
    return f"{d['path']}  ({', '.join(bits)})"


def choose_target(drives, sd_arg, auto):
    """None (이 폴더만) 또는 드라이브 루트 경로."""
    if sd_arg:
        if sd_arg.lower() == 'none':
            return None
        p = sd_arg if sd_arg.endswith(('\\', '/')) else (sd_arg + '\\' if len(sd_arg) == 2 else sd_arg)
        if not os.path.isdir(p):
            raise Quit(f'드라이브를 찾지 못했습니다: {sd_arg}')
        return p
    print('[2단계] 내보낼 위치 선택')
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
    bundle = Path(bundle)
    m = json.loads((bundle / 'manifest.json').read_bytes())
    pk = bundle / 'files/kwce-rc/packages.txt'
    m['_packages'] = pk.read_text(encoding='utf-8') if pk.is_file() else ''
    return m


def file_ok(p, rec):
    return p.is_file() and p.stat().st_size == rec['size'] and sha(p.read_bytes()) == rec['sha256']


def output_ok(out, plan):
    """Existing output is reusable only if every planned file is present with the expected hash."""
    out = Path(out)
    return all(file_ok(out / rel, rec) for rel, rec in plan.files.items()) and all(
        (out / rel).is_file() and (out / rel).read_bytes() == data for rel, data in plan.extras.items())


def apply_plan(bundle, work, cache, plan, log):
    """public_patch.apply_bundle for the planned files only (same checks, same order rule)."""
    from kwce import public_patch as pp
    bundle, work = Path(bundle), Path(work)
    raw = (bundle / 'manifest.json').read_bytes()
    if pp.sha256(raw) != (bundle / 'manifest.sha256').read_text().strip():
        raise ValueError('패치 묶음 manifest가 손상됐습니다')
    m = json.loads(raw)
    for rel, rec in plan.files.items():
        toks = list(rec.get('dict', [])) + [t for c in rec.get('contents', []) for t in c.get('dict', [])]
        for t in toks:
            if t.startswith('file:') and t[5:] not in plan.files:
                raise ValueError(f'{rel}: needs {t[5:]} in the same plan')
    bases = pp.Bases(cache, m['bases'], log)
    dicts = pp.Dicts(pp.Wad(pp._base_bytes(bases, m['sysmenu'])), work)
    order = sorted(plan.files.items(), key=lambda kv: (pp._needs_files(kv[1]), kv[1]['mode'] == 'wad',
                                                       kv[1].get('base') or '', kv[0]))
    for done, (rel, rec) in enumerate(order, 1):
        if rec['mode'] == 'wad':
            data = pp.apply_wad_recipe(rec, bases, dicts, bundle)
        elif rec['mode'] == 'copy':
            data = dicts.sysmenu.dec(rec['sys'])
        elif rec['mode'] == 'delta':
            data = pp.apply_delta(dicts.resolve(rec['dict']), (bundle / 'patch' / rec['patch']).read_bytes(), rec['size'])
        else:
            data = (bundle / 'files' / rel).read_bytes()
        if pp.sha256(data) != rec['sha256']:
            raise ValueError(f'{rel}: 결과가 기대한 해시와 다릅니다. 이 파일은 만들지 않습니다')
        p = work / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
        log(f'  [{done}/{len(order)}] {rel}')
    for rel, data in plan.extras.items():
        p = work / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)


class Progress:
    """apply log lines -> one progress bar + download lines."""

    def __init__(self, total):
        self.total = max(total, 1)

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


def build(bundle, out, cache, plan, auto, apply=None):
    """Make out/ (reusing a complete earlier result)."""
    apply = apply or apply_plan
    print('[3단계] 다운로드·패치')
    if out.exists() and any(out.iterdir()):
        print('  이 폴더에 이미 만든 파일이 있어 확인하는 중...')
        if output_ok(out, plan):
            print('  이전에 만든 파일이 그대로 맞습니다. 다시 만들지 않습니다.')
            return
        print(f'  "{out.name}" 폴더가 이번 묶음과 다릅니다(다른 판이거나 바뀐 파일).')
        if ask('  1. 지우고 새로 만들기  2. 그만두기:', ['1', '2'], '1', auto) != '1':
            raise Quit('그만뒀습니다. 아무것도 바꾸지 않았습니다.')
        shutil.rmtree(out)
    work = out.parent / WORK_NAME
    if work.exists():
        shutil.rmtree(work)                       # 이전에 실패한 실행의 임시 폴더(이 도구가 만든 것)
    if plan.mode == 'full':
        print('  닌텐도 업데이트 서버와 WiiLink 서버에서 원본을 받아 패치합니다.')
        print('  처음에는 약 430MB를 받아 몇 분 걸립니다. 받은 원본은 다음에 다시 쓰입니다.')
    else:
        print('  닌텐도 업데이트 서버에서 시스템 메뉴 원본(약 20MB)을 받아 필요한 파일을 만듭니다.')
    try:
        apply(bundle, work, cache, plan, Progress(len(plan.files)))
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
    print(f'  모든 파일({len(plan.files)}개)의 해시가 맞습니다.')


# ------------------------------------------------------------------ copy to SD
def write_checked(dst, data):
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    if dst.read_bytes() != data:
        raise Quit(f'SD 카드에 쓴 파일을 다시 읽었더니 다릅니다: {dst}. 카드 상태를 확인하세요.')


def copy_to(out, target, plan, auto):
    """Add/replace files on the SD card. Never deletes. Re-reads every written file."""
    print(f'[4단계] SD 카드에 복사: {target}')
    out, target = Path(out), Path(target)
    print('  SD 카드에 이미 있는 파일을 확인하는 중...')
    todo, same = [], 0
    for rel, rec in sorted(plan.files.items()):
        if file_ok(target / rel, rec):
            same += 1
        else:
            todo.append((rel, rec, (target / rel).exists()))
    need = sum(rec['size'] for _, rec, _ in todo)
    free = shutil.disk_usage(target).free
    replace = sum(1 for *_, exists in todo if exists)
    print(f'  새로 쓸 파일 {len(todo)}개({gb(need)}), 이미 같은 파일 {same}개'
          + (f', 새 판으로 바꿀 파일 {replace}개' if replace else ''))
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
        if not file_ok(dst, rec):
            raise Quit(f'SD 카드에 쓴 파일을 다시 읽었더니 다릅니다: {rel}. 카드 상태를 확인하세요.')
        print(f'\r  [{"#" * (n * 30 // len(todo)):<30}] {n * 100 // len(todo):3d}%', end='', flush=True)
    if todo:
        print()
    for rel, data in plan.extras.items():
        dst = target / rel
        if rel == 'kwce-rc/packages.txt' and dst.is_file() and (target / 'kwce-rc/forecast/korean.wad').is_file():
            continue                              # a full KWCE card keeps its full channel list
        write_checked(dst, data)
    if plan.mode == 'gc' and not (target / 'kwce-rc/wiilink-skip.txt').exists():
        write_checked(target / 'kwce-rc/wiilink-skip.txt', GC_SKIP)
    print('  복사한 파일을 모두 다시 읽어 확인했습니다.')
    disc_profiles(target, plan)
    return True


def disc_profiles(target, plan):
    """gc-only.ini / gc-dvd.ini for THIS card: its Priiloader hacks kept, KWCE disc entries added."""
    from kwce.priiloader_profile import build_profile, other_sections
    card_file = target / PRII_CARD                 # Windows paths are case-insensitive (apps/Priiloader too)
    card = card_file.read_bytes() if card_file.is_file() else None
    for mode, rel in PROFILES.items():
        frag = (target / f'kwce-rc/priiloader/fragment-{mode}.ini').read_bytes()
        write_checked(target / rel, build_profile(card, frag))
    card_file.parent.mkdir(parents=True, exist_ok=True)   # the installer writes the active file here
    if card is None:
        print('  Priiloader 핵 파일이 SD에 없어, 디스크 채널 모드 파일에는 KWCE 항목만 넣었습니다.')
    else:
        n = sum(1 for line in other_sections(card).split('\n') if line.startswith('['))
        print(f'  디스크 채널 모드 파일을 만들었습니다(이 카드의 Priiloader 핵 {n}개는 그대로).')


# ------------------------------------------------------------------ main
def finish(out, target, copied, plan, auto):
    print()
    print(LINE)
    print('  패치 완료되었습니다!')
    print(LINE)
    if target and copied:
        print(f'  SD 카드({target})에 모두 복사했습니다. 작업 표시줄의 "하드웨어 안전 제거"로 카드를 꺼내세요.')
    else:
        print(f'  "{out.name}" 폴더 안의 내용(apps, kwce, kwce-rc 등)을 SD 카드 맨 위에 복사하세요.')
        print('  게임큐브·DVD 기능을 쓰려면 SD 카드를 꽂고 이 패처를 한 번 더 실행해 SD로 복사하세요.')
        print('  (그 카드의 Priiloader 설정을 지키는 파일을 그때 만듭니다. 이미 만든 파일은 다시 받지 않습니다.)')
    print('  다음 할 일 (Wii):')
    print('    1. SD 카드를 Wii에 꽂고 홈브류 채널 → KWCE Channel Installer')
    if plan.mode == 'full':
        print('    2. +(START) → 1 = 전체 설치')
        print('    3. 게임큐브·DVD: -(GC L) → 1 게임큐브만 / 2 게임큐브+DVD')
    else:
        print('    2. -(GC L) → 1 게임큐브만 / 2 게임큐브+DVD')
    print('    마지막으로 RESET을 누른 채 전원을 켜서 Priiloader → System Menu Hacks에서')
    print('    KWCE 항목을 켜고 저장합니다. (쓰던 다른 핵도 켜져 있는지 확인하세요.)')
    print('  자세한 설명: README-ko.txt')
    if sys.platform == 'win32' and not auto:
        if ask('  1. 폴더 열고 닫기  2. 그냥 닫기:', ['1', '2'], '2', auto) == '1':
            os.startfile(target if target and copied else out)


def main(argv=None):
    _utf8_console()
    sys.dont_write_bytecode = True
    ap = argparse.ArgumentParser(description='KWCE 패처: 한국판 Wii용 KWCE 파일을 만든다.')
    ap.add_argument('--bundle', default=str(PKG / 'bundle'))
    ap.add_argument('--out', help='결과 폴더 (기본: 꾸러미 폴더 안)')
    ap.add_argument('--cache', default=str(PKG / CACHE_NAME))
    ap.add_argument('--mode', choices=['full', 'gc'], help='full = 채널 전체 + 게임큐브·DVD, gc = 게임큐브·DVD만')
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
    bundle, cache = Path(a.bundle), Path(a.cache)
    try:
        if not (bundle / 'manifest.json').is_file():
            raise Quit(f'패치 묶음을 찾지 못했습니다: {bundle}. zip의 압축을 모두 푼 뒤 실행하세요.')
        m = manifest(bundle)
        plan = Plan(m, choose_mode(a.mode, auto))
        out = Path(a.out) if a.out else PKG / OUT_NAMES[plan.mode]
        print()
        target = choose_target(find_drives(), a.sd, auto)
        print()
        build(bundle, out, cache, plan, auto)
        print()
        copied = copy_to(out, target, plan, auto) if target else False
        finish(out, target, copied, plan, auto)
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

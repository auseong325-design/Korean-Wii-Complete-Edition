"""KWCE 패처 — Windows 꾸러미 진입점 (꾸러미 안에서는 app/run.py). 꾸러미 v7부터(v6은 patcher_app.py).

WiiLink Patcher처럼 단계별로 묻는다.
  ① 설치 구성: 빠른 설정(채널 전체 + 게임큐브·DVD) / 게임큐브·DVD만(채널 없이, 받는 양 약 20MB) /
     원래대로 되돌리기(SD 상태 확인 + Wii에서 할 일 안내, 아무것도 받거나 쓰지 않음)
  ② 내보낼 위치: SD 카드 / USB 드라이브 자동 인식, 또는 이 폴더
  ③ 다운로드·패치(진행 막대)  ④ SD 카드에 복사  ⑤ 완료 화면(Wii에서 할 일)
결과는 먼저 꾸러미 폴더에 만들고, 모든 파일의 해시가 맞을 때만 SD에 복사한다. SD에서는 아무것도 지우지
않고 같은 이름의 파일만 새 것으로 바꾼다. SD에 복사할 때 그 카드의 Priiloader 핵 파일
(apps/priiloader/hacks_hash.ini)에 KWCE 항목을 더한 디스크 채널 모드 파일 두 개를 만든다
(kwce/priiloader_profile.py: Priiloader 0.8.2·0.10 모두 같은 바이트로 읽는 형식, 기존 핵은 그대로).
다른 PC 대비: 다운로드 재시도(3회), PC·SD 여유 공간 확인, FAT32가 아닌 SD 차단, 쓰기 금지·
'랜섬웨어 방지' 폴더 같은 권한 오류 안내, 목록에 없는 드라이브 직접 입력.
옵션: --mode full|gc|revert  --sd <드라이브|none>  --yes(묻지 않고 기본값)  --bundle --out --cache.
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


PERMISSION_HELP = ('"{where}"에 파일을 쓸 수 없습니다. Windows 보안의 "랜섬웨어 방지(제어된 폴더 액세스)"가 '
                   '바탕 화면·문서 폴더를 막았거나 쓰기 권한이 없는 폴더입니다. zip을 다운로드 폴더나 C:\\KWCE 같은 '
                   '곳에 풀어 다시 실행하세요.')
SD_WRITE_HELP = ('SD 카드에 쓸 수 없습니다. 카드 옆의 잠금 스위치(LOCK)가 내려가 있지 않은지, 카드가 꽉 차지 않았는지 '
                 '확인하세요.')


# ------------------------------------------------------------------ console
def _utf8_console():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


ANSWERS = []   # --answers: scripted choices shown as if typed (demos, screenshots, tests)


def ask(prompt, choices, default, auto):
    """Number menu like WiiLink Patcher. auto=True (or no console) takes the default."""
    if ANSWERS:
        a = ANSWERS.pop(0).strip() or default
        a = a if a in choices else default
        print(f'{prompt} [기본 {default}] {a}')
        return a
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


def gb(n):
    if n >= 1e8:
        return f'{n / 1e9:.1f}GB'
    return f'{n / 1e6:.0f}MB' if n >= 1e6 else '1MB 미만'


def width(s):
    """Console columns: Hangul and other wide characters take two."""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)


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


def nand_usage():
    """app/nand-usage.json (configs/nand-usage-vN.json, scripts/measure_nand_usage.py) or None."""
    try:
        return json.loads((APP / 'nand-usage.json').read_bytes())
    except (OSError, ValueError):
        return None


def usage_line(u):
    t = u['total']
    return (f"Wii 저장 메모리 약 {round(t['blocks'], -1):,}블록(약 {round(t['bytes'] / 1e6, -1):.0f}MB, "
            f"채널을 처음 실행한 뒤 생기는 데이터 포함)")


def choose_mode(mode_arg, auto):
    if mode_arg:
        return mode_arg
    u = nand_usage()
    print('[1단계] 설치 구성 선택')
    print('  1. 빠른 설정 (권장) — 한국어 채널 전체 + 게임큐브·DVD 기능')
    if u:
        print(f'     {usage_line(u)}')
    print('  2. 게임큐브·DVD만 — 채널은 받지 않습니다 (받는 양 약 20MB, Wii 저장 메모리는 거의 안 씀)')
    print('  3. 원래대로 되돌리기 — 방법 안내와 SD 카드 확인 (아무것도 받거나 쓰지 않음)')
    return {'1': 'full', '2': 'gc', '3': 'revert'}[ask('  번호를 고르고 Enter:', ['1', '2', '3'], '1', auto)]


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


def volume_fs(root):
    """File system name of a drive root ('FAT32', 'exFAT', 'NTFS'), or '' when unknown / not a drive root."""
    if sys.platform != 'win32' or not (len(str(root)) <= 3 and str(root)[1:2] == ':'):
        return ''
    import ctypes
    fs = ctypes.create_unicode_buffer(261)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(str(root)[:2] + '\\', None, 0, None, None, None, fs, 261)
    return fs.value if ok else ''


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
    local, other = str(len(drives) + 1), str(len(drives) + 2)
    options[local] = None
    print(f'  {local}. 이 폴더에만 저장 (나중에 직접 SD 카드에 복사)')
    print(f'  {other}. 목록에 없는 드라이브 직접 입력')
    pick = ask('  번호를 고르고 Enter:', list(options) + [other], '1', auto)
    while pick == other:
        try:
            letter = input('  SD 카드 드라이브 문자 (예: E): ').strip().rstrip(':\\/').upper()
        except EOFError:
            letter = ''
        if len(letter) == 1 and letter.isalpha() and os.path.isdir(letter + ':\\'):
            return letter + ':\\'
        print('  그런 드라이브가 없습니다. 카드를 꽂았는지 확인하세요.')
        pick = ask('  번호를 고르고 Enter:', list(options) + [other], local, auto)
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
    original = pp.build_base
    pp.build_base = with_retries(original)          # Bases.wad() looks it up at call time
    try:
        _apply_files(pp, bundle, work, plan, m, bases, log)
    finally:
        pp.build_base = original


def _apply_files(pp, bundle, work, plan, m, bases, log):
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
        self.total = max(total, 1); self.last = 0   # display width of the bar line now on screen

    def _over(self, text, end):
        """Overwrite the current line; pad by display width so no old characters are left behind."""
        print('\r' + text + ' ' * max(0, self.last - width(text)), end=end, flush=True)
        self.last = 0 if end else width(text)

    def __call__(self, line):
        s = line.strip()
        if s.startswith('받는 중:'):
            self._over(f'  {s[len("받는 중:"):].strip()} 다운로드 중...', '\n')
        elif s.startswith('[') and '/' in s and ']' in s:
            done = int(s[1:s.index('/')]); rel = s[s.index(']') + 1:].strip()
            part = rel.split('/')
            name = CHANNELS.get(part[1], '') if len(part) > 2 and part[0] == 'kwce-rc' else ''
            label = f'{name} 패치 중' if name else '파일 만드는 중'
            bar = '#' * (done * 30 // self.total)
            self._over(f'  [{bar:<30}] {done * 100 // self.total:3d}%  {label}', '\n' if done == self.total else '')
        elif s:
            print('  ' + s)


def is_network_error(e):
    names = {type(x).__name__ for x in (e, e.__cause__, e.__context__) if x is not None}
    return bool(names & NET_ERRORS)


NET_ERRORS = {'URLError', 'ConnectionError', 'Timeout', 'ConnectTimeout', 'ReadTimeout', 'SSLError', 'gaierror',
              'TimeoutError', 'ConnectionResetError', 'ConnectionAbortedError', 'HTTPError', 'ChunkedEncodingError',
              'ProtocolError', 'IncompleteRead', 'RemoteDisconnected', 'ProxyError'}


def with_retries(fn, tries=3, wait=3.0):
    """Retry a whole base download after a network error (slow Wi-Fi, a dropped connection)."""
    def run(*a, **k):
        for n in range(tries):
            try:
                return fn(*a, **k)
            except Exception as e:
                if not is_network_error(e) or n == tries - 1:
                    raise
                print(f'\r  연결이 끊겨 다시 시도합니다 ({n + 2}/{tries})...' + ' ' * 20)
                time.sleep(wait * (n + 1))
    return run


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
    try:
        if work.exists():
            shutil.rmtree(work)                   # 이전에 실패한 실행의 임시 폴더(이 도구가 만든 것)
        out.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise Quit(PERMISSION_HELP.format(where=out.parent))
    need = plan.size + (450e6 if plan.mode == 'full' else 25e6) + 50e6
    free = shutil.disk_usage(out.parent).free
    if free < need:
        raise Quit(f'이 PC의 저장 공간이 부족합니다(필요 약 {gb(need)}, 남음 {gb(free)}). '
                   '공간을 비우거나 여유 있는 드라이브에 압축을 풀어 다시 실행하세요.')
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
        if isinstance(e, PermissionError):
            raise Quit(PERMISSION_HELP.format(where=out.parent))
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
    fs = volume_fs(target)
    if fs and fs.upper() not in ('FAT32', 'FAT'):
        raise Quit(f'이 카드는 {fs} 형식입니다. Wii는 FAT32 카드만 읽습니다. 카드를 FAT32로 포맷한 뒤 '
                   f'(https://wii.hacks.guide/ 의 SD 카드 준비 참고) 다시 실행하세요. 만든 파일은 "{out}"에 있습니다.')
    try:
        return _copy_to(Path(out), Path(target), plan, auto)
    except PermissionError:
        raise Quit(SD_WRITE_HELP)
    except OSError as e:
        if getattr(e, 'winerror', None) in (19, 21, 112) or e.errno in (28, 30):   # write-protected / not ready / full
            raise Quit(SD_WRITE_HELP)
        raise


def _copy_to(out, target, plan, auto):
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


# ------------------------------------------------------------------ revert
def sd_records(target):
    """Installer restore records on the card: {channel id: 'removed' | 'original'} (kwce-rc/state/<id>.txt)."""
    out = {}
    for f in sorted((Path(target) / 'kwce-rc/state').glob('*.txt')):
        text = f.read_text(encoding='latin1', errors='replace')
        if text.startswith('before='):
            out[f.stem] = 'original' if text.startswith('before=1') else 'removed'
    return out


def revert_guide(target):
    """Explain how to undo KWCE and check that this card can do it. Writes nothing."""
    print('[되돌리기] KWCE를 설치하기 전 상태로 되돌리는 방법')
    if target:
        t = Path(target)
        recs = sd_records(t)
        has_tool = (t / 'apps/kwce-installer-rc/boot.dol').is_file()
        missing = sorted(c for c, how in recs.items() if how == 'original' and not (t / f'kwce-rc/{c}/original.wad').is_file())
        print(f'  SD 카드 확인({target}):')
        print(f"    설치 도구: {'있음' if has_tool else '없음'}")
        if recs:
            names = ', '.join(CHANNELS.get(c, c) for c in recs)
            print(f'    복원 기록: 채널 {len(recs)}개 ({names})')
        else:
            print('    복원 기록: 없음 — 채널을 설치할 때 쓴 SD 카드가 아니거나 kwce-rc 폴더를 지운 경우입니다.')
        if not has_tool or missing:
            print('    → 먼저 이 패처의 1번(빠른 설정)으로 이 카드에 다시 복사하세요. 복원 기록은 지워지지 않습니다.')
    else:
        print('  (SD 카드를 고르면 복원에 필요한 파일과 기록이 있는지 확인해 드립니다.)')
    print()
    print('  1. 채널: 홈브류 채널 → KWCE Channel Installer → +(START) → 2(전체 복원)')
    print('     KWCE 전에 없던 채널은 지우고, 있던 채널은 원래 판으로 다시 넣습니다.')
    print('     복원 기록이 없으면 채널을 고르고 A → Delete channel로 하나씩 지웁니다.')
    print('     세이브 데이터는 남습니다(Wii 설정 → 데이터 관리에서 지울 수 있음).')
    print('  2. 게임큐브·DVD: RESET을 누른 채 전원을 켜서 Priiloader → System Menu Hacks에서')
    print('     이름이 "KWCE"로 시작하는 항목을 모두 끄고 저장합니다.')
    print('  3. (선택) 1·2를 마친 뒤 SD에서 apps/kwce-installer-rc, kwce, kwce-rc 폴더를 지웁니다.')
    print()
    print('  Wii 메뉴가 뜨지 않을 때: RESET을 누른 채 전원을 켜면 Priiloader가 열립니다. 2번처럼 KWCE')
    print('  항목을 끄고 저장한 뒤 다시 켜세요. KWCE는 시스템 메뉴 파일 자체는 바꾸지 않습니다.')


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
        u = nand_usage()
        if u:
            print(f'       {usage_line(u)}.')
            print('       Wii 설정 → 데이터 관리에서 남은 블록을 먼저 확인하고, 모자라면 채널을 골라 1로 하나씩 설치하세요.')
        print('    3. 게임큐브·DVD: -(GC L) → 1 게임큐브만 / 2 게임큐브+DVD')
    else:
        print('    2. -(GC L) → 1 게임큐브만 / 2 게임큐브+DVD')
    print('    마지막으로 RESET을 누른 채 전원을 켜서 Priiloader → System Menu Hacks에서')
    print('    KWCE 항목을 켜고 저장합니다. (쓰던 다른 핵도 켜져 있는지 확인하세요.)')
    if plan.mode == 'full':
        print()
        print('  권장 홈브류: sntp — Wii 시계를 인터넷 시간에 맞춥니다.')
        print('    날씨·뉴스·투표·Mii 콘테스트가 연결 오류(예: NEWS000006)를 내면 먼저 실행하세요.')
        print('    실행한 뒤 시간대는 UTC+9(한국)를 고릅니다. Open Shop Channel에서 받을 수 있습니다.')
    print('  자세한 설명·되돌리는 방법: README-ko.txt (또는 이 패처의 3번)')
    if sys.platform == 'win32' and not auto:
        while True:
            choices = (['1'] if plan.mode == 'full' else []) + ['2', '3']
            menu = ('  1. sntp 받는 곳 열기(웹 브라우저)  ' if plan.mode == 'full' else '  ') + '2. 폴더 열고 닫기  3. 그냥 닫기:'
            pick = ask(menu, choices, '3', auto)
            if pick == '1':
                open_url(SNTP_URL)
                print(f'  열었습니다: {SNTP_URL}')
                continue
            if pick == '2':
                os.startfile(target if target and copied else out)
            break


SNTP_URL = 'https://oscwii.org/library/app/sntp'


def open_url(url):
    """Default browser; if that fails the address is still printed for copying."""
    try:
        import webbrowser
        if not webbrowser.open(url):
            os.startfile(url)
    except Exception:
        print(f'  브라우저를 열지 못했습니다. 이 주소를 직접 여세요: {url}')


def main(argv=None):
    _utf8_console()
    sys.dont_write_bytecode = True
    ap = argparse.ArgumentParser(description='KWCE 패처: 한국판 Wii용 KWCE 파일을 만든다.')
    ap.add_argument('--bundle', default=str(PKG / 'bundle'))
    ap.add_argument('--out', help='결과 폴더 (기본: 꾸러미 폴더 안)')
    ap.add_argument('--cache', default=str(PKG / CACHE_NAME))
    ap.add_argument('--mode', choices=['full', 'gc', 'revert'],
                    help='full = 채널 전체 + 게임큐브·DVD, gc = 게임큐브·DVD만, revert = 되돌리는 방법')
    ap.add_argument('--sd', help='SD 카드 드라이브(예: E:) 또는 none(이 폴더에만 저장)')
    ap.add_argument('--yes', action='store_true', help='묻지 않고 기본값으로 진행')
    ap.add_argument('--answers', help='고를 번호를 차례로 미리 지정(쉼표로 구분, 화면에는 입력한 것처럼 보임)')
    a = ap.parse_args(argv)
    auto = a.yes or not sys.stdin or not sys.stdin.isatty()
    if a.answers:
        ANSWERS[:] = a.answers.split(',')
        auto = False
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
        mode = choose_mode(a.mode, auto)
        print()
        if mode == 'revert':
            revert_guide(choose_target(find_drives(), a.sd, auto))
            if sys.platform == 'win32' and not auto:
                ask('  Enter 키를 누르면 닫습니다.', [''], '', auto)
            return 0
        plan = Plan(m, mode)
        out = Path(a.out) if a.out else PKG / OUT_NAMES[plan.mode]
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

"""KWCE 패처 — Windows 꾸러미 진입점 (꾸러미 안에서는 app/run.py).

더블클릭(KWCE-Patcher.bat)으로 실행하면 꾸러미 안의 패치 묶음(bundle/)으로 SD 카드용 파일을 만든다.
결과는 꾸러미 폴더의 "SD카드에 복사할 파일", 받은 원본은 "받은 원본"(다음 실행 때 다시 씀).
작업은 임시 폴더에서 하고, 모든 파일의 해시가 맞았을 때만 결과 폴더 이름으로 바꾼다.
이 도구는 아무것도 업로드하지 않는다.
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent
PKG = APP.parent
OUT_NAME = 'SD카드에 복사할 파일'
CACHE_NAME = '받은 원본'
WORK_NAME = '.작업 중 (지워도 됨)'


def _utf8_console():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def _bundle_label(bundle):
    try:
        m = json.loads((Path(bundle) / 'manifest.json').read_bytes())
        return f"{Path(bundle).name} → {m.get('source_package', '?')} ({len(m.get('files', {}))}개 파일)"
    except (OSError, ValueError):
        return '?'


def _is_network_error(e):
    names = {type(x).__name__ for x in (e, e.__cause__, e.__context__) if x is not None}
    return bool(names & {'URLError', 'ConnectionError', 'Timeout', 'ConnectTimeout', 'ReadTimeout',
                         'SSLError', 'gaierror', 'TimeoutError', 'ConnectionResetError', 'HTTPError'})


def run(bundle, out, cache, apply=None, log=print):
    """0 = 완료, 1 = 실패. 실패해도 반쯤 만든 결과를 결과 폴더로 남기지 않는다."""
    bundle, out, cache = Path(bundle), Path(out), Path(cache)
    if apply is None:
        from kwce import public_patch as pp
        apply = pp.apply_bundle
    if not (bundle / 'manifest.json').is_file():
        log(f'실패: 패치 묶음을 찾지 못했습니다: {bundle}')
        return 1
    if out.exists() and any(out.iterdir()):
        log(f'이미 결과 폴더가 있습니다: "{out}"')
        log('SD 카드에 이미 복사했다면 그대로 쓰시면 됩니다. 다시 만들려면 이 폴더를 지우거나 이름을 바꾼 뒤 실행하세요.')
        return 1
    work = out.parent / WORK_NAME
    if work.exists():
        shutil.rmtree(work)                       # 이전에 실패한 실행의 임시 폴더(이 도구가 만든 것)
    log(f'패치 묶음: {_bundle_label(bundle)}')
    log(f'받은 원본 보관: "{cache}"')
    log('닌텐도 업데이트 서버와 WiiLink 서버에서 원본을 받습니다. 처음에는 약 430MB, 몇 분 걸립니다.')
    t0 = time.time()
    try:
        m = apply(bundle, work, cache, log)
    except Exception as e:  # one clear line; nothing half-made is reported as done
        log('')
        if _is_network_error(e):
            log(f'실패: 서버에 연결하지 못했습니다 ({type(e).__name__}). 인터넷 연결을 확인하고 다시 실행하세요.')
            log('이미 받은 원본은 보관되어 있어 다시 받지 않습니다.')
        else:
            log(f'실패: {e}')
        shutil.rmtree(work, ignore_errors=True)
        return 1
    if out.exists():
        out.rmdir()                               # 비어 있는 폴더만 여기까지 온다
    work.rename(out)
    log('')
    log(f'완료: 파일 {len(m["files"])}개를 만들었고 모두 해시가 일치합니다 ({time.time() - t0:.0f}초).')
    log(f'"{out}" 폴더 안의 내용을 SD 카드 맨 위(루트)에 복사하세요.')
    log('그다음 Wii의 홈브류 채널에서 KWCE Channel Installer를 실행합니다. 자세한 것은 README-ko.txt.')
    return 0


def main(argv=None):
    _utf8_console()
    sys.dont_write_bytecode = True
    ap = argparse.ArgumentParser(description='KWCE 패처: 공개 패치 묶음으로 SD 카드용 파일을 만든다.')
    ap.add_argument('--bundle', default=str(PKG / 'bundle'))
    ap.add_argument('--out', default=str(PKG / OUT_NAME))
    ap.add_argument('--cache', default=str(PKG / CACHE_NAME))
    a = ap.parse_args(argv)
    try:
        info = json.loads((APP / 'build-info.json').read_bytes())
        print(f"KWCE 패처 (베타) — {info.get('patcher')}, 묶음 {info.get('bundle')}")
    except (OSError, ValueError):
        print('KWCE 패처 (베타)')
    print('=' * 40)
    return run(a.bundle, a.out, a.cache)


if __name__ == '__main__':
    if str(APP) not in sys.path:
        sys.path.insert(0, str(APP))
    raise SystemExit(main())

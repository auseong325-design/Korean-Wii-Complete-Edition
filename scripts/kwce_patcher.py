"""KWCE PC 패처: 공개 패치 묶음으로 SD 카드용 파일을 만든다.

  python scripts/kwce_patcher.py --bundle <kwce-public-vN 폴더> --out <빈 폴더> [--cache <폴더>]

하는 일: ① 닌텐도 업데이트 서버에서 채널 원본과 시스템 메뉴 4.3K를 받고(무료 티켓),
② WiiLink 패치 서버에서 WiiLink 패치를 받아 적용하고(WiiLink Patcher와 같은 순서),
③ KWCE 패치를 적용해 SD 파일을 만든다. 파일마다 SHA-256을 확인하며, 다르면 만들지 않는다.
받은 원본은 --cache 폴더에 남아 다음 실행 때 다시 쓴다. 이 도구는 아무것도 업로드하지 않는다.
만든 폴더의 내용을 SD 카드 루트에 복사한 뒤 Wii의 홈브류 채널에서 KWCE Channel Installer를 실행한다.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import public_patch as pp  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--bundle', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--cache', default=str(ROOT / 'workspace/public/cache'))
    a = ap.parse_args()
    t0 = time.time()
    try:
        m = pp.apply_bundle(a.bundle, a.out, a.cache)
    except Exception as e:  # one clear line for the user; nothing half-made is reported as done
        print(f'실패: {e}')
        raise SystemExit(1)
    print(f'완료: 파일 {len(m["files"])}개를 만들었고 모두 해시가 일치합니다 ({time.time() - t0:.0f}초). '
          f'"{a.out}" 안의 내용을 SD 카드 루트에 복사하세요.')


if __name__ == '__main__':
    main()

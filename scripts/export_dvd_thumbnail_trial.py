"""Export the native59 one-call-site control without changing GC or player resources."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.dvd_thumbnail_trial_sd import TARGETS,PATHS,README,upgrade_definition,sd_files
from kwce.gc_card_encoding_sd import DEFINITIONS


def main():
    out=ROOT/'workspace/hardware/kwce-dvd-stock-thumbnail-v1'
    if out.exists():raise ValueError('Existing numbered control preserved')
    out.mkdir();inputs={}
    for rel in sorted(DEFINITIONS):
        source=ROOT/'workspace/hardware'/('kwce-dvd-deferred-prefetch-v1'if rel in TARGETS else'kwce-gc-card-encoding-v1')/rel
        raw=source.read_bytes();inputs[rel]=hashlib.sha256(raw).hexdigest()
        if rel in TARGETS:
            old=out/'expected'/rel;old.parent.mkdir(parents=True,exist_ok=True);old.write_bytes(raw)
            p=out/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(upgrade_definition(raw))
    (out/README).write_text('''KWCE DVD 순정 메뉴 상태 갱신 대조본 v1 (native59/source30)

native58에서 본체 설정 정지가 재현됐으며, 프로브는 성공/실패가 모두 관측됐습니다.
이번 대조본은 native58과 비교해 메뉴의 원래 SDK updateDiskState 호출 한 곳(4바이트)만 복원합니다.
다른6훅과 모든 주입 코드/SD 초기화 재시도/플레이어R51/GC·카드 인코딩은 유지합니다.
메뉴의 전용 DVD 아이콘이 표시되지 않고 순정 디스크 상태 표시로 보이는 것은 이번 시험의 의도입니다.
정지 해결이나 DVD 재생 성공은 아직 확인되지 않았습니다.

Priiloader System Menu Hacks에서 기존 KWCE DVD: disc channel DVD player 항목을 ON으로 하고
Save Settings하여 새 SD 정의를 읽습니다. GC3항목/카드 인코딩과 다른 핵은 유지합니다.
같은 DVD를 넣은 채 완전 전원 종료·분리 후 부팅해 본체 설정에 한 번 들어갑니다.
우선 설정 진입 결과만 비교합니다. 프로브 성공을 확인하려고 읽기를 반복할 필요는 없습니다.
설정 정지가 다시 발생하면 해당 DVD 항목을 OFF로 되돌리고 결과를 남깁니다.
시스템 메뉴/IOS/WAD 설치나 초기화는 하지 않습니다. 에이전트는 실기를 조작하지 않습니다.

SD 변경은 활성/gc-dvd 완성본/gc-dvd fragment의 DVD 섹션3개와 안내/manifest뿐입니다.
기존 파일은 먼저 백업하고 GC-only 두 정의·GC블록·다른 핵·재생기·프로브·로그를 보존합니다.
SD 파일 복사만으로 실기 RAM 활성 상태는 바뀌지 않습니다.
''',encoding='utf-8')
    old=json.loads((ROOT/'workspace/hardware/kwce-dvd-deferred-prefetch-v1/package-manifest.json').read_text())
    meta=dict(kind='dvd-stock-thumbnail-trial-v1',nand_write=False,gc_changed=False,player_changed=False,
              thumbnail_hook=False,other_hook_changes=False,source_revision=30,hook_revision=59,
              real_console_verified=False,files={p:hashlib.sha256((out/p).read_bytes()).hexdigest()for p in PATHS},
              expected_inputs=inputs,runtime_inputs=old['runtime_inputs'])
    raw=(json.dumps(meta,ensure_ascii=False,indent=2)+'\n').encode()
    (out/'package-manifest.json').write_bytes(raw)
    (out/'package-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
    sd_files(out)
    print('PASS kwce-dvd-stock-thumbnail-v1: one original SDK call restored; GC/player/probe unchanged; hardware unverified')


if __name__=='__main__':main()

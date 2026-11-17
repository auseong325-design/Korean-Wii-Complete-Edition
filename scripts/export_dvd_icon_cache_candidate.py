"""Export native60 icon cache candidate over the user's native59 control definitions."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.dvd_icon_cache_sd import TARGETS,PATHS,README,upgrade_definition,sd_files
from kwce.gc_card_encoding_sd import DEFINITIONS


def main():
    out=ROOT/'workspace/hardware/kwce-dvd-icon-cache-v1'
    if out.exists():raise ValueError('Existing numbered cache candidate preserved')
    out.mkdir();inputs={}
    for rel in sorted(DEFINITIONS):
        source=ROOT/'workspace/hardware'/('kwce-dvd-stock-thumbnail-v1'if rel in TARGETS else'kwce-gc-card-encoding-v1')/rel
        raw=source.read_bytes();inputs[rel]=hashlib.sha256(raw).hexdigest()
        if rel in TARGETS:
            old=out/'expected'/rel;old.parent.mkdir(parents=True,exist_ok=True);old.write_bytes(raw)
            p=out/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(upgrade_definition(raw))
    (out/README).write_text('''KWCE DVD 아이콘 캐시 반영 후보 v1 (native60/source31)

사용자 대조에서 native59(원래 메뉴 SDK 호출)는 DVD 삽입·완전 부팅 뒤 본체 설정 진입이 정상입니다.
원래 SDK 아이콘 경로는 버퍼를 넘기기 전에 DCStoreRange로 캐시 내용을 메모리에 반영합니다.
이 처리가 빠졌던 사용자 DVD 아이콘 경로에, 파일/해시 검증 성공 후 같은 처리를 추가했습니다.
아이콘 표시 경로를 다시 켭니다. 실패했던 native58 대비 소스 변경은 이 호출 한 곳뿐입니다.
나머지 상태 처리/SD 재시도/지연 준비/R51·module10/GC·카드 인코딩/프로브는 유지합니다.
이 누락이 실제 본체 설정 정지의 원인인지는 아직 미검증입니다.

Priiloader의 기존 KWCE DVD: disc channel DVD player 항목을 ON으로 하고 Save Settings하여 새 정의를 읽습니다.
GC3항목/일본어 카드 인코딩과 다른 핵은 유지합니다. 설치 도구의 모드 파일을 바꿀 필요는 없습니다.
같은 DVD 삽입·완전 전원 종료/분리 후 부팅해 본체 설정에 한 번 들어가 비교합니다.
정상이면 메뉴로 돌아와 DVD 아이콘이 보이는지도 확인합니다. 프로브 반복이나 재생 시험은 그다음입니다.
정지가 재발하면 DVD 항목을 OFF로 되돌리고 마지막 단계를 남깁니다.
시스템 메뉴/IOS/WAD 설치나 초기화는 하지 않습니다.

변경은 활성/gc-dvd 완성본/gc-dvd fragment의 DVD3섹션과 안내/manifest뿐입니다.
기존3정의를 먼저 백업하고 GC-only 두 정의·모든 GC/다른 핵·재생기·프로브·로그를 보존합니다.
SD 복사만으로 실기 RAM 적용 상태가 바뀌지는 않습니다. 에이전트는 본체를 조작하지 않습니다.
''',encoding='utf-8')
    old=json.loads((ROOT/'workspace/hardware/kwce-dvd-stock-thumbnail-v1/package-manifest.json').read_text())
    meta=dict(kind='dvd-icon-cache-store-v1',nand_write=False,gc_changed=False,player_changed=False,
              icon_cache_store=True,thumbnail_hook=True,other_functional_changes=False,
              source_revision=31,hook_revision=60,real_console_verified=False,
              files={p:hashlib.sha256((out/p).read_bytes()).hexdigest()for p in sorted(PATHS)},
              expected_inputs=inputs,runtime_inputs=old['runtime_inputs'])
    raw=(json.dumps(meta,ensure_ascii=False,indent=2)+'\n').encode()
    (out/'package-manifest.json').write_bytes(raw)
    (out/'package-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
    sd_files(out)
    print('PASS kwce-dvd-icon-cache-v1: validated icon DCStoreRange added; GC/player/probe unchanged; hardware unverified')


if __name__=='__main__':main()

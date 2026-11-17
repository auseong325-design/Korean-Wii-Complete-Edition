"""New SD candidate: delay player prefetch, preserve GC encoding and all runtime files."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.dvd_prefetch_sd import TARGETS, PATHS, README, upgrade_definition, sd_files
from kwce.gc_card_encoding_sd import DEFINITIONS


def main():
    source=ROOT/'workspace/hardware/kwce-gc-card-encoding-v1'
    out=ROOT/'workspace/hardware/kwce-dvd-deferred-prefetch-v1'
    if out.exists():raise ValueError('Existing numbered candidate preserved')
    out.mkdir()
    inputs={}
    for rel in sorted(DEFINITIONS):
        raw=(source/rel).read_bytes();inputs[rel]=hashlib.sha256(raw).hexdigest()
        if rel in TARGETS:
            original=out/'expected'/rel;original.parent.mkdir(parents=True,exist_ok=True);original.write_bytes(raw)
            p=out/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(upgrade_definition(raw))
    (out/README).write_text('''KWCE DVD 사전 읽기 지연 시험 후보 v1 (native58/source30)

사용자 비교: DVD 핵 OFF에서 본체 설정·HBC 프로브 정상. ON에서는 정지 이력이 있습니다.
메뉴의 작은 DVD 아이콘을 표시할 때 약7.2MiB 플레이어/스택과 배너 전체를 읽던 경로를 분리합니다.
아이콘은 기존 해시 검증을 거쳐 표시하고, 큰 자원은 DVD 상세 화면에서 준비합니다.
재생기R51·물리 판독/IFO 처리·SD 연결 재시도·GC/카드 인코딩 핵은 유지합니다.
실기 정지 원인과 이 후보의 효과, DVD 재생 성공은 아직 미검증입니다.

적용 후 Priiloader System Menu Hacks에서 기존 KWCE DVD: disc channel DVD player를 ON으로 선택하고
Save Settings하여 새 정의를 읽습니다. GC3항목/일본어 카드 인코딩과 다른 핵은 유지합니다.
같은 DVD를 넣은 채 완전 전원 종료·분리 후 부팅해 본체 설정에 들어갑니다.
정상이면 메뉴→HBC→KWCE DVD Read Probe를 실행해 A를 한 번 누릅니다.
이 두 동작부터 확인한 뒤 DVD 채널의 배너/시작/재생 여부를 따로 시험합니다.
정지가 재발하면 DVD 항목만 OFF로 되돌리고 마지막 단계와 종료 방법을 남깁니다.
시스템 메뉴/IOS/WAD 설치나 초기화는 하지 않습니다.

SD 적용 범위: 활성/GC+DVD 완성본/GC+DVD fragment의 DVD 섹션3개와 이 안내/manifest만.
기존 파일은 배포기가 먼저 백업합니다. GC-only 두 정의·모든 GC 항목/다른 핵/재생기/로그는 유지합니다.
SD 정의 복사만으로 실기 RAM 패치 활성화가 바뀌지는 않습니다. 에이전트는 본체를 조작하지 않습니다.
''',encoding='utf-8')
    rc=ROOT/'workspace/hardware/kwce-rc-sd-v38'
    manifest=json.loads((rc/'package-manifest.json').read_text())
    runtime={r['path']:r['sha256'] for r in manifest['sd_files'] if r['path'].startswith('kwce/dvd/')}
    record=dict(kind='dvd-deferred-prefetch-v1',nand_write=False,player_changed=False,gc_changed=False,
                source_revision=30,hook_revision=58,real_console_verified=False,
                files={r:hashlib.sha256((out/r).read_bytes()).hexdigest()for r in PATHS},
                expected_inputs=inputs,runtime_inputs=runtime)
    raw=(json.dumps(record,ensure_ascii=False,indent=2)+'\n').encode()
    (out/'package-manifest.json').write_bytes(raw)
    (out/'package-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
    sd_files(out)
    print('PASS kwce-dvd-deferred-prefetch-v1: 3 DVD-only section updates; GC/player unchanged; hardware unverified')


if __name__=='__main__':main()

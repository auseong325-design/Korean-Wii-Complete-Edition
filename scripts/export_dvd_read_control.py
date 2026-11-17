"""Export a new read/graphics control; never install a system title."""
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kwce.dvd_read_control_sd import TARGETS,PATHS,README,upgrade_definition,sd_files
from kwce.gc_card_encoding_sd import DEFINITIONS


def main():
    out=ROOT/'workspace/hardware/kwce-dvd-read-control-v1'
    if out.exists():raise ValueError('Existing numbered read control preserved')
    out.mkdir();inputs={}
    for rel in sorted(DEFINITIONS):
        source=ROOT/'workspace/hardware'/('kwce-dvd-icon-cache-v1' if rel in TARGETS
                                         else 'kwce-gc-card-encoding-v1')/rel
        raw=source.read_bytes();inputs[rel]=hashlib.sha256(raw).hexdigest()
        if rel in TARGETS:
            old=out/'expected'/rel;old.parent.mkdir(parents=True,exist_ok=True);old.write_bytes(raw)
            p=out/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(upgrade_definition(raw))
    (out/README).write_text('''KWCE DVD 읽기/화면 생성 분리 대조 v1 (native61/source32)

native60에서 DVD 썸네일 표시 후 채널 내부를 열지 않아도 본체 설정 정지가 재현됐습니다.
이번 대조는 같은 아이콘 파일 읽기/길이/SHA 검증/캐시 반영을 유지합니다.
별도 DVD 썸네일 레이아웃/애니메이터를 만들지 않고 원래 SDK의 갱신을 호출합니다.
읽기 성공 시 조작 없이 짧은 일반 선택 확인음(WIPL_SE_DECIDE)을 한 번 냅니다.
이 소리는 새 파일을 실제로 읽었는지 확인하기 위한 진단 표시입니다.
음량/잠금 상태 때문에 소리가 안 날 수 있으므로 무음은 성공/실패 어느 쪽도 증명하지 않습니다.
SD 쓰기/보고서/큰 재생 모듈 사전 준비/네트워크 기능은 추가하지 않았습니다.
본체 설정 정지와 DVD 재생의 해결 여부는 실기 미검증입니다.

Priiloader의 기존 KWCE DVD: disc channel DVD player 항목을 ON/Save Settings합니다.
다른 핵과 GC 인코딩은 유지합니다. 같은 DVD·주황색 대기 후 켜기 조건으로 부팅합니다.
메뉴에서 버튼을 누르기 전에 확인음이 한 번 났는지 확인합니다. 전용 DVD 썸네일은 없습니다.
소리가 났다면 디스크 채널을 열지 않고 바로 본체 설정에 한 번 들어갑니다.
소리가 없으면 비교 미확인으로 기록하고 정지 시험을 반복하지 않습니다.
결과 확인 후 DVD 항목은 OFF로 유지합니다. 프로브/재생을 함께 시험하지 않습니다.
시스템 메뉴/IOS/WAD 설치나 WiiConnect24 설정 변경은 없습니다.

활성/gc-dvd 완성본/fragment의 DVD3섹션만 사전백업 후 갱신합니다.
GC-only 두 정의/모든 GC·다른 핵/재생기/프로브/기존 로그는 보존합니다.
SD 복사만으로 실기 RAM 적용 상태가 바뀌지는 않습니다.
''',encoding='utf-8')
    old=json.loads((ROOT/'workspace/hardware/kwce-dvd-icon-cache-v1/package-manifest.json').read_text())
    meta=dict(kind='dvd-thumbnail-read-control-v1',nand_write=False,gc_changed=False,
              player_changed=False,thumbnail_read_control=True,custom_icon_layout=False,
              success_sound='WIPL_SE_DECIDE',other_functional_changes=False,
              source_revision=32,hook_revision=61,real_console_verified=False,
              files={p:hashlib.sha256((out/p).read_bytes()).hexdigest()for p in sorted(PATHS)},
              expected_inputs=inputs,runtime_inputs=old['runtime_inputs'])
    raw=(json.dumps(meta,ensure_ascii=False,indent=2)+'\n').encode()
    (out/'package-manifest.json').write_bytes(raw)
    (out/'package-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
    sd_files(out)
    print('PASS read control: validated reads, one success sound, stock thumbnail; hardware unverified')


if __name__=='__main__':main()

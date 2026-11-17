"""Freeze the qualified RAM-only native66 SD candidate; no physical writes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.dvd_integrated_sd import DEFINITIONS, TARGETS, PATHS, README, qualified, upgrade, sd_files
from kwce.gc_card_encoding_sd import wii_mount
from kwce.gcmce_recovery import sha


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--drive',required=True);ap.add_argument('--qualification',required=True)
    a=ap.parse_args();card=Path(a.drive).resolve();wii_mount(card);q=Path(a.qualification);qualified(q)
    out=ROOT/'workspace/hardware/kwce-dvd-integrated-v1'
    if out.exists():raise ValueError('Numbered package already exists')
    old={r:(card/r).read_bytes()for r in DEFINITIONS}
    result={r:upgrade(old['kwce-rc/priiloader/gc-dvd.ini']if r=='apps/Priiloader/hacks_hash.ini'else old[r])for r in TARGETS}
    runtime=json.loads((ROOT/'workspace/hardware/kwce-dvd-read-control-v1/package-manifest.json').read_text())['runtime_inputs']
    if any(sha(card/r)!=h for r,h in runtime.items()):raise ValueError('Reviewed player resources changed')
    out.mkdir()
    for rel,data in old.items():
        p=out/'expected'/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    for rel,data in result.items():
        p=out/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    shutil.copyfile(q,out/'qualification.json')
    (out/README).write_text('''KWCE DVD 통합 서비스 실기 시험본 v1 (native66/source37)

이 묶음은 시스템 메뉴 RAM 패치 정의입니다. 시스템 메뉴/IOS/WAD를 설치하지 않습니다.
기존 GC 인코딩 수정과 플레이어 R51·자원5개, 프로브는 그대로입니다.
SD 파일을 읽기만 하는 UI가 아니라, 메뉴의 원래 SDVF 작업 큐에서 CDB 인계 전에
자원3개를 검증해 준비합니다. 화면 함수는 파일을 열거나 SD를 다시 마운트하지 않습니다.
설정 진입은 작업 취소→원래 SD 종료→자식 화면 종료→큰 버퍼 해제 순서를 따릅니다.
설정에서 돌아오면 새 작업 수명에서 다시 읽습니다. BS2 상태 강제 변경은 없습니다.

로컬 확인: 실제43K PPC/SDK 수명 검사, 구형 Priiloader 순차 적용 일치,
격리 Dolphin 메뉴에서 DVD 썸네일→본체 설정→메뉴 복귀, 배너와 재생기 진입.
합성 매체 시험이므로 실제 DVD-Video 판독/UDF/IFO/영상 또는 실기 정지 해결을
확정한 것은 아닙니다. 기존의 반복 프로브 대신 아래 순서로 비교합니다.

1. SD를 Wii에 연결하고 RESET을 누른 채 켜 Priiloader에 들어갑니다.
2. System Menu Hacks에서 기존 GC 항목은 유지하고
   KWCE DVD: disc channel DVD player 항목을 ON, Save Settings합니다.
   이 SD는 GC+DVD 정의로 전환되어 있습니다. GC-only layout 항목은 DVD 모드에서 제외됩니다.
3. 같은 DVD를 넣고 완전 종료·전원선 분리 후 부팅합니다.
   DVD 썸네일이 나온 뒤 디스크 채널을 열지 말고 본체 설정에 먼저 들어갑니다.
4. 정상이라면 메뉴로 돌아와 DVD 디스크 채널의 배너와 시작을 확인합니다.
   재생기 첫 화면/판독 결과를 기록합니다. 그다음 주황 대기 후 부팅을 한 번 비교합니다.
5. 멈추면 그 단계에서 중단하고 Priiloader의 DVD 항목을 OFF로 돌립니다.
   기존 KWCE 설치 도구의 GC 전용 모드 정의도 보존되어 있습니다.
   새 포맷·NAND 복원·IOS 교체는 필요하지 않습니다.

SD의 활성 정의·DVD 완성본·DVD fragment만 바꾸며 먼저 원본을 백업합니다.
SD 복사만으로 Priiloader가 NAND에 저장한 활성 상태가 바뀌지는 않습니다.
''',encoding='utf-8')
    m=dict(kind='dvd-integrated-service-v1',revision=66,source_revision=37,nand_write=False,
           player_changed=False,gc_changed=False,physical_dvd_verified=False,
           expected_inputs={r:hashlib.sha256(b).hexdigest()for r,b in old.items()},runtime_inputs=runtime,
           qualification_sha256=sha(out/'qualification.json'),files={r:sha(out/r)for r in PATHS})
    raw=(json.dumps(m,ensure_ascii=False,indent=2)+'\n').encode();(out/'package-manifest.json').write_bytes(raw)
    (out/'package-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n');sd_files(out)
    print('PASS qualified native66 SD package: RAM definitions only; no physical writes')


if __name__=='__main__':main()

"""Freeze R53/native67 diagnostics after local qualification; no SD writes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.dvd_player_trace_sd import DEFINITIONS,TARGETS,PATHS,README,MODULE,upgrade,sd_files
from kwce.dvd_integrated_sd import qualified
from kwce.gc_card_encoding_sd import wii_mount
from kwce.gcmce_recovery import sha


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--drive',required=True);ap.add_argument('--qualification',required=True)
    ap.add_argument('--revision',type=int,choices=(1,2,3,4,5,6),default=1)
    a=ap.parse_args();card=Path(a.drive).resolve();wii_mount(card)
    v2=a.revision==2
    player,hook,module={1:(53,67,12),2:(54,68,13),3:(55,69,14),4:(56,70,15),5:(57,71,16),6:(58,72,17)}[a.revision]
    readme=README.replace('v1',f'v{a.revision}')
    paths=TARGETS|{MODULE,readme}
    q=Path(a.qualification);qualified(q,hook)
    out=ROOT/f'workspace/hardware/kwce-dvd-player-trace-v{a.revision}'
    if out.exists():raise ValueError('Existing numbered trace package preserved')
    old={r:(card/r).read_bytes() for r in DEFINITIONS}
    changed={r:upgrade(old[r],hook-1,hook)for r in TARGETS}
    prior=json.loads((ROOT/'workspace/hardware/kwce-dvd-integrated-v1/package-manifest.json').read_text())
    if a.revision>=2:
        previous=json.loads((ROOT/f'workspace/hardware/kwce-dvd-player-trace-v{a.revision-1}/package-manifest.json').read_text())
        prior['runtime_inputs'][MODULE]=previous['files'][MODULE]
    if any(sha(card/r)!=h for r,h in prior['runtime_inputs'].items()):raise ValueError('Reviewed runtime changed')
    out.mkdir()
    for rel,data in old.items():
        p=out/'expected'/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    for rel,data in changed.items():
        p=out/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    p=out/MODULE;p.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ROOT/f'workspace/experiments/dvd-native-module-v{module}/player.ash',p)
    shutil.copyfile(q,out/'qualification.json')
    (out/readme).write_text('''KWCE DVD 초기 판독 진단 v1 — R53/native67

이번 실기 실행은 본체 설정/디스크 채널 표시 뒤 재생기 R51의 VMGI 파일 열기
진입까지 진행했고, 그 뒤 기록이 없었습니다. 아직 재생 문제 해결본은 아닙니다.
메뉴의 원래 SDVF worker/설정 종료/GC 인코딩 처리는 native66과 같은 source37입니다.
새 재생기와 그 크기·해시를 반영한 RAM 정의만 변경합니다. NAND 설치물은 없습니다.
R53은 초기 물리 읽기 최대32회의 호출 전/후와 오류 조회 직전,
UDF 앵커/파티션/루트 탐색 경계를 숫자만 기존 playback-r21.log에 추가합니다.
매체 내용·제목·섹터 주소·키·콘솔 식별값·네트워크 전송은 기록하지 않습니다.

1. Priiloader의 기존 KWCE DVD 항목 ON, Save Settings. GC 항목은 유지합니다.
2. 같은 DVD를 넣고 완전 종료 후 전원을 분리했다 다시 켭니다.
3. 본체 설정 진입을 한 번 확인하고, 메뉴로 돌아와 디스크 채널에서 시작합니다.
4. 첫 화면 또는 오류가 나오면 그 내용을 기록합니다. 검은 화면이 지속되면
   추가로5분 이상 기다리거나 같은 부팅을 반복할 필요는 없습니다.
   전원을 끈 뒤 SD를 PC에 연결해 기존 로그를 확인합니다.
5. 이번 회차는 여기서 끝냅니다. 주황 대기 비교/별도 프로브는 실행하지 않습니다.

하위 드라이브의 무응답을 강제로 중단하는 코드는 추가하지 않았습니다.
강제 중단 뒤 DMA 버퍼 해제가 안전한지는 별도 검증이 필요합니다.
기존 로그·세이브·GC 전용 정의·HOME/배너/아이콘/폰트는 보존합니다.
''',encoding='utf-8')
    if v2:
        (out/readme).write_text('''KWCE DVD 읽기 실패 처리 수정 v2 — R54/native68

실기 R53은 첫 읽기가 오류1로 반환된 뒤 동기 오류조회 직전에서 기록이 끊겼습니다.
R54는 이 추가 오류조회 없이 실패를 반환하고 실패한 버퍼를 복사하지 않습니다.
드라이브 정지/닫기 전후도 숫자로 기록합니다. 최초읽기 실패 자체의 해결은 미검증입니다.
GC/메뉴 source37·배너·HOME·폰트·기존로그를 유지하며 NAND 설치/IOS 교체는 없습니다.

1. Priiloader의 기존 KWCE DVD 항목 ON, Save Settings. GC 항목은 유지합니다.
2. 같은DVD를 넣고 완전 종료·전원선 분리 후 부팅합니다.
3. 설정 진입/복귀를 확인한 뒤 디스크 채널에서 시작을 한 번 누릅니다.
4. DVD메뉴/오류안내/자동메뉴복귀 중 무엇이 나오는지 확인합니다.
   검은화면이 지속되면 반복하지 말고 전원 종료 후 SD를 PC에 연결합니다.
5. 주황 대기 비교나 별도 프로브는 추가하지 않습니다.

기록은 기존 kwce/dvd/playback-r21.log에 추가됩니다. 매체 내용/키/식별값은 기록하지 않습니다.
정상 재생과 실기 오류복귀는 아직 검증해야 합니다. 이 수정만으로 판독성공을 주장하지 않습니다.
''',encoding='utf-8')
    if a.revision==3:
        (out/readme).write_text("""KWCE DVD 비디오 장치 설정 보완 v3 — R55/native69

하드웨어 접근 권한과 DVD 비디오 명령 허용은 별개입니다.
IOS 전환 후 DI 초기화 전에 DVD 비디오 허용 비트를 확인하고 필요할 때만 설정합니다.
종료 시 드라이브를 닫은 뒤 이 실행이 변경한 비트만 복원합니다.
R54 실패 반환과 메뉴 source37/GC/캐시/읽기 명령은 유지합니다.
실제 판독 성공 여부는 아직 확인하지 않았습니다. NAND/IOS 설치는 없습니다.

1. Priiloader 기존 KWCE DVD 항목 ON, Save Settings. GC 항목 유지.
2. 같은 DVD를 넣고 완전 종료·전원선 분리 후 부팅.
3. 설정 진입/복귀 확인 후 디스크채널 시작 한 번.
4. DVD 메뉴/재생/자동복귀/정지 여부 확인 후 SD를 PC로 회수.
정지하면 반복하거나 장시간 기다리지 않습니다. HBC 프로브는 추가하지 않습니다.

기존 playback-r21.log에 dvd-video-mode의 전/후 값(-1=접근 불가,0=꺼짐,1=켜짐)을 추가합니다.
매체 내용/주소/키/콘솔 식별값은 기록하지 않습니다.
""",encoding='utf-8')
    if a.revision==4:
        (out/readme).write_text("""KWCE DVD 초기 판독 크기 보완 v4 — R56/native70

R55의 DVD 허용 비트는 이미1이었으므로 그 가설은 이번 실패를 설명하지 못했습니다.
R56은 성공한 HBC 프로브처럼 DI_Init 전에 libdi 캐시를 끕니다.
1섹터 요청을26섹터로 확대하지 않으며 MPlayer 상위 캐시는 유지합니다.
첫32요청의 크기/결과만 기록합니다. 디스크 주소/내용/키/식별값은 기록하지 않습니다.
R54 실패 반환·R55 상태 기록·GC/source37/배너/HOME을 유지합니다.
실제 판독 개선과 성능 영향은 미검증입니다. NAND/IOS 설치는 없습니다.

1. Priiloader 기존 KWCE DVD 항목 ON → Save Settings. GC 항목 유지.
2. 같은DVD 삽입 상태로 전원 종료·전원선 분리 후 부팅.
3. 본체 설정 왕복 확인 후 디스크채널 시작 한 번.
4. DVD메뉴/재생/자동복귀/정지 결과 확인 후 SD를 PC로 회수.
정지하면 장시간 기다리거나 같은 시험을 반복하지 않습니다.
별도 HBC 프로브·주황대기 비교는 추가하지 않습니다.

기록: 기존 kwce/dvd/playback-r21.log에 drive-cache/di-size를 추가합니다.
""",encoding='utf-8')
    if a.revision==5:
        (out/readme).write_text("""KWCE DVD 첫 읽기 비교 v5 — R57/native71

R56은 준비 완료 후 첫1섹터 읽기가 실패했습니다. 크기/허용 비트 변경만으로 해결되지 않았습니다.
R57은 성공한 HBC 프로브와 동일한 정렬 버퍼/세 구간 순서로 먼저1섹터씩 읽습니다.
각 단계의 준비 상태/반환값/선택된 읽기 모드만 기록하며, 실패하면 재시도 없이 반환합니다.
성공하면 기존 DVD 재생 경로로 이어집니다. 실기 판독 해결은 아직 미검증입니다.
기존 GC/메뉴/배너/로그를 보존하며 NAND/IOS 설치는 없습니다.

1. Priiloader 기존 KWCE DVD 항목 ON → Save Settings. GC 항목 유지.
2. 같은DVD 삽입 상태로 전원 종료·전원선 분리 후 부팅.
3. 본체 설정 왕복 확인 후 디스크채널 시작 한 번.
4. DVD메뉴/재생/자동복귀/정지 결과 확인 후 SD를 PC로 회수.
정지하면 장시간 기다리거나 같은 시험을 반복하지 않습니다.
기록: 기존 playback-r21.log의 first-read-begin/end/mode. 매체 내용/식별값 기록 없음.
""",encoding='utf-8')
    if a.revision==6:
        (out/readme).write_text("""KWCE DVD 제어 비트 방향 수정 v6 — R58/native72

앞선 R55~57은 DVD 차단 비트를 허용 비트로 잘못 해석해 설정했습니다.
홈브류 채널 실제 구현은 IOS 전환 뒤 이 비트를 지웁니다.
R58은 같은 방향으로 수정하고 자신이 바꾼 비트만 드라이브 종료 뒤 원복합니다.
이전 dvd-video-mode 1→1은 허용 상태의 증거가 아니었습니다.
새 dvd-disable-bit의1→0은 차단 해제,0→0은 이미 해제 상태를 뜻합니다.
기존 첫 읽기/오류 기록과 GC/메뉴를 유지합니다. NAND/IOS 설치 없음.
로컬 검증 완료 여부와 별개로 실제 DVD 재생 성공은 아직 미확인입니다.

1. Priiloader 기존 DVD 항목 ON → Save Settings. GC 항목 유지.
2. 같은 DVD 삽입 상태로 완전 종료·전원선 분리 후 부팅.
3. 본체 설정 왕복 확인 후 디스크채널 시작 한 번.
4. 결과 확인 후 전원을 끄고 SD를 PC로 연결.
장시간 정지 시 반복하지 않습니다. 별도 프로브는 필요하지 않습니다.
기록은 기존 playback-r21.log에 추가하며 매체 내용/키/식별값을 기록하지 않습니다.
""",encoding='utf-8')
    m=dict(kind=f'dvd-player-trace-v{a.revision}',nand_write=False,physical_dvd_verified=False,
           gc_changed=False,player_revision=player,hook_revision=hook,source_revision=37,
           qualification_sha256=sha(out/'qualification.json'),
           expected_inputs={r:hashlib.sha256(b).hexdigest()for r,b in old.items()},
           runtime_inputs=prior['runtime_inputs'],files={r:sha(out/r)for r in paths})
    raw=(json.dumps(m,ensure_ascii=False,indent=2)+'\n').encode()
    (out/'package-manifest.json').write_bytes(raw)
    (out/'package-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
    sd_files(out)
    print(f'PASS qualified R{player}/native{hook} package; no physical SD writes')


if __name__=='__main__':main()

"""Freeze the forwarder delivery (native74 + R59 on SD) after local qualification.

Reads the card's current definitions; performs no SD writes itself.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.dvd_forwarder_sd import (VERSIONS, CURRENT, MODULE, PLAYER_PATH, DEFINITIONS, TARGETS, names, paths, extra,
                                   previous_runtime, frozen_inputs, sd_files)
from kwce.dvd_player_trace_sd import upgrade
from kwce.dvd_integrated_sd import qualified
from kwce.gc_card_encoding_sd import wii_mount
from kwce.gcmce_recovery import sha

TEXT = '''KWCE DVD 소형 로더 방식 v1 — native76 / 재생기 R61

[고친 것]
1. 일반 채널 정지: 이전에는 Wii 메뉴가 떠 있는 내내 재생기 전체(약7.5MB)를
   메뉴 메모리에 올려 두어, 다른 채널이 쓸 작업 메모리가 모자랐습니다.
   이제 메뉴에는 약0.25MB의 소형 로더만 올리고, 재생기 본체는 시작을 누른 뒤
   SD의 kwce/dvd/player.dol에서 읽어 해시를 확인한 다음 실행합니다.
2. 재생 프레임 저하: 판독 실패 조사 때 꺼 두었던 드라이브 선행 읽기 캐시를
   원래대로 되돌렸습니다(실패 원인은 캐시가 아니라 DVD 차단 비트였습니다).

3. DVD 메뉴의 가장자리 버튼(다음 페이지 화살표 등): 포인터 좌표를 실제 영상
   표시 영역 기준으로 다시 계산합니다. 이전에는 화면 중앙에서 멀수록 어긋났습니다.
4. DVD 메뉴 첫 화면 깨짐/메뉴 이동이 두 번째에야 되는 현상: 재생기가 디스크에서
   0.8초 안에 데이터가 오지 않으면 스트림이 끝난 것으로 처리하던 부분을, 디스크
   재생에서는 15초까지 기다리도록 바꿨습니다(회전 시작·먼 위치 이동 대비).

메뉴 쪽 코드(source37)·GC 기능·배너·HOME 메뉴는 그대로입니다.
시스템 메뉴/IOS/WAD 설치는 없습니다. 1번은 격리 에뮬레이터에서 확인했고,
2~4번은 실제 드라이브가 있어야 확인되므로 실기 결과가 필요합니다.

[시험 순서]
1. SD 장착 → Priiloader의 KWCE DVD 항목 ON → Save Settings. GC 항목은 유지.
2. 같은 DVD를 넣고 완전 종료·전원선 분리 후 부팅.
3. 디스크 채널을 열기 전에 일반 채널 두세 개(홈브류 채널 포함)를 열어 봅니다.
4. 본체 설정 왕복 → 디스크 채널 시작. 시작 후 수 초 동안 검은 화면이 정상입니다
   (SD에서 재생기를 읽는 시간).
5. 재생 후 HOME → Wii 메뉴로 돌아와 다시 일반 채널을 열어 봅니다.
멈추면 반복하지 말고 Priiloader에서 DVD 항목을 OFF로 돌린 뒤 SD를 PC에 연결해 주세요.

[기록] 기존 kwce/dvd/playback-r21.log에 "forwarder 단계 값" 숫자 행이 추가됩니다.
1=정상 인계, 음수=실패 단계(-3 파일 없음, -4/-5 읽기 오류, -6 해시 불일치).
매체 내용·키·식별값은 기록하지 않습니다.
'''


TEXT2 = '''KWCE DVD 메뉴 표시·프레임 수정 v2 — native77 / 재생기 R64

[이전 판(v1)에서 확인된 것] 일반 채널 정지 해소, 소형 로더 인계 정상.

[이번에 고친 것] 사용자 DVD를 PC에서 읽어 에뮬레이터로 재현한 뒤 수정했습니다.
1. 첫 DVD 메뉴 깨짐 / 다음 페이지가 화면에 안 바뀜 / 타이틀·메뉴를 두 번 눌러야 이동:
   영상 디코더는 그림을 한 장 늦게 내보내는데, 메뉴는 정지 화면 한 장뿐이라 새 그림이
   디코더 안에 남고 이전 그림이 표시됐습니다. 정지 화면에 도달하면 남은 그림을
   내보내도록 했고, 앞부분만 잘린 그림은 디코드하지 않습니다.
2. 프레임 저하(재생): 필드 순서를 맞추는 동안 그리기 쪽이 다음 장을 덮어써 두 장 중
   한 장만 표시됐습니다(초당 약 15장). 표시된 뒤에 다음 장을 그리도록 했습니다.
3. 프레임 저하(메뉴): 정지 화면 갱신이 약 51ms 주기에 묶여 커서가 초당 19회만
   움직였습니다. 화면 주사율로 갱신합니다.
4. 재생 중 SD 기록 중단: 기록은 메모리에 모았다가 HOME을 열 때와 종료 때만 씁니다.
5. HOME 메뉴 배터리 칸 수를 본체 HOME 메뉴와 같은 기준으로 계산합니다.

에뮬레이터 측정: 메뉴 초당 60회 갱신, 재생 초당 30장·드롭 0.
실기에서는 아직 확인하지 않았습니다. 시스템 메뉴/IOS/WAD 설치는 없습니다.
Wii 메뉴에서 채널을 바꿀 때의 지연은 이번 판에서 다루지 않았습니다.

[시험 순서]
1. SD 장착 → Priiloader의 KWCE DVD 항목 ON → Save Settings. GC 항목은 유지.
2. 같은 DVD를 넣고 완전 종료·전원선 분리 후 부팅.
3. 디스크 채널 시작 → 첫 메뉴 화면, 커서 움직임, 다음/이전 페이지 확인.
4. 항목 재생 → 프레임 확인 → HOME → 타이틀 또는 메뉴를 한 번 눌러 복귀 확인.
5. HOME 메뉴의 배터리 표시 확인 → Wii 메뉴로 복귀.
이상이 있으면 반복하지 말고 SD를 PC에 연결해 주세요.

[기록] kwce/dvd/playback-r21.log에 perf-time/perf-frames/perf-read 숫자 행이 10초 단위로
남습니다(시각 ms·화면 갱신 수 / 프레임 수·드롭 수 / 디스크 읽기 ms·횟수).
매체 내용·키·식별값은 기록하지 않습니다.
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--drive', required=True); ap.add_argument('--qualification', required=True)
    ap.add_argument('--version', type=int, choices=tuple(VERSIONS), default=CURRENT)
    a = ap.parse_args(); card = Path(a.drive).resolve(); wii_mount(card)
    row = VERSIONS[a.version]; kind, readme, _ = names(a.version)
    q = Path(a.qualification); proof = qualified(q, row['hook'])
    if any(proof['checks'].get(k) is not True for k in extra(a.version)): raise ValueError('Qualification incomplete')
    out = ROOT/f'workspace/hardware/kwce-dvd-forwarder-v{a.version}'
    if out.exists(): raise ValueError('Existing numbered package preserved')
    runtime = previous_runtime(a.version)
    if any(sha(card/r) != h for r, h in runtime.items()): raise ValueError('Reviewed runtime changed')
    old = {r: (card/r).read_bytes() for r in DEFINITIONS}
    changed = {r: upgrade(old[r], row['previous_hook'], row['hook']) for r in TARGETS}
    module, player = frozen_inputs(a.version)
    out.mkdir()
    def put(rel, data):
        p = out/rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
    for rel, data in old.items(): put('expected/'+rel, data)
    for rel, data in changed.items(): put(rel, data)
    put(MODULE, module); put(PLAYER_PATH, player); put(readme, (TEXT if a.version == 1 else TEXT2).encode('utf-8'))
    put('qualification.json', q.read_bytes())
    m = dict(kind=kind, nand_write=False, gc_changed=False, physical_dvd_verified=False,
             player_revision=row['player'], hook_revision=row['hook'], source_revision=37,
             qualification_sha256=sha(out/'qualification.json'),
             expected_inputs={r: hashlib.sha256(b).hexdigest() for r, b in old.items()},
             runtime_inputs=runtime, files={r: sha(out/r) for r in paths(a.version)})
    raw = (json.dumps(m, ensure_ascii=False, indent=2)+'\n').encode()
    (out/'package-manifest.json').write_bytes(raw)
    (out/'package-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
    sd_files(out)
    print(f'PASS forwarder package v{a.version} frozen: RAM definitions + SD data only; no writes yet')


if __name__ == '__main__': main()

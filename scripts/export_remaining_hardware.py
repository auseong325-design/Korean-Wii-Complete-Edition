"""Stage reviewed channel-only Wii candidates without changing the SD card."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.hardware import local_reference_counts
from kwce.remaining_hardware import ROWS, DATA, README, sha, sd_files

def main():
    out = ROOT / 'workspace/hardware/kwce-remaining-sd-v1'
    if out.exists():
        raise SystemExit('Existing package preserved')
    lib = load_library()
    items = []
    for channel, revision, tid, name in ROWS:
        base = ROOT / 'workspace/channels' / channel / f'hardware-v{revision}'
        meta = json.loads((base / 'build-manifest.json').read_text(encoding='utf-8'))
        candidates = list(base.glob('*.wad'))
        if len(candidates) != 1 or not meta.get('hardware_candidate') or meta.get('local_only'):
            raise ValueError('Expected a single hardware candidate: ' + channel)
        data = candidates[0].read_bytes()
        if sha(data) != meta['wad_sha256']:
            raise ValueError('Candidate differs from build manifest: ' + channel)
        t = lib.title.Title()
        t.load_wad(data)
        if t.tmd.title_id.lower() != tid or not t.get_is_fakesigned():
            raise ValueError('Candidate title/signature differs: ' + channel)
        for i in range(len(t.tmd.content_records)):
            t.get_content_by_index(i)
        counts = local_reference_counts(t)
        if counts != meta['hardware_checks']['local_reference_counts']:
            raise ValueError('Candidate endpoint counts differ: ' + channel)
        items.append((f'{DATA}/{name}', data, counts))
    text = '''KWCE 신규 채널 실기 시험 후보 (기존 Wii 전용)

이 폴더의 6개 WAD는 전부 미완성 시험 후보입니다. 이 파일을 SD에 복사한 것만으로는 Wii에 설치되지 않습니다.
Homebrew Channel의 기존 Some YAWMM Mod에서 SD를 선택하고 wad/KWCE-remaining-v1 폴더의 파일을 하나씩 설치하세요.
서명 검사 패치가 있는 기존 cIOS가 필요합니다. cIOS 설치나 시스템 메뉴/IOS WAD 설치는 하지 마세요.
각 파일을 선택할 때 Install을 확인하세요. Uninstall 또는 삭제를 선택하지 마세요.

01 주소 설정 v2: 숨김 채널입니다. 카메라 프린트와 음식 배달보다 먼저 설치하세요.
02 인터넷 v5
03 커비 TV v3
04 디지털 카메라 프린트 v5: 주소 설정에서 주소 자료를 먼저 저장해야 합니다.
05 음식 배달 v4: 주소 자료가 필요하며 가게 목록 오류 339293이 아직 미해결입니다.
06 Wii 스피크 v1: 공식 한국판 채널에 Wiimmfi 접속 패치를 적용한 후보; USB 마이크 필요.

각 채널 설치 결과를 확인한 후 Wii 메뉴에서 별도로 실행해 시험하세요. 주소 설정은 메뉴에 아이콘이 보이지 않을 수 있습니다.
실기 정상 실행·서비스 접속은 아직 확인되지 않았습니다. 주문, 결제, 사진 업로드 등 실제 전송은 시험하지 마세요.
기존 앱, Priiloader 설정, 세이브 및 SD의 기존 파일은 이 복사 작업에서 삭제하지 않았습니다.
'''.encode('utf-8')
    items.append((README, text, None))
    records = []
    for relative, data, counts in items:
        p = out / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        rec = dict(path=relative, bytes=len(data), sha256=sha(data))
        if counts is not None:
            rec['local_reference_counts'] = counts
        records.append(rec)
    record = dict(kind='remaining-six-wii-channels-v1', system_title_included=False,
                  hardware_verified=False, sd_files=records)
    raw = (json.dumps(record, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    (out / 'package-manifest.json').write_bytes(raw)
    (out / 'package-manifest.sha256').write_text(sha(raw) + '\n', encoding='ascii')
    sd_files(out)
    print('PASS: six channel candidates verified and staged; no console installation performed')

if __name__ == '__main__':
    main()

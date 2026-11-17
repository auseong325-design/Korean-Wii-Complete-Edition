"""Create-once, isolated SD package for Photo Prints hardware-v6."""
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.photoprints_sd_v6 import WAD,README,sha,sd_files
from build_photoprints_region_v6 import build

def main():
    out=ROOT/'workspace/hardware/kwce-photo-region-sd-v1'
    if out.exists(): raise SystemExit('Existing SD package preserved')
    generated,meta=build()
    source=ROOT/'workspace/channels/photoprints/hardware-v6/photoprints-ko-hardware-test.wad'
    if source.read_bytes()!=generated: raise ValueError('Candidate is not reproducible')
    guide='''디지털 카메라 프린트 r6 실기 시험\n\n이 후보는 기존 r5의 일본 지역 메타데이터만 한국 지역으로 조정한 것입니다. 채널 내용과 WiiLink 주소는 동일합니다. 실기 실행 결과는 미검증입니다.\nHomebrew Channel → Some YAWMM Mod → 기존 서명 패치 IOS249 → Wii SD Slot → WAD/KWCE-photo-r6 → Photo-Prints-r6.wad → Install WAD.\n주소 설정 채널은 이미 설치되어 있어야 하며, 등록한 주소 자료가 필요합니다. 이전 r5와 같은 채널을 갱신합니다. 설치·시험 결과와 오류 코드를 기록해 주세요.\n'''.encode('utf-8')
    records=[]
    for name,data in [(WAD,generated),(README,guide)]:
        p=out/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        records.append(dict(path=name,bytes=len(data),sha256=sha(data)))
    raw=(json.dumps(dict(kind='photo-region-trial-v6',hardware_success_verified=False,sd_files=records),indent=2)+'\n').encode('utf-8')
    (out/'package-manifest.json').write_bytes(raw)
    (out/'package-manifest.sha256').write_text(sha(raw)+'\n',encoding='ascii')
    sd_files(out);print('PASS: Photo Prints r6 SD trial staged and verified')
if __name__=='__main__':main()

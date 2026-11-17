"""Export a private News-only candidate; no installer, system files or SD writes."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.hardware import hardware_wad,fakesigned

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--revision',type=int,required=True);args=parser.parse_args()
    if args.revision<15:raise SystemExit('Use the memory-reduced candidate')
    base=ROOT/'workspace/channels/news';build=base/f'build-v{args.revision}'
    metadata=json.loads((build/'build-manifest.json').read_text(encoding='utf-8'));source=build/metadata['wads']['personal']['file']
    raw=source.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=metadata['wads']['personal']['sha256']:raise ValueError('Build hash')
    original=(base/'originals/news-usa-wiilink-archive.wad').read_bytes()
    wad,record=hardware_wad(raw,original);restore,_=fakesigned(original)
    root=ROOT/'workspace/hardware';number=1
    while(root/f'news-candidate-v{number}').exists():number+=1
    out=root/f'news-candidate-v{number}';out.mkdir()
    (out/'news-ko-personal-fakesigned.wad').write_bytes(wad)
    (out/'news-wiilink-original-fakesigned.wad').write_bytes(restore)
    (out/'candidate-manifest.json').write_text(json.dumps(dict(revision=args.revision,hardware_tested=False,loading_fix_verified_on_hardware=False,channel_only=True,installer_included=False,record=record,wad_sha256=hashlib.sha256(wad).hexdigest()),indent=2),encoding='utf-8')
    (out/'README-ko.txt').write_text('뉴스 메모리 보완 후보본입니다. 실기 무한 로딩 해결은 미확인입니다.\n설치 도구·시스템 메뉴·IOS·설정·세이브는 포함하지 않습니다.\n공개 뉴스 파일 만료 및 실기 수신 상태는 별도 확인이 필요합니다.\n이 폴더를 기존 배포 스크립트의 전체 SD 패키지로 사용하지 마세요.\n',encoding='utf-8')
    print(f'News-only candidate {number}: build-v{args.revision}; hardware fix unverified; SD untouched')
if __name__=='__main__':main()

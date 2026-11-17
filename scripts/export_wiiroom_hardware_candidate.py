"""Private channel-only Room candidate, with no SD writes or system resources."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.hardware import hardware_wad,fakesigned

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--revision',type=int,choices=[11,13,15,17,21,23,55],default=55);args=parser.parse_args()
    base=ROOT/'workspace/channels/wiiroom';build=base/f'build-v{args.revision}'
    metadata=json.loads((build/'build-manifest.json').read_text());raw=(build/'wiiroom-ko-local-test.wad').read_bytes()
    if metadata['target']!='hardware'or hashlib.sha256(raw).hexdigest()!=metadata['wad_sha256']:raise ValueError('Hardware candidate identity')
    original=(base/'originals/wiiroom-english-wiilink-archive.wad').read_bytes();wad,record=hardware_wad(raw,original);restore,_=fakesigned(original)
    number=1;root=ROOT/'workspace/hardware'
    while(root/f'wiiroom-candidate-v{number}').exists():number+=1
    out=root/f'wiiroom-candidate-v{number}';out.mkdir()
    (out/'wiiroom-ko-personal-fakesigned.wad').write_bytes(wad);(out/'wiiroom-original-fakesigned.wad').write_bytes(restore)
    (out/'candidate-manifest.json').write_text(json.dumps(dict(revision=args.revision,channel_only=True,installer_included=False,hardware_success_verified=False,loading_fix_verified=False,record=record,wad_sha256=hashlib.sha256(wad).hexdigest()),indent=2))
    (out/'README-ko.txt').write_text('Wii의 방 실기 재시험 후보입니다. 무한 로딩 해결은 실기 미확인입니다.\n원래 WiiLink 초기 주소와 NAND 파일 처리를 유지합니다.\n한글 리소스 선택·UI/로고/HOME 번역을 반영했습니다.\n채널 WAD만 포함하며 IOS·시스템 메뉴·인증·세이브·설정·설치 앱은 포함하지 않습니다.\n전체 SD 배포 패키지가 아닙니다.\n',encoding='utf-8')
    print('Room-only private candidate',number,'build',args.revision,'; hardware loading fix unverified; SD untouched')
if __name__=='__main__':main()

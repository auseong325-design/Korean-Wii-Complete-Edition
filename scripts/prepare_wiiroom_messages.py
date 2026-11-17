"""Local-only Wii Room message preparation; no original text on stdout."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import sha256

COMMON={'OK':'확인','Yes':'예','No':'아니요','Cancel':'취소','Back':'뒤로','Next':'다음','Close':'닫기','Return':'돌아가기','Quit':'종료','Save':'저장','Delete':'삭제','Start':'시작','Settings':'설정','Options':'설정','Search':'검색','Help':'도움말','Loading...':'불러오는 중...','Connecting...':'접속 중...','Please wait.':'잠시 기다려 주세요.','Please wait...':'잠시 기다려 주세요.','Wii Menu':'Wii 메뉴','HOME Menu':'HOME 메뉴','Continue':'계속','Confirm':'확인','Accept':'동의','Decline':'동의 안 함','Agree':'동의','Disagree':'동의 안 함','Register':'등록','Change':'변경','Done':'완료','Today':'오늘','Tomorrow':'내일','Yesterday':'어제','Birthday':'생일','Name':'이름','Gender':'성별','Male':'남성','Female':'여성','English':'영어','Japanese':'일본어','Wii Room':'Wii의 방','Wii no Ma':'Wii의 방','Error':'오류','Retry':'다시 시도','Reset':'초기화','Send':'보내기','Receive':'받기','Friends':'친구','Family':'가족','Calendar':'달력','Movies':'동영상','Videos':'동영상','Recommended':'추천','New':'새 소식','More':'더 보기','View':'보기','Watch':'시청','Stop':'정지','Play':'재생','Pause':'일시 정지','Resume':'계속 재생','Volume':'음량','On':'켜기','Off':'끄기'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--offline-draft',action='store_true');args=ap.parse_args()
    base=ROOT/'workspace/channels/wiiroom/analysis';messages=json.loads((base/'messages.json').read_text(encoding='utf-8'))
    mapping=json.loads((base/'matched-translations.json').read_text(encoding='utf-8'))
    for row in messages:
        if row['text'].strip()in COMMON:mapping[str(row['index'])]=COMMON[row['text'].strip()]
    config=dict(source_sha256='533ac68bc2b7267e52a18c48acf423c3f86c1e97641962d62a1991c630457d8c',messages=mapping,reviewed_common_only=True,full_localization_complete=False)
    target=ROOT/'configs/wiiroom-messages-ko.json'
    if target.exists():raise SystemExit('Existing reviewed mapping preserved')
    target.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8');print('Reviewed common message slots:',len(mapping),flush=True)
    if args.offline_draft:
        from kwce.local_mt import translate,model_record
        draft={};needed=[r for r in messages if r['text'].strip()and str(r['index'])not in mapping]
        out=base/'offline-draft-v1.json'
        if out.exists():raise SystemExit('Existing offline draft preserved')
        for start in range(0,len(needed),24):
            chunk=needed[start:start+24];results=translate([r['text']for r in chunk])
            draft.update({str(r['index']):dict(source_sha256=sha256(r['text'].encode()),target=t)for r,t in zip(chunk,results)})
            print('Offline draft progress:',min(start+24,len(needed)),'/',len(needed),flush=True)
        out.write_text(json.dumps(dict(model=model_record(),unreviewed=True,messages=draft),ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()

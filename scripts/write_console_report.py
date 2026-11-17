"""Generate the non-identifying console report from local SysCheck + audit."""
import json,re
from audit_sd import ROOT, SD, PRIVATE

def main():
    s=(SD/'SysCheck.csv').read_text(encoding='utf-8-sig').replace('\r','')
    ios=re.findall(r'^(IOS\d+(?:\[[^\]]+\])?) \(rev (\d+)(?:, Info: ([^)]+))?\): (.+)$',s,re.M)
    rows=json.loads((PRIVATE/'nand-audit.json').read_text(encoding='utf-8'))
    nand=next(r for r in rows['backups'] if r['path']==rows['selected_source'])
    lines=['# 실기 상태 기준 보고서','', '기준일: 2026-10-21 (Asia/Seoul). [직접 확인]은 제공된 파일을 읽거나 로컬에서 복호화한 결과다. 실제 Wii를 이번 작업에서 조작했다는 뜻이 아니다. 시리얼·콘솔 ID·MAC·IP·SSID·인증 정보는 생략한다.','',
    '## 하드웨어·지역·화면','',
    '| 항목 | 직접 확인한 값 | 한계 |','|---|---|---|',
    '| 모델 | NAND setting.txt: RVL-001(KOR) | 외부 케이스·기판·포트 육안 검사 미실시 |',
    '| 지역/언어 | SysCheck KOR, WiiMedic South Korea/NTSC-K/Korean; NAND AREA=KOR, GAME=KR, VIDEO=NTSC | 지역 변경 이력은 보고서만으로 배제 불가 |',
    '| 메뉴 | SysCheck 4.3K v518; 새 NAND TMD v518 | 두 자료는 별도 시점 |',
    '| 칩/드라이브 | Hollywood 0x11, SysCheck drive date 02.13.2007 | 드라이브 날짜는 DVD 비디오/레코더블 읽기 성공 증거 아님 |',
    '| 화면 | WiiMedic 16:9, progressive enabled, NTSC 480i/480p | NAND SYSCONF IPL.AR=1, IPL.PGS=1과 일치 |',
    '| SYSCONF | IPL.LNG=9(Korean), IPL.SADR 첫 바이트=136(Korea) | 원본과 보존 프로필 해시 비교 |',
    '| GameCube | WiiMedic active 0/4, Wii Remote 1/4 | 연결/활성 수치이며 포트 부재·고장·기능 복원 필요성 확정 불가 |',
    '| 메모리 | WiiMedic MEM1 free 22536KB, MEM2 free 53011KB | 당시 앱의 free arena, RAM 전수검사 아님 |','',
    '## 시스템 소프트웨어','',
    '- [직접 확인] SysCheck ME v2.5.0, IOS58 rev6176에서 실행, 생성일 2026-10-21. HBC 1.1.2 / IOS58, Boot2 v4. 타이틀 110개, IOS 51개, stub 4개.',
    '- [직접 확인] 주요 IOS: IOS58 rev6176 USB2.0, IOS80 rev16174 Trucha/NAND 패치. 메뉴 TMD의 의존 IOS는 title 00000001-00000050(IOS80). 순정 IOS80으로 간주하지 않는다.',
    '- [직접 확인] BC(title 00000001-00000100) v6, MIOS(title 00000001-00000101) v10. 설치되어 있다는 사실은 GameCube 디스크/포트/게임 실행 성공을 뜻하지 않는다.',
    '- [직접 확인] Priiloader installed(SysCheck), Installed (Unknown)(WiiMedic). BootMii IOS254 rev65281. SD bootmii/에 지원 파일 존재.',
    '- [직접 확인] HackMii installer.log는 boot1 때문에 boot2 설치 불가(-2), BootMii IOS만 가능이라고 기록한다. WiiMedic의 Likely compatible과 충돌한다. 복구 판단은 RECOVERY_RISK.md 참조.',
    '- [직접 확인] 새 NAND에는 Priiloader 관련 1000009e.app, title_or.tmd가 존재한다. 보관된 원본 메뉴 실행 파일 SHA-1이 wii-ipl 43K 기준과 일치한다. 설치된 Priiloader의 구체적 버전·활성 hacks는 미확정이다.','',
    '### IOS 전체 목록 (SysCheck)','', '| 슬롯/베이스 | 리비전 | 계열 정보 | 보고된 특성 |','|---|---:|---|---|']
    lines += [f'| {slot} | {rev} | {info or "—"} | {flags} |' for slot,rev,info,flags in ios]
    lines += ['', '### 패치·이력 해석','',
    '- [직접 확인] Stub: IOS4 r65280, IOS10 r768, IOS16 r512, IOS51 r4864. Stub 존재만으로 이상 설치라고 결론내리지 않는다.',
    '- [직접 확인] Hermes 계열 202/222/223/224, IOS236, d2x-v11beta1 248/249/250/251. SysCheck가 표시한 베이스와 revision을 위 표에 보존했다.',
    '- [직접 확인] IOS11/20/30/40/50/52/60/70/80은 모두 r16174, Trucha/NAND 패치를 보고한다. IOSsyscheck.log에서도 이 슬롯들의 base hash가 서로 같다.',
    '- [추정] 위 저슬롯 IOS는 IOS60 계열 기반의 공통 패치 묶음일 가능성이 높다. SD WAD 이름에 IOS60v6174 기반 FS/ES/NP/VP/DIP 표기가 있지만, 파일 존재만으로 설치 주체·설치 시점·현재 바이트 일치를 확정하지 않는다.',
    '- [직접 확인] SD의 오래된 d2x-v8/IOS36 WAD와 현재 SysCheck 결과는 버전이 다르다. SD 파일명을 현재 설치 상태로 옮겨 적지 않았다.',
    '- [직접 확인] IOSsyscheck.log에는 BC/MIOS를 IOS256/257 형식으로 표시한 항목도 있다. 이 두 항목을 SysCheck의 일반 IOS 51개에 추가해 이중 집계하지 않는다.','',
    '## NAND·저장장치·네트워크','',
    '- [직접 확인] WiiMedic NAND: used 11076/32768 clusters, free 21692, used 5075/6143 inodes, free 1068, Health 95/100 GOOD. Ticket Groups=-1. IOS Scan과 Storage Test는 Not run yet로 명시되어 있다.',
    '- [한계] 보고서 점수는 ECC/HMAC·플래시 수명·SD/HDD 실제 속도·배드블록 전수검사가 아니다. 새 NAND SFFS FAT의 free=9988, reachable FST=1068 등과 보고서 사용량은 측정 정의/시점이 달라 그대로 비교할 수 없다.',
    '- [직접 확인] WiiMedic WiFi Module Working, WiFi Connected와 IP 할당을 보고하지만 WiFi Card Info INVALID도 함께 기록한다. AP 스캔 결과는 존재한다. 인터넷 또는 WiiLink 등록 성공은 입증하지 못한다.',
    '- [직접 확인] SD에 apps/bootmii/private/WAD/wads/wii/backups와 로더·홈브류·설정 파일이 있다. 총 파일/크기는 SD manifest 참조. apps의 설치 파일 존재는 실기 설치 증거와 구분한다.',
    '- [직접 확인] SD 앱 메타데이터에서 nanddumper@IOS v1.1을 확인했다. 원본 NAND/키와 체크섬 파일은 전부 보존했다.','',
    '## NAND 스냅샷 교차검증','',
    f"- 새 기준 NAND: 복호화 TMD {len(nand['titles'])}개. IOS58/80/254, BC/MIOS 버전은 SysCheck 핵심 값과 일치한다. SD 루트 NAND는 98개 TMD로 새 NAND(110개)와 다른 상태다.",
    '- 콘텐츠 TMD 레코드 912개를 검사했다. shared1/content.map으로 공유 콘텐츠를 해석한 후에도 로컬 파일 없는 레코드 78개(시스템 분류 1, 00010000 분류 22, 00010001 분류 55)가 있다. 이 항목은 설치 메타데이터만 남은 디스크/채널 흔적 등을 포함할 수 있으며, 전부 NAND 손상이라고 단정하지 않는다.',
    '- 실제 존재하는 파일 중 00010008-48414b4b, content 00000002(index2)는 크기는 맞지만 TMD SHA-1이 다르다. 수정된 채널/리소스인지 손상인지 추가 조사 필요. System Menu v518의 7개 콘텐츠는 공유 콘텐츠까지 모두 TMD 크기·SHA-1이 일치한다.',
    '- TMD 서명·티켓 서명·모든 홈브류의 출처·실기 부트 체인 검증은 하지 않았다. 상세 비공개 목록은 workspace/private/title-content-audit.json에 있다.','',
    '## 복구 판단과 다음 조사','',
    'HBC·Priiloader·BootMii/IOS 설치 및 두 NAND/키 쌍이 확인되지만 완전한 브릭 복구를 보증하지 않는다. 물리 포트 테스트, 스토리지 테스트, Priiloader RESET 진입, 실기 BootMii 진입·복구는 미검증이다. 이번 단계에서는 실기 설치·삭제·복원이나 네트워크 설정 변경을 하지 않았다.','',
    '[BootMii 공식 FAQ](https://bootmii.org/faq/) · [Priiloader 공식 저장소](https://github.com/DacoTaco/priiloader) · [Dolphin NAND importer 소스](https://github.com/dolphin-emu/dolphin/blob/2609a/Source/Core/DiscIO/NANDImporter.cpp)']
    (ROOT/'docs/reference/CONSOLE_BASELINE.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Console baseline generated, IOS rows:',len(ios))

if __name__=='__main__':main()

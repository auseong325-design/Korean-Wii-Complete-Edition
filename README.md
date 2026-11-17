# KWCE — Korean Wii Complete Edition (베타)

국내판 Wii(RVL-001, 시스템 메뉴 4.3K)용 비공식 패치.

- 막혀 있던 **게임큐브 디스크 실행·메모리카드 관리** 복원, 디스크 채널에서 **DVD 재생**(선택)
- 한국에 출시되지 않은 채널 한글화: 날씨, 뉴스, 모두의 투표, Mii 콘테스트, Wii의 방, 닌텐도 채널, 인터넷, 커비 TV, 디지털 카메라 프린트, 음식 배달, TV 가이드, 주소 설정, Wii 스피크 (온라인 기능은 [WiiLink](https://wiilink.ca) 서비스 이용)

## 다운로드

[Releases](../../releases)에서 `KWCE-Patcher-…-win.zip`을 받으세요. 닌텐도 파일은 들어 있지 않고, 패처가 PC에서 닌텐도 업데이트 서버·WiiLink 서버의 원본을 받아 패치합니다.

## 사용법

준비물: 홈브류 채널, d2x cIOS 249, Priiloader가 설치된 국내판 Wii ([wii.hacks.guide](https://wii.hacks.guide/)), FAT32 SD 카드, Windows 10/11(64비트). 시작 전에 BootMii로 NAND 백업을 권장합니다.

1. zip 압축을 모두 풀고 `KWCE-Patcher.bat` 실행 → 번호 선택 (SD 카드를 꽂아 두면 바로 복사)
   - 빠른 설정: 채널 전체 + 게임큐브·DVD (처음 약 430MB 받음, Wii 저장 메모리 약 2,410블록)
   - 게임큐브·DVD만: 약 20MB
2. Wii: 홈브류 채널 → KWCE Channel Installer
   - 채널: +(START) → 1(전체 설치)
   - 게임큐브·DVD: -(GC L) → 1 또는 2, 그다음 RESET을 누른 채 전원을 켜서 Priiloader → System Menu Hacks에서 KWCE 항목을 켜고 저장
3. 연결 오류(NEWS000006 등)가 나면 [sntp](https://oscwii.org/library/app/sntp)로 Wii 시계를 맞추세요(시간대 UTC+9).

되돌리기: 설치 도구 +(START) → 2(전체 복원), Priiloader에서 KWCE 항목 끄고 저장. 자세한 내용은 zip 안의 `README-ko.txt`.

## 주의

베타입니다. 한 대의 국내판 Wii에서만 시험했습니다. 사용에 따른 책임은 사용자에게 있습니다. 비공식 팬 프로젝트이며 닌텐도·WiiLink와 관계없습니다.

## 라이선스

KWCE 코드는 GPL-3.0(`LICENSE`). 포함된 구성 요소(libWiiPy, WiiMC 포크, WiiLink Set Personal Data 포크, Noto Sans KR 등)의 라이선스와 전체 대응 소스는 릴리스의 `KWCE-source-…zip`에 있습니다. 온라인 서비스는 WiiLink 팀 덕분입니다.

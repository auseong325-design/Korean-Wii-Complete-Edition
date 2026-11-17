KWCE 소스 (GPL-3.0, LICENSE)

- kwce/ scripts/ homebrew/ configs/ tests/ : KWCE 소스 (패처, 설치 도구, DVD 로더, 채널 패치 생성)
- third_party/wiimc-fae733f.zip + generated/wiimc-kwce-r66 : DVD 재생기(WiiMC 포크, GPLv3).
  원본에 generated 폴더를 덮어쓰면 빌드한 소스입니다. r31은 예전 DVD Player 채널용.
- third_party/set-personal-data-18fa5a7d + generated/set-personal-data-kwce-r2 : 주소 설정(WiiLink SPD 포크, GPL-3.0).
  third_party/libpatcher-3e51f23a (MIT), third_party/NotoSansKR-OFL.txt (글꼴 라이선스).
- generated/*/KWCE-REMOVED.txt 에 적힌 파일은 원본에서 지웁니다.
- Mail Patcher·Account Linker의 소스는 SD 파일 안 source.zip에 있습니다.
- 도구 판은 configs/*.lock.json. 닌텐도 파일·키는 들어 있지 않습니다.

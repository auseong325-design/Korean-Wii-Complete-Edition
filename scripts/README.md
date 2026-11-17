# scripts 목록

Linux에서는 `.venv-linux/bin/python`을 사용한다. [Linux 설정/실행 안내](../docs/LINUX.md), `setup_linux.sh`, `launch_linux_dolphin.py`, `linux_dolphin_ui.py`가 새 진입점이다. 기존 Windows 전용 스크립트의 지원 여부와 이식 범위는 안내 문서를 따른다.
스크립트는 서로 import하므로(`audit_sd`, `launch_dolphin`, `prepare_channel_access` 등) 한 폴더에 둔다. 필요한 것만 찾아 쓰고, **기록용** 표시는 지난 리비전을 재현할 때만 쓴다. 실행은 프로젝트 루트에서 `.venv\Scripts\python.exe scripts\<name>.py`.

## 매일 쓰는 것

더블클릭용 모음은 [Emulator_BAT](../Emulator_BAT/README.md)다. `sync_emulator_bats.py`는 활성 카탈로그·메뉴 설정에서 BAT/안내를 생성하고(`--check`는 읽기 전용), `run_emulator_shortcut.py <이름> [--dry-run]`는 현재 허용된 실행 명령을 선택한다. `check_all.py`는 BAT 모음도 자동 갱신한다.

| 스크립트 | 용도 |
|---|---|
| `check_all.py [--quick]` | 전체 점검 한 줄 요약(설치 일치, 모든 launcher `--check`, 테스트, GC, SD) |
| `dolphin_ui.py` | Dolphin 렌더 창 focus/shot/point/click/key/log/stop ([docs/TESTING.md](../docs/TESTING.md)) |
| `review_channel_installations.py [--json]` | 카탈로그 `installs` 12개의 빌드·설치 일치 |
| `audit_sd.py --verify` | SD 원본 전체 SHA-256 대조 |
| `verify_environment.py [--full-sd]` | 도구·lock·제외 규칙 점검 |

## 채널 실행 (capability 0 launcher)

| 채널 | 실행 | 설치 / 피드 |
|---|---|---|
| 날씨 | `run_forecast_test.py [--offline/--menu]`, `launch_forecast.py [--menu/--check/--cache-preview/--manual-capture]` | `install_forecast.py`, `refresh_public_forecast.py`, `seed_forecast_cache.py` |
| 뉴스 | `launch_channel_feed.py news [--menu/--check]` | `install_news.py`, `seed_news_cache.py`, `make_news_manual_sample_feed.py [--restore]` |
| 투표·Mii·닌텐도 | `run_channel_test.py <channel> [--menu/--check/--mii-setup]` | `install_access_build.py <ch> --build N --access M`, `make_channel_access_fixtures.py` |
| Wii의 방 | `launch_wiiroom.py [--menu/--check/--probe]` | `install_wiiroom_test.py --revision N`, `refresh_wiiroom_fixtures.py`(생성기 `prepare_wiiroom_test.py`) |
| GC | `launch_dolphin.py --profile gc-native-v6-user [--menu/--check]` | — |

보존 프로필용 이전 launcher(기록용): `launch_news.py`, `launch_votes.py`, `launch_nintendo.py`, `launch_mii_contest.py`.

## 실기 적용 (알파)

`export_hardware_package.py`(SD 패키지 생성), `deploy_to_sd.py <package> --drive H: [--dry-run]`(실기 SD 복사, 사용자 지시 시), `prepare_hardware_test.py --package kwce-alpha-vN`, `launch_hardware_test.py [--check]` — [docs/hardware/README.md](../docs/hardware/README.md).

## 빌드

`build_forecast.py`, `build_news.py`, `build_votes_ui.py`(투표 v11+), `build_votes.py`(v1, 기록용), `build_mii_contest.py`, `build_nintendo.py`, `build_wiiroom.py` — 모두 `--revision N`, 기존 번호 덮어쓰기 거부. 개인 델타 내보내기: `export_*_patch.py`.

## 원본 확보·분석·번역 초안

`acquire_*.py`(원본 보존), `analyze_*.py`, `summarize_nintendo_*.py`, `probe_nintendo_list_header.py`, `analyze_channel_access_format.py`, `fetch_wiiroom_references.py`, `lock_channel_access_sources.py`, `prepare_wiiroom_messages.py`, `draft_*.py`(로컬 모델 초안, 미검수).

## 테스트 NAND 준비 (대부분 1회성, 기록용)

`prepare_<channel>.py`(GC v6 복제로 채널 NAND 생성), `prepare_channel_access*.py`, `prepare_channel_local_settings.py`, `prepare_votes_local_settings.py`, `prepare_channel_sandbox.py`, `prepare_feed_sandbox.py`, `build_channel_access_helper.py`, `build_wiiroom_helper.py`, `build_forecast_manual_helper.py`, `prepare_channel_test_controls.py`, `prepare_news_feed_controls.py`, `prepare_news_feed_tasks.py`, `prepare_news_location_glyphs.py`, `prepare_nintendo_access_logging.py`, `prepare_nintendo_service_locale.py`, `prepare_mii_local_nas.py`, `prepare_forecast*.py`, `forecast_profile.py`.

Mii·설명서 보조: `prepare_synthetic_test_mii.py`, `apply_ui_created_test_mii.py`, `index_channel_test_mii.py`, `prepare_mii_manual_test_avatars.py <channel>`, `prepare_mii_manual_captures.py`, `prepare_forecast_manual_captures.py`.

## 검증 (채널·GC)

`verify_channels.py`, `verify_news.py`, `verify_news_runtime.py`, `verify_votes.py`, `verify_mii_contest.py`, `verify_mii_local_fixtures.py`, `verify_channel_access_preservation.py`, `verify_gc_native.py`, `verify_phase1.py`, `inspect_dolphin_fst.py`, `inspect_gc_card_state.py`, `test_launcher_guards.py`.

## GC·Phase 0 (기록용)

`build_gc_v2.py`, `prepare_gc_v5.py`, `prepare_gc_v6.py`, `prepare_gc_sandbox.py`, `seed_gc_fixture.py`, `seed_gc_raw_fixture.py`, `stage_gc_test_disc.py`, `catalog_disc.py`, `audit_nand.py`, `audit_titles.py`, `extract_nand_local.py`, `finalize_import.py`, `write_console_report.py`, `prepare_offline_dolphin.py`, `prepare_dolphin.py`, `prepare_devkit.py`, `prepare_wii_ipl.py`, `smoke_toolchain.py`, `sync_sources.py`, `Enter-Environment.ps1`.

## C# helper 소스

`AppContainerRunner.cs`, `FeedRunner.cs`, `FeedServer.cs`, `ChannelTestServer.cs`, `NetProbe.cs`, `FstAtomicProbe.cs` — 컴파일된 helper는 `tools/`·`workspace/sandbox/*`에 고정 해시로 있다. 소스를 고치면 새 helper 리비전을 만든다.

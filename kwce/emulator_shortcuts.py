"""Generate portable BAT entry points; resolve active installs without a shell."""
import json
import os
import re
import shlex
import tempfile
from pathlib import Path

FOLDER='Emulator_BAT'
MARKER=b'KWCE-GENERATED-EMULATOR-SHORTCUT'
CHANNEL_COMMANDS={
    'forecast':('scripts/run_forecast_test.py','--offline'),
    'news':('scripts/launch_channel_feed.py','news'),
    'votes':('scripts/run_channel_test.py','votes'),
    'nintendo':('scripts/run_channel_test.py','nintendo'),
    'mii-contest':('scripts/run_channel_test.py','mii-contest'),
    'wiiroom':('scripts/launch_wiiroom.py',),
    'tvguide':('scripts/launch_tvguide.py',),
    'dvd-player':('scripts/launch_dvd_test.py',),
    'personal-data':('scripts/launch_personal_data.py',),
    'internet':('scripts/launch_internet.py',),
    'kirbytv':('scripts/launch_kirbytv.py',),
    'photoprints':('scripts/launch_photoprints.py',),
    'food':('scripts/launch_food.py',),
}
# Launchers without a reviewed --menu mode. personal-data is a hidden title
# (no Wii Menu icon); the others have no menu mode yet.
NO_MENU={'personal-data','kirbytv','photoprints'}


def plans(catalog,settings):
    if catalog.get('schema')!=2 or settings.get('schema')!=1:raise ValueError('Unsupported launcher catalog')
    profile=settings['system_menu_profile']
    match=re.fullmatch(r'gc-native-v([1-9][0-9]*)-user',profile)
    if not match or int(match[1])<6:raise ValueError('Only the current GC native test profile is allowed')
    result={'01_System_Menu':dict(label='시스템 메뉴 · GC v'+match[1],profile=profile,artifact='GC v'+match[1],
        argv=['scripts/launch_dolphin.py','--profile',profile,'--menu'])}
    if settings.get('include_installer_emulator')is True:
        result['02_Installer_Emulator']=dict(label='설치 앱 에뮬레이터 시험대 (실기 아님)',profile='hardware-test-v1',
            artifact='시험대에 준비된 설치 앱',argv=['scripts/launch_hardware_test.py'])
    if settings.get('include_mail_preview')is True:
        result['03_Mail_Preview']=dict(label='Wii 알림판 메일 · 등록 불가 한글 도구 미리보기',profile='mail-test-v1',artifact='화면 검수 전용',argv=['scripts/launch_wii_mail_preview.py'])
    if settings.get('include_dvd_test')is True:
        if settings.get('dvd_test_profile','dvd-test-v1')not in('dvd-test-v1','dvd-test-v2','dvd-test-v3'):raise ValueError('Unapproved DVD test profile')
        result['04_DVD_Player_Test']=dict(label='DVD 플레이어 · 준비된 ISO 자동 재생 (디스크 삽입 불필요)',profile=settings.get('dvd_test_profile','dvd-test-v1'),
            artifact='시험대 SD에 준비된 플레이어',argv=['scripts/launch_dvd_test.py'])
    dvd_menu=settings.get('dvd_menu_profile')
    if dvd_menu in ('dvd-test-v2','dvd-test-v3'):
        result['05_DVD_Disc_Channel']=dict(label='DVD 디스크 채널 배너 · 합성 디스크 자동 삽입 → 시작 → 재생',profile=dvd_menu,artifact='통합 DVD 시험대',argv=['scripts/launch_dvd_test.py','--menu'])
    elif dvd_menu is not None:
        match=re.fullmatch(r'gc-native-v([1-9][0-9]*)-user',dvd_menu)
        if not match or int(match[1])<8:raise ValueError('Only a GC native profile with the DVD hook (v8+) is allowed')
        result['05_DVD_Disc_Channel']=dict(label='시스템 메뉴 · GC v'+match[1]+' 디스크 채널 DVD 연결 시험',profile=dvd_menu,artifact='GC v'+match[1],
            argv=['scripts/launch_dolphin.py','--profile',dvd_menu,'--menu'])
    if settings.get('include_wiispeak_test')is True:
        result['06_WiiSpeak_Test']=dict(label='Wii 스피크 채널 · 부팅 시험대 (마이크 없음, 공식 한국판/실기 후보 비교)',profile='wiispeak-test-v1',
            artifact='시험대에 설치된 빌드',argv=['scripts/launch_wiispeak.py'])
    seen=set()
    for channel in catalog['channels']:
        key=channel['id']
        if not re.fullmatch(r'[a-z][a-z0-9-]*',key)or key in seen:raise ValueError('Invalid or duplicate channel id')
        seen.add(key)
        active=[r for r in channel['installs']if r['role']=='active']
        if len(active)!=1:raise ValueError('Each channel needs exactly one active install')
        row=active[0];argv=shlex.split(row['launch'])
        # An unfamiliar launcher needs an explicit review before becoming a
        # double-click action. Never execute arbitrary catalog shell text.
        if tuple(argv)!=CHANNEL_COMMANDS.get(key):raise ValueError('Unapproved channel launcher; update the shortcut policy')
        if not re.fullmatch(r'[a-z][a-z0-9-]*',row['profile']):raise ValueError('Invalid active profile alias')
        if not re.fullmatch(r'(access-)?build-v[1-9][0-9]*',row['artifact'])and not(key=='dvd-player'and re.fullmatch(r'wad-v[1-9][0-9]*',row['artifact'])):raise ValueError('Invalid active artifact')
        common=dict(label=channel['display_name_ko'],profile=row['profile'],artifact=row['artifact'],
            blocked=channel.get('stage')=='blocked')
        result['Channel_'+key]=dict(common,argv=argv)
        if key not in NO_MENU:
            result['Menu_'+key]=dict(common,label=common['label']+' · Wii 메뉴부터',argv=[*argv,'--menu'])
        if key=='forecast':
            result['Forecast_Refresh']=dict(common,label='날씨 · 공개 예보 갱신 후 실행',argv=[argv[0]])
    result.update({
        'Check_Quick':dict(label='빠른 통합 검사',argv=['scripts/check_all.py','--quick']),
        'Check_Full':dict(label='전체 통합 검사 (SD 전체 해시 포함)',argv=['scripts/check_all.py']),
        'Update_BAT':dict(label='BAT 목록·안내 갱신',argv=[]),
        'Stop_Emulator':dict(label='선택한 프로젝트 Dolphin 종료',argv=['scripts/dolphin_ui.py','stop']),
    })
    return result


def load_plans(root):
    return plans(json.loads((root/'configs/channels.catalog.json').read_text(encoding='utf-8')),
        json.loads((root/'configs/emulator-launchers.json').read_text(encoding='utf-8')))


def bat(key):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',key):raise ValueError('Unsafe shortcut name')
    text=f'''@echo off
rem {MARKER.decode()} -- edit generator/catalog, not this file.
setlocal DisableDelayedExpansion
chcp 65001 >nul
pushd "%~dp0.."
if errorlevel 1 goto bad_root
if not exist ".venv\\Scripts\\python.exe" goto no_python
".venv\\Scripts\\python.exe" -X utf8 "scripts\\run_emulator_shortcut.py" "{key}"
set "KWCE_BAT_RESULT=%ERRORLEVEL%"
popd
if not "%KWCE_BAT_RESULT%"=="0" goto failed
exit /b 0
:no_python
echo Project Python is missing. Restore the project environment first.
popd
set "KWCE_BAT_RESULT=1"
goto failed
:bad_root
echo Cannot open the project folder.
set "KWCE_BAT_RESULT=1"
:failed
echo.
echo Launcher stopped with error %KWCE_BAT_RESULT%. See the message above.
if not defined KWCE_BAT_NO_PAUSE pause
exit /b %KWCE_BAT_RESULT%
'''
    return text.replace('\n','\r\n').encode('ascii')


def expected_files(entries):
    result={key+'.bat':bat(key)for key in entries}
    lines=['<!-- '+MARKER.decode()+' -->','# 최신 에뮬레이터 실행 BAT 모음','',
        '원하는 BAT를 더블클릭한다. 프로젝트 Python과 기존 전용 launcher를 사용하며, 개인 Dolphin이나 실기 SD를 대상으로 하지 않는다.',
        '다른 Dolphin이 실행 중이면 먼저 종료한다. 실패하면 창을 유지해 오류를 볼 수 있다. 폴더를 프로젝트 밖으로 따로 옮기지 않는다.','',
        '| BAT | 용도 | 활성 프로필 | 설치/대상 |','|---|---|---|---|']
    for key,row in sorted(entries.items()):
        note=' **내부 진입 보류 중**'if row.get('blocked')else''
        lines.append(f"| [{key}.bat]({key}.bat) | {row['label']}{note} | {row.get('profile','—')} | {row.get('artifact','—')} |")
    lines+=['','- `Channel_`은 채널 본문부터, `Menu_`는 같은 최신 채널 프로필의 Wii 메뉴부터 실행한다.',
        '- 날씨 기본 실행은 보관 캐시·과거 검수 시각을 쓰는 오프라인 모드다. `Forecast_Refresh.bat`만 호스트에서 공개 예보를 갱신한다.',
        '- 뉴스/투표/Mii/Wii의 방은 기존 로컬 재생·합성 응답을 사용한다. 실제 서비스 접속 성공과 구분한다.',
        '- 닌텐도는 최신 시험본이지만 내부 진입 오류가 남아 있다. 완료된 채널로 보지 않는다.',
        '- 주소 설정·인터넷·커비 TV·디지털 카메라 프린트·음식 배달은 2026-10-28에 추가한 1차 시험본이다. 주소 설정은 숨김 타이틀이라 `Menu_` BAT가 없고, 커비 TV·카메라 프린트는 아직 Wii 메뉴 시작을 지원하지 않는다. 남은 문제는 STATUS를 따른다.',
        '- 설치 앱 시험대도 Dolphin 안에서만 열린다. 실기 SD 복사·실기 설치 BAT는 이 모음에 없다.',
        '- `06_WiiSpeak_Test.bat`는 Wii 스피크 채널 부팅 시험대다. Dolphin에는 마이크(Wii 스피크)가 없으므로 한국어 제목 화면이나 기기 미연결 안내가 나오면 정상이다. 공식 한국판과 실기 후보는 `scripts/install_wiispeak_test.py --build`로 바꾼다.','',
        '## DVD 시험 방법','',
        '`04_DVD_Player_Test.bat`는 시험용 SD에 준비된 ISO를 플레이어에서 자동 재생한다. Dolphin의 열기/디스크 교체 창에서 ISO를 선택할 필요가 없다.',
        '프로젝트 Dolphin은 격리되어 바탕화면·다운로드·드라이브 루트를 탐색하면 접근 거부가 날 수 있다. 준비된 ISO는 launcher가 해시를 확인하고 시험용 SD에서 읽는다.',
        '잘못 연 파일 선택창은 취소하고, `Stop_Emulator.bat`로 DVD 시험대를 종료한 뒤 04번을 실행한다. 영상 종료 후 Wii 메뉴로 돌아온 상태에서 다시 볼 때도 종료 후 04번을 실행한다.',
        '`05_DVD_Disc_Channel.bat`는 같은 통합 DVD 시험대의 Wii 메뉴로 시작한다. 건강 안내에서 A(스페이스)를 누르고 첫 페이지의 디스크 채널을 선택한다. 합성 삽입 상태가 갱신되면 DVD 배너와 시작 버튼이 나타난다(약 30초까지 걸릴 수 있음).',
        '05번의 dvd-test-v3는 별도 DVD 채널 없이 메모리 훅이 SD 실행 모듈을 읽어 제공 ISO를 재생한다. 다른 페이지로 열리면 Q(리모컨 −)로 첫 페이지로 이동한다. 이 합성 삽입·배너는 Dolphin 검수용이며 실기의 DVD 인식 검증과 구분한다.','',
        '## 이후 갱신','',
        '`configs/channels.catalog.json`의 각 채널 `role=active`와 `launch`를 실행 때마다 읽는다. BAT에는 빌드 번호를 고정하지 않는다.',
        '메뉴 기준은 `configs/emulator-launchers.json`에서 관리한다. 새 채널 launcher는 `kwce/emulator_shortcuts.py`의 허용 명령도 검토·등록한다.',
        '`Update_BAT.bat` 또는 `python scripts/sync_emulator_bats.py`로 목록·안내를 갱신한다. `check_all.py`의 quick/full 검사도 자동 갱신한다.',
        '`python scripts/sync_emulator_bats.py --check`는 파일 변경 없이 최신 목록과 일치하는지 확인한다.',
        '생성 파일은 직접 편집하지 않는다. 같은 이름의 사용자 파일이 있으면 덮어쓰지 않고 중단한다.','',
        '[전체 상태](../docs/STATUS.md) · [테스트 방법](../docs/TESTING.md)','']
    result['README.md']='\n'.join(lines).encode('utf-8')
    return result


def synchronize(root,check=False):
    entries=load_plans(root);files=expected_files(entries);folder=root/FOLDER
    if folder.is_symlink()or folder.is_junction():raise ValueError('Indirect BAT folder refused')
    changed=[]
    # Validate every destination before the first write.
    for name,data in files.items():
        path=folder/name
        if path.is_symlink()or path.is_junction():raise ValueError('Indirect BAT file refused')
        previous=path.read_bytes()if path.exists()else None
        if previous is not None and MARKER not in previous[:160]:raise ValueError('Existing user file preserved; choose a different BAT name')
        if previous!=data:changed.append(name)
    if check:return changed
    if changed:folder.mkdir(exist_ok=True)
    for name in changed:
        fd,temporary=tempfile.mkstemp(prefix='.kwce-',suffix='.tmp',dir=folder)
        try:
            with os.fdopen(fd,'wb')as stream:stream.write(files[name])
            os.replace(temporary,folder/name)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
    return changed

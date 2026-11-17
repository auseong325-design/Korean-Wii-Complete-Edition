"""Assemble the unified release-candidate SD bundle (installer app + every channel WAD
+ two disc-channel Priiloader profiles). Output: workspace/hardware/kwce-rc-sd-vN/
(new N each run, ignored, never published). Nothing is sent to or run on a console.

--check is READ-ONLY: it resolves each channel's current hardware WAD, verifies it
against its own build manifest, and prints one line per channel (ok / deferred +
reason). It writes nothing and fabricates no WAD, so a channel that is mid-flight
or whose post-merge hardware candidate has not been regenerated shows as deferred
rather than being silently bundled stale.

Default (no --check) builds the bundle and FAILS LOUDLY if any listed channel has
no current, manifest-matching candidate -- the bundle is the last step, after the
in-flight channels are finished and their hardware candidates refreshed.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import rc_hardware
from kwce.channels import load_library
from kwce.hardware import hardware_wad, fakesigned

from kwce.toolchain import DKP, tool  # Windows: tools/devkitpro-root (unchanged); Linux: tools/linux/...
SRC = ROOT / 'homebrew/kwce-installer-rc/source'
CHAN = ROOT / 'workspace/channels'
MENU = ROOT / 'workspace/console-baseline/menu-original-43K.dol'
# Text files were always written on Windows (newline translation -> CRLF); keep that on every host.
CRLF = '\r\n'


def _rev(folder):
    return int(folder.name.rsplit('-v', 1)[1])


def resolve(channel, lib):
    """Return (kind, source_label, korean_bytes, original_bytes_or_None) or ('deferred', reason, None, None)."""
    cid = channel['id']
    tid = channel['tid'].lower()
    base = CHAN / cid

    # 1) Newest workspace/channels/<id>/hardware-v* candidate that matches its manifest
    #    (or exactly the pinned folder, RC3+, so a recorded bundle stays reproducible).
    hw = sorted((p for p in base.glob('hardware-v*') if p.is_dir()), key=_rev)
    if channel.get('pin') and channel['source'] == 'hardware':
        hw = [p for p in hw if p.name == channel['pin']]
        if not hw:
            return ('deferred', f"pinned {channel['pin']} missing", None, None)
    for folder in reversed(hw):
        mani = folder / 'build-manifest.json'
        wads = list(folder.glob('*.wad'))
        if not mani.exists() or len(wads) != 1:
            continue
        m = json.loads(mani.read_text(encoding='utf-8'))
        data = wads[0].read_bytes()
        if m.get('local_only') or not m.get('hardware_candidate'):
            continue
        if rc_hardware.sha(data) != m.get('wad_sha256'):
            return ('deferred', f'{folder.name}: WAD differs from manifest', None, None)
        t = lib.title.Title()
        t.load_wad(data)
        if t.tmd.title_id.lower() != tid or not t.get_is_fakesigned():
            return ('deferred', f'{folder.name}: title/signature mismatch', None, None)
        original = _original(base, lib, tid)
        return ('hardware', folder.name, data, original)

    # 2) DVD channel: newest wad-v*/dvd-player.wad (KWCE-made; restore = remove).
    if channel['source'] == 'dvd':
        dvd = sorted((p for p in base.glob('wad-v*') if p.is_dir()), key=_rev)
        if channel.get('pin'):
            dvd = [p for p in dvd if p.name == channel['pin']]
        for folder in reversed(dvd):
            w = folder / 'dvd-player.wad'
            wm = folder / 'wad-manifest.json'
            if not w.exists() or not wm.exists():
                continue
            m = json.loads(wm.read_text(encoding='utf-8'))
            data = w.read_bytes()
            if rc_hardware.sha(data) != m.get('wad_sha256'):
                return ('deferred', f'{folder.name}: WAD differs from manifest', None, None)
            korean, _ = fakesigned(data)
            return ('dvd', folder.name, korean, None)
        return ('deferred', 'no wad-v* found', None, None)

    # 3) Classic korean_original: build the region-4 hardware variant from korean + original.
    if channel['source'] == 'korean_original' and channel.get('korean') and channel.get('original'):
        korean_path = base / channel['korean']
        original_path = base / channel['original']
        if not korean_path.exists():
            return ('deferred', f"korean build missing: {channel['korean']}", None, None)
        if not original_path.exists():
            return ('deferred', f"original missing: {channel['original']}", None, None)
        mani = korean_path.parent / 'build-manifest.json'
        if mani.exists():
            m = json.loads(mani.read_text(encoding='utf-8'))
            expected = m['wads'][channel.get('variant', 'personal')]['sha256'] if 'wads' in m else m.get('wad_sha256')
            if expected and rc_hardware.sha(korean_path.read_bytes()) != expected:
                return ('deferred', 'korean build differs from manifest', None, None)
        korean, _ = hardware_wad(korean_path.read_bytes(), original_path.read_bytes())
        restore, _ = fakesigned(original_path.read_bytes())
        return ('korean_original', korean_path.parent.name, korean, restore)

    return ('deferred', 'no hardware candidate found', None, None)


def resolve_edition(channel, edition, lib):
    """RC9+: one edition WAD of a channel (cfg['editions'][id] entry: key, label, pin).
    Returns (folder name, WAD bytes) or ('deferred', reason)."""
    folder = CHAN / channel['id'] / edition['pin']
    mani = folder / 'build-manifest.json'
    wads = list(folder.glob('*.wad'))
    if not mani.exists() or len(wads) != 1:
        return 'deferred', f"{edition['pin']} missing"
    m = json.loads(mani.read_text(encoding='utf-8'))
    data = wads[0].read_bytes()
    if m.get('local_only') or not m.get('hardware_candidate') or m.get('variant') != edition['key']:
        return 'deferred', f"{edition['pin']}: not the hardware build of {edition['key']}"
    if rc_hardware.sha(data) != m.get('wad_sha256'):
        return 'deferred', f"{edition['pin']}: WAD differs from manifest"
    t = lib.title.Title()
    t.load_wad(data)
    if t.tmd.title_id.lower() != channel['tid'].lower() or not t.get_is_fakesigned():
        return 'deferred', f"{edition['pin']}: title/signature mismatch"
    return folder.name, data


def editions_readme(cfg):
    """README section for packages with channel editions (RC9+); older packages have none."""
    names = ', '.join(e['label'] for eds in cfg['editions'].values() for e in eds)
    return (
        '\n음식 배달 채널: 실제 주문판 (WiiLink Domino\'s / Just Eat, 선택 사항)\n'
        '- 기본으로 설치되는 음식 배달 채널은 한국어 표준판입니다. WiiLink 표준판이라 메뉴를 둘러볼 수만 있고\n'
        '  실제 주문은 되지 않습니다.\n'
        '- 해외에 사는 분을 위해 WiiLink의 실제 주문판을 한국 Wii에서 켜지도록 고친 판을 함께 넣었습니다:\n'
        f'  {names}\n'
        '- 고르는 방법: 목록에서 음식 배달 채널을 고르고 A -> 왼쪽/오른쪽으로 판을 고른 뒤 1(GC X)로 설치합니다.\n'
        '  표준판으로 돌아가려면 같은 화면에서 "standard Korean build"를 고르고 1을 누르면 됩니다.\n'
        '- 실제 주문판은 WiiLink를 거쳐 Domino\'s / Just Eat에 진짜 주문을 넣습니다. KWCE는 주문을 넣어 보거나\n'
        '  흉내 내지 않았고, 한국 Wii에서 써 본 적도 없습니다. 아래 조건이 모두 맞아야 동작할 수 있습니다.\n'
        '  1) 고른 나라에 살고 있을 것(서버가 나라 번호로 가게와 결제를 고릅니다. 한국 Wii의 나라 번호 136은\n'
        '     서버가 받지 않으므로, 고른 판이 그 나라 번호를 대신 보냅니다).\n'
        '  2) Open Shop Channel의 WiiLink Account Linker로 이 Wii를 WiiLink 계정에 연결할 것. 이 도구는\n'
        '     본체 고유 키로 WiiLink에 본체를 등록하므로 KWCE 묶음에 넣지 않았습니다. 직접 받아 실행하세요.\n'
        '  3) 주소 설정 채널(Set Personal Data)에서 주소를 그 나라 형식의 영어로(한/영 키), 전화번호를 그 나라\n'
        '     번호로 넣을 것. 우편번호도 그 나라 것을 씁니다.\n'
        '- 실제 주문판의 채널 화면은 영어입니다(WiiLink 원문). Wii 메뉴의 채널 이름, HOME 메뉴, 글꼴만 한국어입니다.\n'
        '- 결제: Domino\'s는 배달 때 현금, Just Eat은 주문 뒤 just-eat.wiilink.ca 웹 페이지에서 결제합니다.\n'
    )


def _original(base, lib, tid):
    """Fakesigned WiiLink original for restore, if one is on disk; else None (restore = remove)."""
    folder = base / 'originals'
    if not folder.is_dir():
        return None
    for w in sorted(folder.glob('*.wad')):
        t = lib.title.Title()
        t.load_wad(w.read_bytes())
        if t.tmd.title_id.lower() == tid:
            restore, _ = fakesigned(w.read_bytes())
            return restore
    return None


def compile_installer(work, src=None, defines=()):
    src = Path(src) if src else SRC
    cc = [str(tool('powerpc-eabi-gcc.exe', DKP / 'devkitPPC/bin')), '-O2', '-Wall', '-Wextra', '-mrvl', '-mcpu=750',
          '-meabi', '-mhard-float', '-DGEKKO', *defines, '-I' + str(DKP / 'libogc/include'), '-L' + str(DKP / 'libogc/lib/wii'),
          *[str(p) for p in sorted(src.glob('*.c'))], '-lwiiuse', '-lbte', '-lfat', '-logc', '-lm',
          '-o', str(work / 'kwce-rc.elf')]
    r = subprocess.run(cc, capture_output=True, text=True)
    out = (r.stdout or '') + (r.stderr or '')
    if r.returncode:
        raise SystemExit('RC installer compile failed:\n' + out)
    if [l for l in out.splitlines() if 'warning:' in l]:
        raise SystemExit('RC installer compiler warnings:\n' + out)
    nm = subprocess.run([str(tool('powerpc-eabi-nm.exe', DKP / 'devkitPPC/bin')), str(work / 'kwce-rc.elf')],
                        capture_output=True, text=True, check=True).stdout
    rc_hardware.forbidden_symbols(nm)  # refuses any System Menu / NAND writer symbol
    subprocess.run([str(tool('elf2dol.exe', DKP / 'tools/bin')), str(work / 'kwce-rc.elf'), str(work / 'boot.dol')],
                   check=True, capture_output=True)
    return (work / 'boot.dol').read_bytes()


def freeze_source(cfg):
    """RC3+: compile from homebrew/kwce-installer-rc/<rcN>/source, a frozen copy of the head
    source made on the first build of that version; a later build of the same version must
    find it byte-identical (otherwise bump the version). RC1/RC2 configs keep the head path."""
    if not cfg.get('priiloader_merge'):
        return SRC
    if cfg['version'] in rc_hardware.FINAL_RELEASES:
        tag = 'v' + cfg['version']           # final release: homebrew/kwce-installer-rc/v1.0
    else:
        tag = cfg['version'].rsplit('-', 1)[-1]
        if not tag.startswith('rc') or not tag[2:].isdigit():
            raise SystemExit('RC version must end in -rcN')
    frozen = ROOT / 'homebrew/kwce-installer-rc' / tag / 'source'
    head = {p.name: p.read_bytes() for p in SRC.iterdir() if p.is_file()}
    if frozen.exists():
        have = {p.name: p.read_bytes() for p in frozen.iterdir() if p.is_file()}
        if have != head:
            raise SystemExit(f'{frozen.relative_to(ROOT)} differs from the head source: bump the RC version first')
    else:
        frozen.mkdir(parents=True)
        for name, data in head.items():
            (frozen / name).write_bytes(data)
    return frozen


def rc3_readme(cfg):
    n = rc_hardware.release_of(cfg['version'])
    return (
        'KWCE 채널 설치 도구 (릴리스 후보 ' + cfg['version'] + ')\n\n'
        + ('디스크 채널 실기 인식 문제를 조사하는 시험 후보입니다. 실기 동작은 확인되지 않았습니다.\nSD에 복사하는 것만으로는 설치되지 않습니다.\n'
           if n >= 24 else '이 묶음은 실기 시험만을 앞둔 상태입니다. SD에 복사하는 것만으로는 설치되지 않습니다.\n') +
        'Homebrew Channel에서 KWCE Channel Installer(apps/kwce-installer-rc)를 실행하세요.\n'
        '- 서명 검사 패치가 있는 d2x cIOS 249가 필요합니다. 시스템 메뉴/IOS WAD는 설치하지 않습니다.\n'
        '- 위/아래로 채널을 고르고 1(GC X)로 설치, 2(GC Y)로 복원합니다. +(START)는 전체 설치/전체 복원입니다.\n'
        '- 전체 설치는 실험 채널(닌텐도, 음식 배달, TV 가이드)을 넣을지 한 번 묻고, 끝에 건너뛴 채널과\n'
        '  실패한 채널을 알려 줍니다. 자세한 기록은 kwce-rc/log.txt에 남습니다.\n'
        '- 본체 모델을 자동으로 구분합니다. RVL-001은 채널 설치와 디스크 채널 모드를 모두 쓸 수 있습니다.\n'
        '  게임큐브 단자가 없는 RVL-101(패밀리 에디션)은 채널 설치/복원만 합니다.\n'
        '  이 묶음은 한국 Wii용입니다. Wii U(vWii)에는 별도 vWii 묶음을 쓰세요.\n'
        '- 복원은 KWCE 이전 상태로 되돌립니다. 원래 없던 채널은 지우고(세이브는 유지), 있던 채널은\n'
        '  WiiLink 원본을 다시 넣습니다. 복원용 원본은 내용을 그대로 두고, 한국 본체가 실행할 수 있도록\n'
        '  지역 표시만 맞췄습니다.\n\n'
        '디스크 채널 모드 (RVL-001만)\n'
        '- 설치 도구에서 -(GC L)을 누른 뒤 1 = 게임큐브만(닌텐도 2장 디스크 배치, DVD 없음),\n'
        '  2 = 게임큐브 + DVD(3장 배치, DVD 플레이어 실행)를 고릅니다.\n'
        '- 도구가 apps/Priiloader/hacks_hash.ini를 kwce-rc/priiloader/backup/에 먼저 백업한 뒤 바꿉니다.\n'
        '  원래 있던 다른 Priiloader hack은 그대로 남습니다.\n'
        '- 바꾼 뒤에는 RESET을 누른 채 전원을 켜서 Priiloader > System Menu Hacks에서 KWCE 항목을 켜고 저장하세요.\n'
        + ('- DVD는 디스크 채널에서 SD의 실행 모듈을 직접 불러옵니다. 별도 DVD 채널은 필요 없습니다.\n'
           '  kwce/dvd 폴더가 있는 SD를 꽂아 두세요. 기존 DVD Player는 채널 메뉴에서 삭제할 수 있습니다.\n'
           if cfg.get('native_dvd') else '- DVD 모드에서 DVD Player 타일만 숨깁니다. 플레이어 채널은 삭제하지 마세요.\n'
           '  내부 채널 자리는 계속 차지하며 디스크 채널에서 DVD를 시작합니다.\n' if n >= 16 else '') +
        '- kwce-rc/priiloader/gc-only.ini와 gc-dvd.ini는 PC 배포 도구가 이 SD의 Priiloader 파일을 바탕으로\n'
        '  만든 완성본입니다. fragment-*.ini는 KWCE 항목만 담은 조각이니 그대로 hacks_hash.ini로 쓰지 마세요.\n\n'
        'WiiLink\n'
        '- 뉴스, 날씨, 닌텐도 채널, Wii의 방, 모두의 투표 등 온라인 기능은 WiiLink 서비스를 씁니다.\n'
        '- 설치 도구는 시작할 때 본체의 WiiConnect24 설정이 WiiLink인지 읽기만 해서 확인합니다.\n'
        '  이미 WiiLink이면 아무 것도 묻지 않습니다. 아니면 WiiLink Mail Patcher를 apps/에 복사할지 한 번 묻습니다\n'
        '  (건너뛰어도 됩니다. 이후에는 묻지 않으며 메인 화면의 A로 다시 열 수 있습니다).\n'
        '- WiiLink Mail Patcher는 WiiLink의 GPLv3 프로그램을 수정 없이 컴파일한 것입니다. kwce-rc/extras/\n'
        '  wiilink-mail-patcher/ 안에 LICENSE, SOURCE.txt, source.zip(해당 커밋의 소스)이 함께 있습니다.\n'
        '  패처는 사용자가 홈브류 채널에서 직접 실행할 때만 WiiLink 서버와 통신합니다.\n\n'
        '상태 보고 (B 키)\n'
        '- 뉴스, 날씨, 닌텐도 채널을 한 번씩 연 뒤 설치 도구에서 B를 누르면 kwce-rc/wc24-NN.txt가 저장됩니다.\n'
        '  WiiConnect24 설정 단계, 메일 도메인, 채널별 다운로드 작업 상태만 담고 ID, 비밀번호, 주소 경로는 담지 않습니다.\n\n'
        '다른 본체에 쓸 때\n'
        + ('- apps/kwce-installer-rc, kwce-rc, kwce/dvd 및 KWCE-RC-*를 SD 루트에 복사하고 설치 도구를 실행하세요.\n'
           if cfg.get('native_dvd') and n >= 20 else
           '- 이 폴더들(apps/kwce-installer-rc, kwce-rc, KWCE-RC-*)을 SD 카드 루트에 그대로 복사하고 설치 도구를 실행하면 됩니다.\n') +
        '- 필요한 것: 홈브류 채널, d2x cIOS 249, (디스크 채널 모드를 쓰려면) Priiloader.\n'
        '- 이 묶음의 채널 파일에는 닌텐도 콘텐츠와 본체에서 가져온 글꼴이 들어 있어 개인 사용 용도입니다. 공개 게시하지 마세요.\n\n'
        '실기 정상 실행·서비스 접속은 아직 확인되지 않았습니다. 기존 앱·세이브·SD 파일은 삭제하지 않았습니다.\n'
    )


def rc30_readme(cfg):
    """Additions for RC30+ (forwarder DVD, card-menu fixes, Account Linker)."""
    text = '\nRC30 변경 사항\n'
    if cfg.get('gc_card_menu') == 2:
        text += ('- 게임큐브 메모리 카드 메뉴: 일본판 세이브는 일본어(CP932), 그 밖의 지역 세이브는 원래 방식으로 설명을\n'
                 '  읽어 미국·유럽 세이브의 é, ü 같은 글자가 깨지지 않습니다. 메뉴에서 카드를 포맷하면 한국 본체의\n'
                 '  게임큐브 게임이 받는 형식(ANSI)으로 만듭니다. 이미 쓰던 카드는 바꾸지 않습니다.\n'
                 '  한국판 글꼴에 한자가 없어 일본 세이브 설명의 한자는 ?로 보입니다.\n')
    if cfg.get('dvd_forwarder'):
        text += ('- DVD: 디스크 채널이 작은 로더만 메모리에 두고, 재생기는 SD의 kwce/dvd/player.dol을 해시 확인 뒤\n'
                 '  불러옵니다. kwce/dvd 폴더 전체(player.dol 포함)를 SD에 두세요. 파일이 없거나 다르면 DVD는 시작하지\n'
                 '  않고 Wii 메뉴로 돌아갑니다.\n')
    if cfg.get('account_linker'):
        text += ('- WiiLink Account Linker 2.2.0(공식 원본, 수정 없음)을 apps/wiilink-account-linker에 넣었습니다.\n'
                 '  WiiLink 로그인 서버가 바뀐 뒤의 연결 ID를 씁니다. 실행과 계정 연결은 사용자가 직접 합니다.\n'
                 '  같은 폴더에 LICENSE(AGPL-3.0), SOURCE.txt, source.zip이 있습니다. KWCE-ACCOUNT-LINKER-README-ko.txt 참고.\n')
    if cfg.get('dvd_forwarder', 0) >= 3:
        text += ('\nRC31 변경 사항\n'
                 '- DVD HOME 메뉴: Wii 본체 HOME 메뉴와 같은 크기·화면 범위로 그립니다. 리모컨 설정에서 위쪽 막대가\n'
                 '  화면 밖으로 완전히 사라지고, 설정을 닫을 때 효과음이 끝까지 울립니다.\n'
                 '- DVD 메뉴·재생 화면의 커서를 Wii 기본 커서로 바꿨습니다.\n'
                 '- kwce/dvd의 boot.ash·player.dol·home.arc가 바뀌었습니다. 설치 도구에서 디스크 모드(-)를 다시\n'
                 '  골라야 새 DVD 항목이 Priiloader에 들어갑니다. 그 전에는 디스크 채널이 DVD를 읽을 수 없는\n'
                 '  디스크로 표시합니다(예전 항목이 새 로더를 해시로 거부).\n')
    return text


# Per-release README lines. Text of an already exported release must not change (--reproduce).
FINAL_CHANGES = {
    '1.0.1': ('- 1.0.1에서 바뀐 것: 뉴스(Wii 표준시가 없을 때 한국 시각을 UTC로 바꿔 최신 뉴스를 받음), 음식 배달(도움말의 버튼 그림·대기 시간\n'
              '  숫자 위치, 배너 글자), Wii의 방·Mii 콘테스트 배너 한글 로고. DVD·디스크 모드 파일은 1.0과 같습니다.\n'),
    '1.0.2': ('- 1.0.2에서 바뀐 것(1.0.1 실기 보고 뒤): 뉴스·Wii의 방·모두의 투표 세 채널만 바뀌었습니다.\n'
              '  · 뉴스: 1.0.1의 수정은 실기에서 효과가 없었습니다. 채널이 쓰는 WiiConnect24 시각 대신 항상 본체 시계\n'
              '    (한국 시각 - 9시간)를 쓰도록 바꿨습니다. 본체 시계가 한국 시각으로 맞아 있어야 합니다.\n'
              '  · Wii의 방 354405: 서버가 Mii 정보 등록에 code 0으로 답하는데 채널은 1·2만 받아들이던 것을 0도 받게 했습니다.\n'
              '  · 모두의 투표 239001: 원인을 가리던 고정 번호 대신 0239NN으로 표시합니다(NN = WiiConnect24 오류 번호).\n'
              '    오류 자체를 고친 것은 아니며, 표시되는 번호를 알려 주면 원인을 좁힐 수 있습니다.\n'
              '  나머지 채널·DVD·디스크 모드 파일은 1.0.1과 같습니다.\n'),
    '1.0.3': ('- 1.0.3에서 바뀐 것(온라인 Dolphin 점검 뒤 문구·표시 수정): 날씨·뉴스·닌텐도·음식 배달·Wii의 방·Mii 콘테스트.\n'
              '  · 날씨: 지역 선택 제목의 마침표가 다음 줄로 떨어지던 것을 한 줄로.\n'
              '  · 뉴스: 갱신 시각이 "0시 54분 전"으로 보이던 것을 "0시간 54분 전"으로(글꼴에 빠진 글자 추가).\n'
              '  · 닌텐도·음식 배달·Wii의 방: Wii 메뉴 용어에 맞춰 "Wii 게시판"을 "Wii 알림판"으로.\n'
              '  · 음식 배달 안내 문장 주어("이 채널은"), Mii 콘테스트 장인 안내의 쪽 나눔.\n'
              '  나머지 채널·DVD·디스크 모드 파일은 1.0.2와 같습니다.\n'),
    '1.0.4': ('- 1.0.4에서 바뀐 것: 1.0.3(날씨·뉴스·닌텐도·음식 배달·Wii의 방·Mii 콘테스트 문구·표시 수정)에 더해\n'
              '  음식 배달 표준판을 관상용으로 바꿨습니다. 가게·메뉴·장바구니는 WiiLink 체험 서버를 그대로 쓰지만,\n'
              '  주문 확정과 가게 요청은 본체 안에서만 완료되어 이름·주소·전화번호가 전송되지 않습니다.\n'
              '  완료 화면과 주문 기록은 정상으로 남습니다. 배달 시간 줄은 영어로 표시됩니다.\n'
              '  실제 주문이 필요한 해외 거주자는 설치 도구에서 Domino\'s/Just Eat 판을 고르세요(실제 전송).\n'
              '  나머지 채널·DVD·디스크 모드 파일은 1.0.3과 같습니다.\n'),
    '1.0.5': ('- 1.0.5에서 바뀐 것(1.0.4 실기 사진 보고 뒤): 뉴스·모두의 투표·Mii 콘테스트·인터넷·음식 배달·닌텐도·Wii의 방.\n'
              '  · 뉴스: Wii 메뉴 배너·아이콘에 헤드라인이 나오지 않던 것(채널이 저장한 언어로 찾도록).\n'
              '  · 모두의 투표 023945: WiiLink 결과 지도 파일의 서명이 맞지 않아 나던 오류창을 띄우지 않게 했습니다.\n'
              '    투표·예상은 그대로 되지만 결과 지도는 서버가 고칠 때까지 받지 못할 수 있습니다.\n'
              '  · 음식 배달·닌텐도: HOME 메뉴 확인창 글자를 다른 채널과 같은 크기로. 음식 배달 HOME 위아래 흰 줄 제거.\n'
              '  · Wii 메뉴 제목: Mii 콘테스트(배너 글자 간격, 아이콘 글자), 닌텐도(배너·아이콘 글자),\n'
              '    인터넷(굵고 큰 제목). Wii의 방 설정의 지역 그림을 한반도로.\n'
              '  나머지 채널·DVD·디스크 모드 파일은 1.0.4와 같습니다.\n'),
    '1.0.6': ('- 1.0.6에서 바뀐 것(채널 전수 검수 뒤): 닌텐도·음식 배달·인터넷·커비 TV·모두의 투표.\n'
              '  · 닌텐도·음식 배달: HOME 메뉴 "설명서"의 조작 방법 화면을 한국어로, "자세한 설명 보기" 확인창에\n'
              '    글자가 나오게("채널을 종료합니다. 계속하시겠습니까?"). 닌텐도 영상의 "A 버튼을 눌러 시작해 주세요." 표시.\n'
              '  · 인터넷: 240004 오류 제목이 낱말 중간에서 줄이 바뀌던 것을 한 줄로.\n'
              '  · 커비 TV: 열쇠 안내 세 쪽의 줄바꿈.\n'
              '  · 모두의 투표: "투표 지역 변경"이 오류 뒤 꺼지던 것을 한국판 "거주 지역" 설정을 여는 것으로.\n'
              '  나머지 채널·DVD·디스크 모드 파일은 1.0.5와 같습니다.\n'),
    '1.0.7': ('- 1.0.7에서 바뀐 것: 모두의 투표만 바뀌었습니다.\n'
              '  · "투표 지역 변경"이 Wii 메뉴로 나가던 원인: 채널의 실행 함수가 한국 본체 지역을 몰라서\n'
              '    거주 지역 앱 실행을 거부했습니다. 이 확인을 통과시키고 한국판 거주 지역 앱을 엽니다.\n'
              '  나머지 채널·DVD·디스크 모드 파일은 1.0.6과 같습니다.\n'),
    '1.0.8': ('- 1.0.8에서 바뀐 것: 모두의 투표만 바뀌었습니다.\n'
              '  · WiiLink 투표 서버에는 한국이 없어 다른 나라로 참여합니다. 기본판은 미국, 설치 도구에서\n'
              '    채널을 고른 뒤 좌우로 "Japan (vote as Japan)"을 고르면 일본으로 참여합니다(질문은 일본어/영어).\n'
              '  · 지역은 두 판 모두 "나라 전체"로 보냅니다. 한국 지역 번호가 그 나라의 엉뚱한 주·현으로\n'
              '    집계되던 것을 막습니다. 본체의 거주 지역 설정은 투표 결과에 쓰이지 않습니다.\n'
              '  · 미국판과 일본판을 바꾸면 채널이 국가가 바뀌었다고 보고 투표 기록을 새로 시작할 수 있습니다.\n'
              '  나머지 채널·DVD·디스크 모드 파일은 1.0.7과 같습니다.\n'),
    '1.0.9': ('- 1.0.9에서 바뀐 것: 닌텐도 채널만 바뀌었습니다.\n'
              '  · 채널을 열 때 나오는 "닌텐도 채널" 글자가 미국판 글자 순서를 그대로 따라 늦게 펴지던 것을,\n'
              '    다섯 글자가 고르게(3프레임 간격) 돌아 들어와 0.85초 안에 반사와 함께 자리 잡게 했습니다.\n'
              '  나머지 채널·DVD·디스크 모드 파일은 1.0.8과 같습니다.\n'),
}
FINAL_UNVERIFIED = {
    '1.0.1': '  1.0.1의 변경(뉴스·음식 배달·로고)은 실기 확인 전입니다.\n',
    '1.0.2': '  1.0.1의 배너·로고는 실기 적용을 보고받았습니다. 1.0.2의 변경(뉴스·Wii의 방·투표)은 실기 확인 전입니다.\n',
    '1.0.3': '  1.0.2·1.0.3의 변경은 실기 확인 전입니다(온라인 Dolphin에서 화면 확인).\n',
    '1.0.4': '  1.0.2~1.0.4의 변경은 실기 확인 전입니다(온라인 Dolphin에서 화면 확인).\n',
    '1.0.5': '  1.0.5의 변경은 실기 확인 전입니다(온라인 Dolphin에서 화면 확인, 투표 지도 서명은 Dolphin이 검사하지 않음).\n',
    '1.0.6': '  1.0.6의 변경은 실기 확인 전입니다. 투표 "투표 지역 변경"은 Dolphin에서 거주 지역 화면 대신 Wii 메뉴로 돌아갔습니다.\n',
    '1.0.7': '  1.0.7의 투표 지역 변경은 실기·Dolphin 화면 확인 전입니다.\n',
    '1.0.8': '  1.0.8의 투표 변경(1.0.7 포함)은 실기·Dolphin 화면 확인 전입니다.\n',
    '1.0.9': '  1.0.9의 닌텐도 오프닝은 Dolphin 화면만 확인했고 실기 확인 전입니다. 1.0.8의 투표 변경도 실기 확인 전입니다.\n',
}


def final_notes(cfg):
    """Release notes appended to the README of a final personal release (1.0)."""
    exp = [c['name'] for c in cfg['channels'] if c.get('experimental')]
    return ('\nKWCE ' + cfg['version'] + ' 릴리스 노트 (개인용, 소유자 본체 전용)\n'
            ''            + ('- 판 번호: ' + cfg['version'] + '은 RC31 다음 판입니다(내부 번호 ' + str(rc_hardware.release_of(cfg['version'])) + '). 채널·DVD·디스크 모드 파일은\n'
               '  RC31과 같아 RC31로 설치한 채널은 Korean, up to date로 보이고, 더 예전 판은 UPDATE: RCx -> ' + cfg['version'] + '로 보입니다.\n'
               if cfg['version'] == '1.0' else
               '- 판 번호: ' + cfg['version'] + ' (내부 번호 ' + str(rc_hardware.release_of(cfg['version'])) + '). 1.0에서 바뀐 채널은 UPDATE: 1.0 -> ' + cfg['version'] + '로 보입니다.\n'
               + FINAL_CHANGES[cfg['version']]) +
            '- 담긴 것: 채널 ' + str(len(cfg['channels'])) + '개(예전 DVD 플레이어 채널은 제거 전용), 디스크 채널 모드(게임큐브 모든 지역 +\n'
            '  선택형 DVD, Priiloader 메모리 hack, NAND 시스템 메뉴 불변), WiiLink Account Linker 2.2.0·Mail Patcher 원본.\n'
            '- 실험 채널: ' + ', '.join(exp) + '. 서버·실제 주문은 확인하지 않았습니다.\n'
            '- 확인: 소유자 본체에서 RC31 실기 정상 작동을 보고받았습니다(2026-11-15, DVD HOME 화면·효과음·Wii 커서 포함).\n'
            + ('' if cfg['version'] == '1.0' else FINAL_UNVERIFIED[cfg['version']]) +
            '  채널별 실기 확인 범위는 개별 보고에 따르며, 모든 화면의 실기 확인을 뜻하지 않습니다.\n'
            '- 알려진 제한(빌드로 고칠 수 없음): 뉴스·TV 가이드 일부는 WiiLink 서버 쪽 오류, 닌텐도 채널 262302,\n'
            '  투표·Mii 제출 오류, 일본 게임큐브 세이브 설명의 한자는 ?로 표시(한국판 글꼴에 한자 없음),\n'
            '  DVD 효과음에는 원본의 리버브가 없음, 음식 배달 표준판 실행 파일 속 일본어 일부.\n'
            '- 이 묶음에는 닌텐도 저작물과 이 본체에서 가져온 글꼴이 들어 있어 공개·재배포하지 마세요.\n')


def rc4_readme(cfg):
    n = rc_hardware.release_of(cfg['version'])
    final = cfg['version'] in rc_hardware.FINAL_RELEASES
    return (
        ('KWCE 채널 설치 도구 (' + cfg['version'] + ', 개인용)\n\n' +
         ('소유자 본체용 개인 릴리스입니다. 내용은 RC31과 같고 판 번호만 1.0입니다. 공개 배포용이 아닙니다.\n' if cfg['version'] == '1.0'
          else '소유자 본체용 개인 릴리스입니다. 공개 배포용이 아닙니다.\n') +
         '실기 확인 범위와 남은 문제는 이 안내문 끝의 1.0 릴리스 노트를 보세요. SD에 복사하는 것만으로는 설치되지 않습니다.\n'
         if final else
         'KWCE 채널 설치 도구 (릴리스 후보 ' + cfg['version'] + ')\n\n'
         '이 묶음은 실기 시험만을 앞둔 상태입니다. SD에 복사하는 것만으로는 설치되지 않습니다.\n') +
        'Homebrew Channel에서 KWCE Channel Installer(apps/kwce-installer-rc)를 실행하세요.\n'
        '서명 검사 패치가 있는 d2x cIOS 249가 필요합니다. 시스템 메뉴/IOS WAD는 설치하지 않습니다.\n\n'
        '목록 화면\n'
        '- 채널마다 지금 본체에 깔린 판을 보여 줍니다.\n'
        '  Korean, up to date = 이 묶음의 한국어판 / UPDATE: RCx -> ' + rc_hardware.release_name(cfg['version']) + ' = 예전 한국어판(업데이트 있음)\n'
        '  original = 원래 채널 / not installed = 없음 / other version = 이 도구가 모르는 판\n'
        '  !REGION = 지역 표시가 달라 이 본체의 Wii 메뉴가 실행하지 않는 판\n'
        '- 판 구분은 본체에 저장된 타이틀 정보(TMD)를 읽어서만 합니다. 본체에 아무것도 쓰지 않습니다.\n'
        '  예전 KWCE 묶음과 원본 채널 목록은 kwce-rc/versions.txt에 들어 있습니다.\n\n'
        '버튼\n'
        '- 위/아래: 채널 고르기\n'
        '- A: 채널 메뉴(자세한 정보 + 설치/업데이트, 복원, 삭제)\n'
        '- 1(GC X): 고른 채널 설치/업데이트, 2(GC Y): 고른 채널 복원\n'
        '- +(START): 전체 메뉴 -> 1 = 전체 설치/업데이트(이미 최신인 채널은 건너뜀), A = 업데이트만,\n'
        '  2 = 전체 복원\n'
        '- -(GC L): 디스크 채널 모드(RVL-001만), B: 도구(WiiLink 설정, WiiConnect24 보고, 채널 상태 보고)\n'
        '- HOME(GC Z): 나가기 -> HOME 한 번 더 = 홈브류 채널, A = Wii 메뉴로 바로 가기\n\n'
        '설치·업데이트\n'
        '- 전체 설치는 실험 채널(닌텐도, 음식 배달, TV 가이드)과 이 도구가 모르는 판이 있는 채널을\n'
        '  넣을지 한 번씩 묻고, 끝에 바꾼 채널, 건너뛴 채널, 실패한 채널을 알려 줍니다.\n'
        '- 설치가 끝나면 본체에 들어간 판이 이 묶음의 한국어판과 같은지 다시 읽어서 확인합니다.\n'
        '- 이미 최신인 채널을 1로 고르면 다시 설치(복구)할지 묻습니다.\n\n'
        '복원·삭제 (세이브 데이터는 지우지 않습니다)\n'
        '- 복원은 KWCE를 처음 쓰기 전 상태로 되돌립니다. 원래 없던 채널은 지우고, 있던 채널은 원본을\n'
        '  다시 넣습니다. 이미 그 상태면 아무것도 하지 않습니다. 복원용 원본은 내용을 그대로 두고 한국\n'
        '  본체가 실행할 수 있도록 지역 표시만 맞췄습니다.\n'
        + ('- 삭제: 채널을 고르고 A -> 위/아래로 Delete channel 선택 -> A -> 대상과 안내 확인 -> A\n'
           '  -> -(GC L)으로 최종 확인합니다. 다른 버튼은 취소입니다. 채널 메뉴의 - 단축키도 됩니다.\n'
           '  저장 데이터는 유지됩니다. 복원 결과는 기존 기록과 SD의 원본 패키지에 따라 달라집니다.\n'
           if n >= 15 else
           '- 삭제는 채널 메뉴(A)에서 -(GC L)을 누르고, 확인(A) 뒤 -(GC L)을 한 번 더 눌러야 실행됩니다.\n'
           '  지운 채널도 나중에 1로 다시 설치하거나 2로 원본을 되돌릴 수 있습니다.\n') +
        '- 설치나 삭제 중에 전원/리셋 버튼을 누르면 지금 하는 단계를 마친 뒤에 꺼지거나 나갑니다.\n\n'
        '디스크 채널 모드 (RVL-001만)\n'
        '- -(GC L)을 누른 뒤 1 = 게임큐브만(닌텐도 2장 디스크 배치, DVD 없음), 2 = 게임큐브 + DVD(3장 배치)를\n'
        '  고릅니다. 도구가 apps/Priiloader/hacks_hash.ini를 kwce-rc/priiloader/backup/에 먼저 백업한 뒤 바꾸고,\n'
        '  원래 있던 다른 Priiloader hack은 그대로 남습니다.\n'
        '- 바꾼 뒤에는 RESET을 누른 채 전원을 켜서 Priiloader > System Menu Hacks에서 KWCE 항목을 켜고 저장하세요.\n'
        + ('- DVD는 디스크 채널에서 SD의 실행 모듈을 직접 불러옵니다. 별도 DVD 채널은 필요 없습니다.\n'
           '  kwce/dvd 폴더가 있는 SD를 꽂아 두세요. 기존 DVD Player는 채널 메뉴에서 삭제할 수 있습니다.\n'
           '  전체 설치는 예전 DVD 바로가기를 만들지 않습니다. Native DVD setup information으로 안내를 봅니다.\n'
           if cfg.get('native_dvd') else '- DVD 모드에서는 DVD Player 타일을 숨깁니다. 플레이어 채널은 삭제하지 마세요.\n'
           '  채널 자리는 내부적으로 계속 차지하며 디스크 채널에서 DVD를 시작합니다.\n' if n >= 16 else '') +
        '- kwce-rc/priiloader/gc-only.ini와 gc-dvd.ini는 PC 배포 도구가 이 SD의 Priiloader 파일을 바탕으로 만든\n'
        '  완성본입니다. fragment-*.ini는 KWCE 항목만 담은 조각이니 그대로 hacks_hash.ini로 쓰지 마세요.\n\n'
        'WiiLink\n'
        '- 뉴스, 날씨, 닌텐도 채널, Wii의 방, 모두의 투표 등 온라인 기능은 WiiLink 서비스를 씁니다.\n'
        '- 설치 도구는 시작할 때 본체의 WiiConnect24 설정이 WiiLink인지 읽기만 해서 확인합니다. 이미 WiiLink이면\n'
        '  아무 것도 묻지 않습니다. 아니면 WiiLink Mail Patcher를 apps/에 복사할지 한 번 묻습니다(건너뛰어도 되며,\n'
        '  이후에는 B > 1로 다시 열 수 있습니다).\n'
        '- WiiLink Mail Patcher는 WiiLink의 GPLv3 프로그램을 수정 없이 컴파일한 것입니다. kwce-rc/extras/\n'
        '  wiilink-mail-patcher/ 안에 LICENSE, SOURCE.txt, source.zip(해당 커밋의 소스)이 함께 있습니다.\n\n'
        '보고 파일 (읽기 전용, 문제를 알려 주실 때 함께 보내 주세요)\n'
        '- B > 2: kwce-rc/wc24-NN.txt. 뉴스, 날씨, 닌텐도 채널을 한 번씩 연 뒤 저장하세요. WiiConnect24 설정 단계,\n'
        '  메일 도메인, 채널별 다운로드 작업 상태만 담고 ID, 비밀번호, 주소 경로는 담지 않습니다.\n'
        '- B > +(START): kwce-rc/status-NN.txt. 채널별로 깔린 판, 지역, 복원 기록을 담습니다. 일련번호나\n'
        '  본체 ID는 담지 않습니다. 모든 동작은 kwce-rc/log.txt에도 남습니다.\n\n'
        '다른 본체에 쓸 때\n'
        + ('- apps/kwce-installer-rc, kwce-rc, kwce/dvd 및 KWCE-RC-*를 SD 루트에 복사하고 설치 도구를 실행하세요.\n'
           if cfg.get('native_dvd') and n >= 21 else
           '- 이 폴더들(apps/kwce-installer-rc, kwce-rc, KWCE-RC-*)을 SD 카드 루트에 그대로 복사하고 설치 도구를 실행하면 됩니다.\n') +
        '- 필요한 것: 홈브류 채널, d2x cIOS 249, (디스크 채널 모드를 쓰려면) Priiloader.\n'
        '- 이 묶음은 한국 Wii용입니다. 다른 지역 본체에서는 화면 위에 경고가 나오고 한국어 채널이 실행되지 않습니다.\n'
        '- 이 묶음의 채널 파일에는 닌텐도 콘텐츠와 본체에서 가져온 글꼴이 들어 있어 개인 사용 용도입니다. 공개 게시하지 마세요.\n\n'
        '실기 정상 실행·서비스 접속은 아직 확인되지 않았습니다. 기존 앱·세이브·SD 파일은 삭제하지 않았습니다.\n'
    )


def public_readme(text, cfg):
    """Public beta edition (design v3): same install content as the personal build, public wording only.
    Every personal-use sentence must be found and replaced; anything missing stops the build."""
    v = cfg['version']
    swaps = [
        (f'KWCE 채널 설치 도구 ({v}, 개인용)\n', f'KWCE 채널 설치 도구 ({v} 공개판, 베타)\n'),
        ('소유자 본체용 개인 릴리스입니다. 공개 배포용이 아닙니다.\n',
         f'KWCE 패처로 만든 공개 베타판입니다. 설치되는 채널·파일은 {v}와 같습니다.\n'),
        ('- 이 묶음의 채널 파일에는 닌텐도 콘텐츠와 본체에서 가져온 글꼴이 들어 있어 개인 사용 용도입니다. 공개 게시하지 마세요.\n',
         '- 채널 파일은 KWCE 패처가 이 PC에서 닌텐도 업데이트 서버의 원본에 패치를 적용해 만든 것입니다.\n'
         '  만든 파일(WAD 등)을 다른 사람에게 배포하지 마세요. 각자 패처로 만들면 됩니다.\n'),
        ('실기 정상 실행·서비스 접속은 아직 확인되지 않았습니다. 기존 앱·세이브·SD 파일은 삭제하지 않았습니다.\n',
         '설치 도구는 기존 앱·세이브·SD 파일을 지우지 않습니다.\n'),
        (', Japan (vote as Japan)\n',
         '\n- 모두의 투표 채널도 같은 방법으로 "Japan (vote as Japan)" 판을 고를 수 있습니다(일본으로 투표, 질문은\n'
         '  일본어/영어). 기본판은 미국으로 투표합니다. WiiLink 투표 서버에 한국이 없기 때문입니다.\n'),
        (f'KWCE {v} 릴리스 노트 (개인용, 소유자 본체 전용)\n', f'KWCE {v} 릴리스 노트 (공개 베타)\n'),
        ('- 확인: 소유자 본체에서 RC31 실기 정상 작동을 보고받았습니다(2026-11-15, DVD HOME 화면·효과음·Wii 커서 포함).\n',
         '- 확인: 개발자의 한국판 Wii(RVL-001) 한 대에서 RC31의 실기 정상 작동을 확인했습니다(2026-11-15, DVD HOME\n'
         '  화면·효과음·Wii 커서 포함). 다른 본체에서는 시험하지 않았습니다(베타).\n'),
        ('- 이 묶음에는 닌텐도 저작물과 이 본체에서 가져온 글꼴이 들어 있어 공개·재배포하지 마세요.\n',
         '- 공개판 배포물에는 닌텐도 파일이 들어 있지 않습니다. 패처가 만든 SD 파일은 각자 사용하고 재배포하지 마세요.\n'
         '- 문제가 생겨도 책임지지 않습니다. 설치 전에 BootMii NAND 백업을 만들어 두세요.\n'),
    ]
    for old, new in swaps:
        if text.count(old) != 1:
            raise SystemExit(f'public edition: README sentence not found exactly once: {old[:40]!r}')
        text = text.replace(old, new)
    for word in ('개인용', '개인 릴리스', '소유자 본체', '이 본체에서 가져온'):
        if word in text:
            raise SystemExit(f'public edition: personal wording left in README: {word}')
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', help='build from this config snapshot instead of configs/rc-package.json')
    ap.add_argument('--check', action='store_true', help='read-only: report candidate state, write nothing')
    ap.add_argument('--reproduce', metavar='PACKAGE',
                    help='rebuild a recorded RC3+ package into a temporary folder and require a byte-identical manifest')
    args = ap.parse_args()

    lib = load_library()
    repro = None
    if args.reproduce:
        repro = ROOT / 'workspace/hardware' / args.reproduce
        rec0 = json.loads((repro / 'package-manifest.json').read_text(encoding='utf-8'))
        if 'config' not in rec0 or 'installer_source' not in rec0:
            raise SystemExit('This package predates recorded build inputs (RC1/RC2); its files stay preserved on disk.')
        cfg = rec0['config']
    elif args.config:
        cfg = json.loads((ROOT / args.config).read_text(encoding='utf-8'))
    else:
        cfg = rc_hardware.config()
    resolved, deferred = [], []
    for ch in cfg['channels']:
        kind, label, korean, original = resolve(ch, lib)
        if kind == 'deferred':
            deferred.append((ch['id'], label))
            print(f"  DEFER  {ch['id']:<14} {label}")
        else:
            resolved.append((ch, kind, label, korean, original))
            print(f"  ok     {ch['id']:<14} {kind}/{label}  korean {len(korean)//1024}KB "
                  + ('original ' + str(len(original) // 1024) + 'KB' if original else 'restore=remove'))

    # RC9+: optional editions (e.g. the WiiLink real-order Food editions), installed instead of korean.wad
    editions = []
    by_id = {ch['id']: ch for ch in cfg['channels']}
    for cid, entries in (cfg.get('editions') or {}).items():
        for ed in entries:
            label, data = resolve_edition(by_id[cid], ed, lib)
            if label == 'deferred':
                deferred.append((f"{cid}/{ed['key']}", data))
                print(f"  DEFER  {cid + '/' + ed['key']:<14} {data}")
            else:
                editions.append((cid, ed, label, data))
                print(f"  ok     {cid + '/' + ed['key']:<14} edition/{label}  {len(data)//1024}KB")

    print(f"\n  resolved {len(resolved)}/{len(cfg['channels'])}  deferred {len(deferred)}"
          + (f"  editions {len(editions)}" if cfg.get('editions') else ''))
    if args.check:
        print('CHECK ONLY: nothing written.')
        return
    if deferred:
        raise SystemExit('Bundle not built: refresh/finish these channels first -> '
                         + ', '.join(cid for cid, _ in deferred))

    # ---- full build (only when every channel resolved) ----
    base = ROOT / 'workspace/hardware'
    base.mkdir(exist_ok=True)
    if repro is not None:
        src_dir = ROOT / rec0['installer_source']
        out = Path(tempfile.mkdtemp(prefix='rc-repro-')) / repro.name
    else:
        src_dir = freeze_source(cfg)
        n = max([int(p.name.rsplit('-v', 1)[1]) for p in base.glob('kwce-rc-sd-v*')
                 if p.name.rsplit('-v', 1)[1].isdigit()], default=0) + 1
        out = base / f'kwce-rc-sd-v{n}'
    source_version = re.search(r'#define VERSION "([^\"]+)"', (src_dir / 'main.c').read_text(encoding='utf-8'))
    if not source_version or source_version.group(1) != cfg['version']:
        raise SystemExit('Installer source version does not match the RC package configuration')
    out.mkdir()
    work = out / '_build'
    work.mkdir()
    try:
        dol = compile_installer(work, src_dir)
    except BaseException:
        shutil.rmtree(out)
        raise
    shutil.rmtree(work)

    app = out / rc_hardware.APP
    app.mkdir(parents=True)
    (app / 'boot.dol').write_bytes(dol)
    long_text = ('Installs every Korean KWCE channel WAD from sd:/kwce-rc and restores the '
                 'original WiiLink channel or the pre-KWCE state. Install-all or per-channel. Detects RVL-001 vs '
                 'RVL-101/vWii; channel titles only, never system titles. Requires d2x cIOS 249.')
    if cfg.get('versions'):
        long_text = ('Installs, updates, restores and deletes the Korean KWCE channels from sd:/kwce-rc. '
                     'Detects which Korean build each channel has and offers only the newer ones; restores the '
                     'pre-KWCE state. Detects RVL-001 vs RVL-101/vWii; channel titles only, never system titles. '
                     'Requires d2x cIOS 249.')
    (app / 'meta.xml').write_text(
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<app version="1">\n'
        '  <name>KWCE Channel Installer</name>\n  <coder>KWCE</coder>\n'
        f'  <version>{cfg["version"]}</version>\n'
        '  <short_description>Korean channel install / restore ('
        + ('personal release' if cfg['version'] in rc_hardware.FINAL_RELEASES else 'release candidate')
        + ')</short_description>\n'
        f'  <long_description>{long_text}</long_description>\n</app>\n',
        encoding='utf-8', newline=CRLF)
    shutil.copy2(ROOT / 'workspace/hardware/kwce-alpha-v7/apps/kwce-installer/icon.png', app / 'icon.png')

    data_dir = out / rc_hardware.DATA
    dvd_hook = None
    if cfg.get('dvd_forwarder'):
        # RC30+: RC29 banner/HOME/font/icon + the frozen forwarder loader/player pair.
        from kwce.rc_disc_v2 import runtime_files as forwarder_files
        dvd_files, dvd_hook = forwarder_files(cfg['native_dvd'], cfg['dvd_forwarder'], lib)
        for name,data in dvd_files.items():
            target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    elif cfg.get('native_dvd'):
        from kwce.dvd_native_hardware import runtime_files
        for name,data in runtime_files(cfg['native_dvd'],lib).items():
            target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    account_linker = None
    if cfg.get('account_linker'):
        # RC30+: the pinned, unmodified official Account Linker package, copied as verified.
        from kwce.account_linker_package import sd_files as account_linker_files
        account_linker, linker_files = account_linker_files(ROOT / 'workspace/hardware' / cfg['account_linker'])
        for src_file, rel in linker_files:
            if rel not in rc_hardware.ACCOUNT_LINKER_FILES:
                raise SystemExit(f'Unexpected Account Linker file {rel}')
            target=out/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(src_file.read_bytes())
    lines = ['# id|title id|name|experimental|gamecube_only (generated; do not edit)']
    channel_records = []
    for ch, kind, label, korean, original in resolved:
        folder = data_dir / ch['id']
        folder.mkdir(parents=True)
        (folder / 'korean.wad').write_bytes(korean)
        orig_rec = None
        if original:
            original, region_rec = rc_hardware.restore_region(original, cfg.get('restore_region'))
            (folder / 'original.wad').write_bytes(original)
            orig_rec = dict(bytes=len(original), sha256=rc_hardware.sha(original))
            if cfg.get('restore_region') is not None:
                orig_rec['region'] = region_rec
        line=f"{ch['id']}|{ch['tid'].lower()}|{ch['name']}|{int(ch['experimental'])}|0"
        if ch.get('remove_only'):line+='|1'
        lines.append(line)
        channel_records.append(dict(id=ch['id'], source=f'{kind}/{label}', experimental=ch['experimental'],
                                    korean=dict(bytes=len(korean), sha256=rc_hardware.sha(korean)), original=orig_rec))
    (data_dir / 'packages.txt').write_text('\n'.join(lines) + '\n', encoding='ascii', newline=CRLF)
    if editions:
        records = {r['id']: r for r in channel_records}
        for cid, ed, label, data in editions:
            (data_dir / cid / f"korean-{ed['key']}.wad").write_bytes(data)
            records[cid].setdefault('editions', []).append(dict(key=ed['key'], label=ed['label'], source=f'edition/{label}',
                                                                bytes=len(data), sha256=rc_hardware.sha(data)))
        (data_dir / 'editions.txt').write_bytes(rc_hardware.edition_list([(cid, ed['key'], ed['label'])
                                                                          for cid, ed, _l, _d in editions]))

    # RC4+: the version list the installer uses to tell older Korean builds and originals apart.
    versions_rec = None
    if cfg.get('versions'):
        sources = (rec0.get('versions') or {}).get('sources') if repro is not None else None
        if sources is None:
            sources = rc_hardware.version_sources(ROOT, cfg['channels'], out.name)
        missing = [s for s in sources if not (ROOT / s).is_file()]
        if missing:
            shutil.rmtree(out.parent if repro is not None else out)
            raise SystemExit(f'version list sources missing: {missing[:3]}')
        raw_versions, versions_rec = rc_hardware.version_list(
            ROOT, cfg['channels'], rc_hardware.release_of(cfg['version']), cfg['version'], sources)
        (data_dir / 'versions.txt').write_bytes(raw_versions)

    # RC3+: optional extras (unmodified third-party tools, GPL license + source included).
    for name, folder in (cfg.get('extras') or {}).items():
        src_extra = ROOT / 'workspace/hardware/extras' / folder
        missing = [n for n in ('boot.dol', 'meta.xml', 'icon.png', 'LICENSE', 'SOURCE.txt', 'source.zip')
                   if not (src_extra / n).is_file()]
        if missing:
            shutil.rmtree(out)
            raise SystemExit(f'extra {name}: {src_extra.relative_to(ROOT)} is missing {missing}')
        dst_extra = data_dir / 'extras' / name
        dst_extra.mkdir(parents=True)
        for item in sorted(src_extra.iterdir()):
            if item.is_file():
                shutil.copy2(item, dst_extra / item.name)

    # Two disc-channel Priiloader profiles (GameCube-capable RVL-001 only).
    menu = MENU.read_bytes()
    pri = data_dir / 'priiloader'
    pri.mkdir()
    if cfg.get('gc_card_menu') == 2:
        if not dvd_hook:
            raise SystemExit('gc_card_menu 2 is reviewed only with the forwarder DVD section')
        gc_only, rec_only = rc_hardware.disc_ini_v2(menu, dvd=False, dvd_hook=dvd_hook)
        gc_dvd, rec_dvd = rc_hardware.disc_ini_v2(menu, dvd=True, dvd_hook=dvd_hook)
    else:
        gc_only, rec_only = rc_hardware.disc_ini(menu, dvd=False,strict_search_order=cfg.get('strict_priiloader_search_order',False),packed_tokens=cfg.get('packed_priiloader_tokens',False))
        hiding = cfg.get('hide_dvd_tile',False)
        hide_source = ROOT / ('kwce/dvd_hide_tile_v2.py' if hiding == 2 else 'kwce/dvd_hide_tile_v1.py')
        if hiding and hashlib.sha256(hide_source.read_bytes()).hexdigest() != cfg.get('dvd_hide_tile_source_sha256'):
            raise ValueError('Reviewed DVD hiding source differs')
        gc_dvd, rec_dvd = rc_hardware.disc_ini(menu, dvd=True, hide_dvd_tile=cfg.get('hide_dvd_tile',False),native_dvd=cfg.get('native_dvd'),strict_search_order=cfg.get('strict_priiloader_search_order',False),packed_tokens=cfg.get('packed_priiloader_tokens',False))
    if cfg.get('priiloader_merge'):
        # RC3+: KWCE-only fragments; scripts/deploy_to_sd.py merges each into the card's
        # own hacks_hash.ini and writes complete gc-only.ini / gc-dvd.ini next to them.
        (pri / rc_hardware.FRAGMENT.format('gc-only')).write_bytes(gc_only)
        (pri / rc_hardware.FRAGMENT.format('gc-dvd')).write_bytes(gc_dvd)
    else:
        (pri / 'gc-only.ini').write_bytes(gc_only)
        (pri / 'gc-dvd.ini').write_bytes(gc_dvd)

    readme = (
        'KWCE 채널 설치 도구 (릴리스 후보 ' + cfg['version'] + ')\n\n'
        '이 묶음은 실기 시험만을 앞둔 상태입니다. SD에 복사하는 것만으로는 설치되지 않습니다.\n'
        'Homebrew Channel에서 KWCE Channel Installer(apps/kwce-installer-rc)를 실행하세요.\n'
        '- 전체 설치/복원 또는 채널별 선택이 가능합니다.\n'
        '- 본체 모델(RVL-001 / RVL-101 / vWii)을 자동으로 구분합니다. 게임큐브 포트가 없는 RVL-101·vWii에서는\n'
        '  채널 설치/복원만 하고, 디스크 채널(게임큐브) 복원은 대상이 아닙니다.\n'
        '- 서명 검사 패치가 있는 기존 d2x cIOS 249가 필요합니다. 시스템 메뉴/IOS WAD는 설치하지 않습니다.\n\n'
        '디스크 채널(게임큐브) 복원은 Priiloader 메모리 hack으로만 들어갑니다(NAND 시스템 메뉴 불변).\n'
        'kwce-rc/priiloader 폴더에 두 가지가 있습니다. 둘 중 하나만 Priiloader hacks_hash.ini로 쓰세요:\n'
        '- gc-only.ini : 게임큐브 기능만 복원. 디스크 모델 배치는 닌텐도 2장 디스크 지원 시절 배치 그대로.\n'
        '- gc-dvd.ini  : 게임큐브 + DVD(3장 배치, DVD 실행 훅 포함).\n\n'
        '실기 정상 실행·서비스 접속은 아직 확인되지 않았습니다. 기존 앱·세이브·SD 파일은 삭제하지 않았습니다.\n'
    ).encode('utf-8')
    if cfg.get('priiloader_merge'):
        readme = rc3_readme(cfg).encode('utf-8')
    if cfg.get('versions'):
        readme = rc4_readme(cfg).encode('utf-8')
    if cfg.get('editions'):
        readme += editions_readme(cfg).encode('utf-8')
    if cfg.get('gc_card_menu') or cfg.get('dvd_forwarder') or cfg.get('account_linker'):
        readme += rc30_readme(cfg).encode('utf-8')
    if cfg['version'] in rc_hardware.FINAL_RELEASES:
        readme += final_notes(cfg).encode('utf-8')
    if cfg.get('public_edition'):
        readme = public_readme(readme.decode('utf-8'), cfg).encode('utf-8')
    (out / rc_hardware.README).write_text(readme.decode('utf-8'), encoding='utf-8', newline=CRLF)

    record = dict(kind='kwce-rc-unified-v1', package=out.name, version=cfg['version'],
                  menu_writer_linked=False, nand_writes=False, system_menu_version=518,
                  dol_sha256=rc_hardware.sha(dol), disc_profiles=[rec_only, rec_dvd],
                  channels=channel_records, hardware_tested=False, publish=False,
                  note=('Public beta edition: same install content as the personal build; channel files are '
                        'rebuilt by the KWCE PC patcher from Nintendo update-server bases. Do not redistribute '
                        'the generated files.') if cfg.get('public_edition') else
                       'Personal use on the owner console only; contains console-derived fonts.',
                  sd_files=[])
    if cfg.get('priiloader_merge'):
        record.update(priiloader_merge=True, config=cfg,
                      installer_source=src_dir.relative_to(ROOT).as_posix())
    if versions_rec is not None:
        record['versions'] = versions_rec
    if dvd_hook:
        record['dvd_forwarder'] = dict(version=cfg['dvd_forwarder'], hook_revision=dvd_hook,
                                       physical_dvd_verified=False)
    if account_linker is not None:
        record['account_linker'] = dict(package=cfg['account_linker'], version=account_linker['version'],
                                        source_commit=account_linker['source_commit'], modified_upstream_binary=False)
    sd = []
    # Windows path order (case-insensitive parts), the order every earlier RC manifest was written in.
    for p in sorted(out.rglob('*'), key=lambda q: PureWindowsPath(q.relative_to(out).as_posix())):
        if p.is_file() and p.name not in ('package-manifest.json', 'package-manifest.sha256'):
            sd.append(dict(path=p.relative_to(out).as_posix(), bytes=p.stat().st_size, sha256=rc_hardware.sha(p.read_bytes())))
    record['sd_files'] = sd
    raw = (json.dumps(record, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    (out / 'package-manifest.json').write_bytes(raw)
    (out / 'package-manifest.sha256').write_text(rc_hardware.sha(raw) + '\n', encoding='ascii', newline=CRLF)
    rc_hardware.sd_files(out)
    if repro is not None:
        same = (repro / 'package-manifest.json').read_bytes() == raw
        shutil.rmtree(out.parent)
        if not same:
            raise SystemExit(f'REPRODUCE FAILED: {repro.name} manifest (and so at least one SD file) differs')
        print(f"PASS: {repro.name} reproduced byte-identically ({len(record['sd_files'])} SD files, "
              f"dol {record['dol_sha256'][:16]})")
        return
    print(f"PASS: {out.relative_to(ROOT)}  {len(resolved)} channels  dol {record['dol_sha256'][:16]}  "
          f"disc profiles gc-only+gc-dvd  no menu writer")


if __name__ == '__main__':
    main()

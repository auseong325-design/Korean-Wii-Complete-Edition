"""Build a new numbered, read-only HBC DVD probe with pinned SDK archives."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.toolchain import DKP, tool
from kwce.dvd_probe import sd_files


def prepare_sdk():
    # These two 'any' packages contain PPC headers/archives, no host programs.
    import zstandard
    lock = json.loads((ROOT/'configs/dvd-player-toolchain.lock.json').read_text())
    target = ROOT/'tools/linux/dvd-probe-sdk-r2490'
    for entry in lock['packages']:
        if entry['name'] not in ('libogc2-git', 'libogc2-libfat-git'):
            continue
        archive = ROOT/'tools/packages'/entry['url'].rsplit('/', 1)[-1]
        if hashlib.sha256(archive.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Pinned DVD probe SDK archive mismatch')
        with archive.open('rb') as f, zstandard.ZstdDecompressor().stream_reader(f) as raw:
            with tarfile.open(fileobj=raw, mode='r|*') as tar:
                for member in tar:
                    if member.name.startswith('opt/devkitpro/libogc2/wii/'):
                        tar.extract(member, target, filter='data')
    return target/'opt/devkitpro/libogc2/wii'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--revision',type=int,choices=(1,2),default=2)
    revision = ap.parse_args().revision
    sdk = prepare_sdk() if sys.platform == 'linux' else DKP/'libogc2/wii'
    base = ROOT/'workspace/hardware'
    n = 1
    while (base/f'kwce-dvd-probe-sd-v{n}').exists(): n += 1
    out = base/f'kwce-dvd-probe-sd-v{n}'
    src = out/'source'; src.mkdir(parents=True)
    source = ROOT/('homebrew/kwce-dvd-probe/source/main.c' if revision==1 else
                   'homebrew/kwce-dvd-probe/r2/source/main.c')
    shutil.copy2(source, src/'main.c')
    elf = src/'probe.elf'; dol = src/'boot.dol'
    cmd = [str(tool('powerpc-eabi-gcc.exe')), '-O2', '-Wall', '-Wextra', '-Werror',
           '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
           '-mrvl', '-mcpu=750', '-meabi', '-mhard-float', '-DGEKKO',
           '-I'+str(sdk/'include'), '-L'+str(sdk/'lib'), str(src/'main.c'),
           '-ldi', '-lfat', '-lwiiuse', '-lbte', '-logc', '-lm', '-o', str(elf)]
    run = subprocess.run(cmd, capture_output=True, text=True)
    (src/'compile.log').write_text(run.stdout+run.stderr)
    if run.returncode: raise ValueError('DVD probe build failed; inspect private compile log')
    nm = subprocess.run([str(tool('powerpc-eabi-nm.exe')), str(elf)], capture_output=True,
                        text=True, check=True).stdout
    forbidden = ('ISFS_Write', 'ISFS_Delete', 'ISFS_CreateFile', 'ES_AddTitleStart',
                 'ES_AddContentStart', 'ES_DeleteTitle', 'CONF_Set', 'IOS_ReloadIOS',
                 'net_init', 'net_init_async', 'net_socket')
    if any(line.rstrip().endswith(' '+name) for line in nm.splitlines() for name in forbidden):
        raise ValueError('Out-of-scope system/network writer linked')
    subprocess.run([str(tool('elf2dol.exe', DKP/'tools/bin')), str(elf), str(dol)],
                   capture_output=True, check=True)
    app = out/'apps/kwce-dvd-probe'; app.mkdir(parents=True)
    shutil.copy2(dol, app/'boot.dol')
    (app/'meta.xml').write_text('''<?xml version="1.0" encoding="UTF-8"?>
<app version="1"><name>KWCE DVD Read Probe</name><coder>KWCE</coder><version>1.0</version>
<short_description>Read-only physical DVD diagnosis</short_description>
<long_description>Insert the same DVD and press A. Saves numeric call boundaries and metadata checks only to a new SD report. No NAND writes, IOS reload, network, keys or disc contents logged.</long_description>
<ahb_access/><no_ios_reload/></app>
''')
    if revision == 2:
        p = app/'meta.xml'
        p.write_text(p.read_text().replace('<version>1.0</version>','<version>2.0</version>'))
    (out/'KWCE-DVD-PROBE-ko.txt').write_text('''KWCE DVD 읽기 진단 v1

1. 실패했던 같은 DVD를 넣고 홈브류 채널에서 KWCE DVD Read Probe를 실행합니다.
2. A를 한 번 누르고 끝날 때까지 기다립니다. HOME(또는 GC START)으로 복귀합니다.
3. sd:/kwce-rc/dvd-probe-번호.txt를 새로 저장합니다. 기존 기록은 덮어쓰지 않습니다.
4. 같은 DVD로 완전 전원 종료 뒤 한 번, 메뉴 재부팅 뒤 한 번씩 비교합니다.

숫자 기록: 호출 순번/단계/결과2개/소요ms. init·mount·read·error 직전/직후를 저장합니다.
read-begin의 첫 숫자 0/1/2는 고정 시험 위치(시작/ISO 설명자/UDF 주 앵커), 둘째는 1/26 섹터입니다.
read-end 첫 숫자 0만 성공입니다. metadata 비트 1=ISO 서명,2=BEA,4=NSR,8=UDF 앵커 태그·체크섬·위치 일치입니다.
metadata0 자체는 고장을 뜻하지 않습니다. complete도 재생/전체 UDF/IFO 정상 판정은 아닙니다.

AHB 권한이 없으면 ahb0에서 끝납니다. mount 대기는 최대15초이나 SDK의 물리 읽기 자체에는 중단 타이머가 없습니다.
30초 넘게 화면이 그대로면 마지막 단계와 수동 종료 여부를 알려 주십시오. 계속 읽기를 반복하지 않습니다.
SD 쓰기 실패 시 후속 드라이브 명령을 중단합니다. 디스크 내용·제목·키·본체 식별자는 저장하지 않습니다.
진단은 현재 IOS/AHB 상태를 사용합니다. 디스크 채널/WiiMC와 실행 환경이 달라 결과 비교에는 한계가 있습니다.
기존 재생기·Priiloader·GC 카드 패치는 변경하지 않습니다. 네트워크 전송은 이 버전에 없습니다.
''', encoding='utf-8')
    if revision == 2:
        p = out/'KWCE-DVD-PROBE-ko.txt'
        text = '''KWCE DVD 읽기 진단 v2

native58 사전 준비 지연 후보에서도 본체 설정 정지가 재현됐습니다. 현재 DVD 핵은 OFF로 유지합니다.
이 앱은 메뉴 핵을 수정하지 않으며, 기본 ON/OFF 상태를 자동 변경하지 않습니다.
홈브류 채널에서 KWCE DVD Read Probe 2.0을 열어 A를 한 번 누릅니다.
새 보고서는 sd:/kwce-rc/dvd-probe-번호.txt에 저장하며 이전 보고서를 덮어쓰지 않습니다.
첫 물리 읽기 실패에서 후속 드라이브 명령을 중단하며 IOS 오류 조회는 호출하지 않습니다.
SD 기록 실패는 화면에 phase=1(기록)/2(flush)/3(fsync), errno와 마지막 읽기 결과를 표시합니다.
직전 숫자 이벤트와 수동 명령 없는 DI 레지스터 값은 RAM에 보관해 화면에 표시합니다.
이 화면은 추가 SD 쓰기에 의존하지 않습니다. SD 파일이 짧아도 화면의 STOP SUMMARY를 기록해 주세요.
SD log failed는 진단기의 중단 안내입니다. HOME/START로 복귀를 시도하고, 반응이 없으면 그 사실을 남깁니다.
v1의 error-begin 마지막 기록만으로 GetError 정지를 확정하지 않습니다. 그 로그 저장이 실패하면 GetError는 호출되지 않습니다.

정상일 때만 고정3위치의1/26섹터 각6읽기를 수행합니다. 성공은 반환0이며 양수/음수는 모두 실패입니다.
complete는 시험 종료이고 전체IFO/영상/장시간 판독 정상을 뜻하지 않습니다. 내용·제목·키·본체 식별자를 기록하지 않습니다.
IOS 재로드/NAND 쓰기/네트워크는 없습니다. SDK 호출 자체의 정지에는 강제 중단 타이머가 없습니다.
이번 비교는 드라이브/SD 오류를 구분하기 위한 것입니다. 새 메뉴 후보를 켜서 정지를 반복하지 않습니다.
'''
        p.write_text(text,encoding='utf-8')
    paths = [app/'boot.dol', app/'meta.xml', out/'KWCE-DVD-PROBE-ko.txt']
    rows = [dict(path=p.relative_to(out).as_posix(), bytes=p.stat().st_size,
                 sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
    meta = dict(kind='dvd-read-probe-v1', nand_write=False, network=False,
                content_logging=False, ios_reload=False, real_console_verified=False,
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                sdk='libogc2-r2490.cb0df37/libfat-r272.c756e1e', sd_files=rows)
    if revision == 2: meta['probe_revision'] = 2
    raw = (json.dumps(meta, ensure_ascii=False, indent=2)+'\n').encode()
    (out/'package-manifest.json').write_bytes(raw)
    (out/'package-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
    sd_files(out)
    print(f'PASS {out.name}: pinned PPC build, no NAND/network writer; hardware unverified')


if __name__ == '__main__': main()

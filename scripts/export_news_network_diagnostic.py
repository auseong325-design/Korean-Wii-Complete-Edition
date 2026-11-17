"""Build a narrowly scoped, read-only News connectivity/cache diagnostic."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.news_network_diagnostic import sd_files

DKP = ROOT / 'tools/devkitpro-root/opt/devkitpro'
FORBIDDEN = ('ISFS_Write', 'ISFS_Delete', 'ISFS_CreateFile', 'ES_AddTitleStart',
             'ES_AddContentStart', 'ES_DeleteTitle', 'CONF_Set', 'IOS_ReloadIOS')


def main():
    base = ROOT / 'workspace/hardware'
    number = 1
    while (base / f'kwce-news-network-sd-v{number}').exists():
        number += 1
    out = base / f'kwce-news-network-sd-v{number}'
    source = out / 'source'
    source.mkdir(parents=True)
    original = ROOT / 'homebrew/kwce-news-network/source'
    for name in ('main.c', 'cache.c', 'cache.h'):
        shutil.copy2(original / name, source / name)
    elf = source / 'probe.elf'
    dol = source / 'boot.dol'
    command = [str(DKP / 'devkitPPC/bin/powerpc-eabi-gcc.exe'), '-O2', '-Wall', '-Wextra',
               '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections', '-mrvl',
               '-mcpu=750', '-meabi', '-mhard-float', '-DGEKKO',
               '-I' + str(DKP / 'libogc/include'), '-L' + str(DKP / 'libogc/lib/wii'),
               str(source / 'main.c'), str(source / 'cache.c'),
               '-lwiiuse', '-lbte', '-lfat', '-logc', '-lm', '-o', str(elf)]
    build = subprocess.run(command, capture_output=True, text=True)
    (source / 'compile.log').write_text(build.stdout + build.stderr, encoding='utf-8')
    if build.returncode or 'warning:' in build.stderr:
        raise ValueError('Diagnostic compiler failed or warned')
    nm = subprocess.run([str(DKP / 'devkitPPC/bin/powerpc-eabi-nm.exe'), str(elf)],
                        capture_output=True, text=True, check=True).stdout
    if any(line.rstrip().endswith(' ' + name) for line in nm.splitlines() for name in FORBIDDEN):
        raise ValueError('Forbidden Wii system writer symbol linked')
    subprocess.run([str(DKP / 'tools/bin/elf2dol.exe'), str(elf), str(dol)],
                   capture_output=True, check=True)
    subprocess.run([sys.executable, str(ROOT / 'scripts/test_news_network_diagnostic.py'),
                    '--elf', str(elf), '--dol', str(dol)], check=True)
    app = out / 'apps/kwce-news-network'
    app.mkdir(parents=True)
    shutil.copy2(dol, app / 'boot.dol')
    (app / 'meta.xml').write_text(
        '<?xml version="1.0" encoding="UTF-8"?><app version="1"><name>KWCE News Diagnostic</name>'
        '<coder>KWCE</coder><version>1.0</version><short_description>Read-only News cache and network check</short_description>'
        '<long_description>Reads News cache metadata and tests public News and Forecast HTTP headers. '
        'No account, console ID or article text is recorded.</long_description></app>\n', encoding='utf-8')
    readme = out / 'KWCE-NEWS-NETWORK-README-ko.txt'
    readme.write_text(
        'KWCE 뉴스 읽기 전용 진단\n\n'
        '뉴스 오류를 다시 확인한 뒤 홈브류 채널에서 KWCE News Diagnostic을 실행하세요. '
        '자동으로 뉴스 캐시의 항목 수·기한/국가·언어 헤더를 요약하고 뉴스/날씨 서버에 '
        '익명 HEAD 요청을 보냅니다. 결과는 SD:/kwce-rc/news-net-번호.txt에 새로 저장되고 '
        '잠시 뒤 홈브류 채널로 돌아갑니다. 기존 보고서는 덮어쓰지 않습니다.\n\n'
        '기사 본문·사진·본체 식별자·인증서·주소·IP·MAC·설정 값 원문은 저장하지 않습니다. 숫자 구조만 별도 보고서에 저장합니다. '
        '캐시 CRC와 일부 헤더 구조를 확인하며 서명과 채널 전체 동작은 검증하지 않습니다. 독립 연결 점검은 '
        '뉴스 채널 자체의 WiiConnect24 다운로드 성공을 보장하지 않습니다. '
        '인터넷 설정, 본체 저장 데이터와 채널 설치는 변경하지 않습니다.\n', encoding='utf-8')
    payload = [app / 'boot.dol', app / 'meta.xml', readme]
    rows = []
    for path in payload:
        data = path.read_bytes()
        rows.append({'path': path.relative_to(out).as_posix(), 'bytes': len(data),
                     'sha256': hashlib.sha256(data).hexdigest()})
    record = {'kind': 'news-network-diagnostic-v1', 'nand_write': False,
              'console_identifiers': False, 'wad_included': False,
              'real_console_verified': False, 'sd_files': rows}
    manifest = out / 'package-manifest.json'
    manifest.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / 'package-manifest.sha256').write_text(hashlib.sha256(manifest.read_bytes()).hexdigest() + '\n', encoding='ascii')
    sd_files(out)
    print(f'PASS: {out.name}; read-only cache metadata and anonymous HEAD; real console untested')


if __name__ == '__main__':
    main()

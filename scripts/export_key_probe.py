"""Build a new numbered, read-only HBC key probe (public patch design v2, stage 2).

  .venv-linux/bin/python scripts/export_key_probe.py
Output: workspace/hardware/kwce-key-probe-sd-vN (never overwritten).
"""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/'scripts'))
from kwce.toolchain import DKP, tool  # noqa: E402
from kwce.key_probe import sd_files  # noqa: E402
from export_dvd_probe import prepare_sdk  # noqa: E402

SOURCE = ROOT/'homebrew/kwce-key-probe/source/main.c'
FORBIDDEN = ('ISFS_Write', 'ISFS_Delete', 'ISFS_CreateFile', 'ISFS_CreateDir', 'ISFS_Rename', 'ES_AddTitleStart',
             'ES_AddTicket', 'ES_AddContentStart', 'ES_DeleteTitle', 'ES_DeleteTicket', 'CONF_Set', 'IOS_ReloadIOS',
             'net_init', 'net_init_async', 'net_socket', 'ES_Encrypt')
README = '''KWCE 키 시험 v4 (읽기 전용)

공개판 설계 2단계 추가 시험입니다(한국 키 채널을 위한 NAND 읽기 경로).
1. 홈브류 채널에서 KWCE Key Probe를 실행합니다. 자동으로 진행되고 1분 안팎 걸립니다.
2. 끝나면 HOME(또는 GC START)으로 나갑니다. 결과는 sd:/kwce-key-probe/report-번호.txt에 새로 저장됩니다.

시험 내용(모두 읽기만 함):
- N1: 이미 설치된 Wii 스피크(한국 키)·날씨·모두의 투표 채널의 콘텐츠를 IOS(ES)를 통해 읽어 SHA-1이 TMD와 같은지.
- N2: 같은 채널의 NAND 파일을 읽기 모드로 열 수 있는지(반환값만).
- H: 본체의 하드웨어 AES(/dev/aes)가 쓸 수 있는지와 속도.
키 값·키 해시·본체 식별자는 화면·파일 어디에도 쓰지 않습니다.
NAND 쓰기, 채널 설치, IOS 재로드, 네트워크는 없습니다.
'''


def main():
    sdk = prepare_sdk() if sys.platform == 'linux' else DKP/'libogc2/wii'
    base = ROOT/'workspace/hardware'
    n = 1
    while (base/f'kwce-key-probe-sd-v{n}').exists():
        n += 1
    out = base/f'kwce-key-probe-sd-v{n}'
    src = out/'source'; src.mkdir(parents=True)
    shutil.copy2(SOURCE, src/'main.c')
    elf = src/'probe.elf'; dol = src/'boot.dol'
    cmd = [str(tool('powerpc-eabi-gcc.exe')), '-O2', '-Wall', '-Wextra', '-Werror',
           '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
           '-mrvl', '-mcpu=750', '-meabi', '-mhard-float', '-DGEKKO',
           '-I'+str(sdk/'include'), '-L'+str(sdk/'lib'), str(src/'main.c'),
           '-lfat', '-lwiiuse', '-lbte', '-logc', '-lm', '-o', str(elf)]
    run = subprocess.run(cmd, capture_output=True, text=True)
    (src/'compile.log').write_text(run.stdout+run.stderr)
    if run.returncode:
        raise ValueError('Key probe build failed; inspect ' + str((src/'compile.log').relative_to(ROOT)))
    nm = subprocess.run([str(tool('powerpc-eabi-nm.exe')), str(elf)], capture_output=True, text=True, check=True).stdout
    bad = [name for line in nm.splitlines() for name in FORBIDDEN if line.rstrip().endswith(' '+name)]
    if bad:
        raise ValueError('Out-of-scope writer linked: ' + ', '.join(sorted(set(bad))))
    subprocess.run([str(tool('elf2dol.exe', DKP/'tools/bin')), str(elf), str(dol)], capture_output=True, check=True)
    app = out/'apps/kwce-key-probe'; app.mkdir(parents=True)
    shutil.copy2(dol, app/'boot.dol')
    (app/'meta.xml').write_text('''<?xml version="1.0" encoding="UTF-8"?>
<app version="1"><name>KWCE Key Probe</name><coder>KWCE</coder><version>4</version>
<short_description>Read-only WAD decryption check</short_description>
<long_description>Checks reading installed titles through ES (decrypted by IOS), ISFS read-open codes and /dev/aes speed. Writes only a new report on SD. No NAND writes, IOS reload, network, keys or console identifiers logged.</long_description>
<ahb_access/><no_ios_reload/></app>
''')
    (out/'KWCE-KEY-PROBE-ko.txt').write_text(README, encoding='utf-8')
    paths = [app/'boot.dol', app/'meta.xml', out/'KWCE-KEY-PROBE-ko.txt']
    rows = [dict(path=p.relative_to(out).as_posix(), bytes=p.stat().st_size,
                 sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
    meta = dict(kind='key-probe-v1', nand_write=False, network=False, key_output=False, ios_reload=False,
                real_console_verified=False, source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                sdk='libogc2-r2490.cb0df37/libfat-r272.c756e1e', sd_files=rows)
    raw = (json.dumps(meta, ensure_ascii=False, indent=2)+'\n').encode()
    (out/'package-manifest.json').write_bytes(raw)
    (out/'package-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
    sd_files(out)
    print(f'PASS {out.name}: pinned PPC build, no NAND/network writer; hardware unverified')


if __name__ == '__main__':
    main()

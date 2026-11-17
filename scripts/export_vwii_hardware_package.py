"""Build/check an isolated candidate for the linked Korean vWii setup."""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from audit_sd import ROOT, sha256
sys.path.insert(0, str(ROOT))
from kwce.vwii_hardware import (APP, DATA, README, KIND, TITLES, convert_wad,
                                 installer_source, readonly_config_source, sd_files, validate_rows)

CONFIG = ROOT / 'configs/hardware-vwii-ko-v1.json'
DKP = ROOT / 'tools/devkitpro-root/opt/devkitpro'
SOURCE = ROOT / 'homebrew/kwce-installer/source/main.c'
PIPELINE = ['kwce/vwii_hardware.py', 'kwce/channel_hardware.py', 'kwce/dvd_hardware.py',
            'kwce/hardware.py', 'scripts/export_vwii_hardware_package.py',
            'homebrew/kwce-installer/source/kwce.h', 'configs/devkit.lock.json',
            'configs/channel-tools.lock.json', 'docs/hardware/VWII-KO-README-ko.txt']


def config():
    cfg = json.loads(CONFIG.read_text(encoding='utf-8'))
    validate_rows(cfg['channels'])
    if sha256(SOURCE) != cfg['installer_source_sha256']:
        raise ValueError('Reviewed base installer source differs')
    return cfg


def inputs(row):
    folder = ROOT / 'workspace/channels' / row['id']
    korean, original = folder / row['korean'], folder / row['original']
    if sha256(korean) != row['source_sha256'] or sha256(original) != row['original_sha256']:
        raise ValueError('Reviewed vWii input digest differs')
    return korean.read_bytes(), original.read_bytes()


def compile_installer(staged, output):
    elf = staged / 'installer.elf'
    cmd = [str(DKP/'devkitPPC/bin/powerpc-eabi-gcc.exe'), '-O2', '-Wall', '-Wextra',
           '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
           '-Wl,--wrap=CONF_SaveChanges',
           '-mrvl', '-mcpu=750', '-meabi', '-mhard-float', '-DGEKKO',
           '-I'+str(DKP/'libogc/include'), '-L'+str(DKP/'libogc/lib/wii'),
           str(staged/'main.c'), str(staged/'config_readonly.c'),
           '-lwiiuse', '-lbte', '-lfat', '-logc', '-lm', '-o', str(elf)]
    done = subprocess.run(cmd, capture_output=True, text=True)
    (staged/'compile.log').write_text(done.stdout+done.stderr, encoding='utf-8')
    if done.returncode or 'warning:' in done.stderr:
        raise ValueError('vWii installer compile error/warning; local log retained')
    symbols = subprocess.run([str(DKP/'devkitPPC/bin/powerpc-eabi-nm.exe'), str(elf)],
                             capture_output=True, text=True, check=True).stdout
    forbidden = ['menu_available', 'menu_install', 'menu_restore', 'menu_state',
                 'ES_DeleteTitleContent', 'ES_DeleteTitle', 'ISFS_Write']
    if any(re.search(r'\b'+name+r'$', symbols, re.M) for name in forbidden):
        raise ValueError('Unexpected vWii system/settings/title-delete writer linked')
    disassembly = subprocess.run([str(DKP/'devkitPPC/bin/powerpc-eabi-objdump.exe'), '-d', str(elf)],
                                  capture_output=True, text=True, check=True).stdout
    if '__wrap_CONF_SaveChanges' not in symbols or re.search(
            r'\bb(?:l)?\s+[^\n]*<CONF_SaveChanges>', disassembly):
        raise ValueError('libogc settings save bypassed the read-only wrapper')
    subprocess.run([str(DKP/'tools/bin/elf2dol.exe'), str(elf), str(output)],
                   capture_output=True, check=True)
    return dict(compile_warnings=0, forbidden_symbols_absent=True, configuration_save_wrapped=True)


def stage_source(folder, rows):
    folder.mkdir(parents=True)
    source = installer_source(SOURCE.read_text(encoding='utf-8'), rows)
    (folder/'main.c').write_text(source, encoding='utf-8', newline='\n')
    (folder/'config_readonly.c').write_text(readonly_config_source(), encoding='utf-8', newline='\n')
    shutil.copy2(SOURCE.with_name('kwce.h'), folder/'kwce.h')


def check(package, reproduce=False):
    cfg = config()
    record, _ = sd_files(package)
    if record['channels'] != [dict(r, conversion=record['channels'][i]['conversion'])
                              for i, r in enumerate(cfg['channels'])]:
        raise ValueError('vWii channel snapshot differs from configuration')
    if record['config_sha256'] != sha256(CONFIG):
        raise ValueError('vWii configuration digest differs')
    if record['pipeline_sha256'] != {p: sha256(ROOT/p) for p in PIPELINE}:
        raise ValueError('vWii build pipeline snapshot differs')
    expected_source = installer_source(SOURCE.read_text(encoding='utf-8'), cfg['channels'])
    if (package/'source/main.c').read_text(encoding='utf-8') != expected_source:
        raise ValueError('vWii generated installer source differs')
    if sha256(package/'source/kwce.h') != sha256(SOURCE.with_name('kwce.h')):
        raise ValueError('vWii generated header differs')
    if (package/'source/config_readonly.c').read_text(encoding='utf-8') != readonly_config_source():
        raise ValueError('vWii read-only configuration wrapper differs')
    for row in cfg['channels']:
        payload, checks = convert_wad(*inputs(row), row['id'])
        output = package/DATA/row['id']/'korean.wad'
        if output.read_bytes() != payload or checks != next(
                r['conversion'] for r in record['channels'] if r['id'] == row['id']):
            raise ValueError('vWii WAD reproduction differs')
    if reproduce:
        base = ROOT/'workspace/private'
        n = 1
        while (base/f'vwii-reproduce-{n}').exists():
            n += 1
        staged = base/f'vwii-reproduce-{n}'
        stage_source(staged, cfg['channels'])
        boot = staged/'boot.dol'
        compile_installer(staged, boot)
        if boot.read_bytes() != (package/APP/'boot.dol').read_bytes():
            raise ValueError('vWii installer binary reproduction differs')
    print('PASS: Korean vWii candidate; 7 WADs reproduced, contents/IOS/title IDs preserved; '
          + ('installer binary reproduced; ' if reproduce else '')
          + 'isolated paths, no system/menu writer; hardware unverified')


def build():
    cfg = config()
    base = ROOT/'workspace/hardware'
    base.mkdir(parents=True, exist_ok=True)
    n = 1
    while (base/f'kwce-vwii-ko-v{n}').exists():
        n += 1
    out = base/f'kwce-vwii-ko-v{n}'
    out.mkdir()
    rows = []
    for row in cfg['channels']:
        payload, checks = convert_wad(*inputs(row), row['id'])
        target = out/DATA/row['id']/'korean.wad'
        target.parent.mkdir(parents=True)
        target.write_bytes(payload)
        rows.append(dict(row, conversion=checks))
        print(f'PASS: {row["id"]} r{row["build"]}, region 3, content bytes preserved', flush=True)
    stage_source(out/'source', rows)
    app = out/APP
    app.mkdir(parents=True)
    compiled = compile_installer(out/'source', app/'boot.dol')
    (app/'meta.xml').write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<app version="1"><name>KWCE Korean vWii (v{n})</name><coder>KWCE</coder><version>0.1-vwii-ko.{n}</version>
<short_description>Korean vWii channel candidates</short_description>
<long_description>For the linked Korean vWii setup on Wii U. Seven channel candidates; vWii d2x cIOS249 required. Install only, no downgrade, no System Menu/IOS/Priiloader changes. Real-console behavior unverified. Nintendo/TV Guide experimental.</long_description></app>
''', encoding='utf-8')
    shutil.copy2(base/'kwce-alpha-v7/apps/kwce-installer/icon.png', app/'icon.png')
    (out/DATA/'packages.txt').write_text('# id|title id|name|experimental\n'+''.join(
        f'{r["id"]}|{r["title_id"]}|{r["label"]}|{int(r["experimental"])}\n' for r in rows), encoding='ascii')
    guide = (ROOT/'docs/hardware/VWII-KO-README-ko.txt').read_text(encoding='utf-8')
    (out/README).write_text(guide.replace('@PACKAGE@', out.name).replace('@REVISION@', str(n)), encoding='utf-8')
    files = [*sorted(app.iterdir()), out/DATA/'packages.txt', out/README]
    files += [out/DATA/c/'korean.wad' for c in TITLES]
    record = dict(kind=KIND, package=out.name, config_sha256=sha256(CONFIG),
                  target=cfg['target'], guide_url=cfg['guide_url'], channels=rows,
                  pipeline_sha256={p: sha256(ROOT/p) for p in PIPELINE}, **compiled,
                  menu_writer_linked=False, priiloader_update=False, system_titles_included=False,
                  iso_included=False, hardware_success_verified=False, publish=False,
                  install_only=True, downgrade_allowed=False,
                  sd_files=[dict(path=p.relative_to(out).as_posix(), bytes=p.stat().st_size,
                                 sha256=sha256(p)) for p in files])
    manifest = out/'package-manifest.json'
    manifest.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (out/'package-manifest.sha256').write_text(sha256(manifest)+'\n', encoding='ascii')
    check(out, reproduce=True)
    print(f'PASS: {out.name} created; SD not copied, console not operated')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--reproduce', action='store_true')
    ap.add_argument('--package')
    args = ap.parse_args()
    if args.package and not re.fullmatch(r'kwce-vwii-ko-v[1-9][0-9]*', args.package):
        raise SystemExit('Invalid vWii package name')
    if args.check:
        if args.package:
            package = ROOT/'workspace/hardware'/args.package
        else:
            candidates = [p for p in (ROOT/'workspace/hardware').glob('kwce-vwii-ko-v*')
                          if re.fullmatch(r'kwce-vwii-ko-v[1-9][0-9]*', p.name)
                          and (p/'package-manifest.json').is_file()]
            if not candidates:
                raise SystemExit('No completed vWii candidate; run this script without --check first')
            package = max(candidates, key=lambda p: int(p.name.rsplit('-v', 1)[1]))
        check(package, args.reproduce)
    else:
        build()


if __name__ == '__main__':
    main()

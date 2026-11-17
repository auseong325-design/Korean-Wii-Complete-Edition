"""Build an isolated, user-operated News branch trace and v25 return package."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1];sys.path.insert(0, str(ROOT))
from kwce.channel_hardware import installer_source
from kwce.channels import load_library
from kwce.hardware import hardware_wad
from kwce.news_branch_diagnostic import sd_files, sha
DKP = ROOT / 'tools/devkitpro-root/opt/devkitpro'


def main():
    out = ROOT / 'workspace/hardware/kwce-news-trace-sd-v6'
    if out.exists(): raise ValueError('Existing package preserved')
    work = out / 'source';work.mkdir(parents=True)
    root = ROOT / 'homebrew/kwce-installer/source'
    original_source = (root / 'main.c').read_text(encoding='utf-8')
    source = installer_source(original_source, [{'title_id': '0001000248414745'}])
    old = '#define BASE "sd:/kwce"';new = '#define BASE "sd:/kwce-news-trace"'
    if source.count(old) != 1: raise ValueError('Installer base anchor')
    source = source.replace(old, new)
    source = source.replace('1 (GC X): install Korean   2 (GC Y): restore', '1 (GC X): apply selected build')
    source = source.replace('0.4-channels-v1', '1.0-news-trace')
    source = source.replace('BASE "/state/%s.txt"', 'BASE "/state/%.31s.txt"')
    old = 'else do_restore(&pkgs[sel]);'
    if source.count(old) != 1: raise ValueError('Restore control anchor')
    source = source.replace(old, 'else { say("Restore key disabled. Select News return v25 and install it.\\n"); wait_any(); }')
    a = source.index('/* Remove contents and tickets;')
    b = source.index('/* ---- packages / screen', a)
    source = source[:a] + r'''/* Strict same-version News replacement: no uninstall or first install. */
static void do_install(const package *p)
{
    char path[96];
    snprintf(path, sizeof path, BASE "/%s/korean.wad", p->id);
    FILE *f = fopen(path, "rb");
    if (!f) { say("  Missing News WAD.\\n"); wait_any(); return; }
    u32 h[8]; u16 version = 0;
    int ok = fread(h, 4, 8, f) == 8;
    if (ok) {
        u32 o = ALIGN64(h[0]) + ALIGN64(h[2]) + ALIGN64(h[3]) + ALIGN64(h[4]) + 0x1DC;
        ok = !fseek(f, o, SEEK_SET) && fread(&version, 2, 1, f) == 1;
    }
    fclose(f);
    if (!ok || installed_version(p->tid) != version) {
        say("  Existing News channel and WAD must have the same title version. Nothing changed.\\n");
        wait_any(); return;
    }
    say("\\n== News channel: %s\\n", p->name);
    if (!confirm("Replace the News channel? Do not power off during installation.")) return;
    install_wad(path, p->tid);
    wait_any();
}

''' + source[b:]
    source = source.replace(r'\\n', r'\n')
    if 'tid != 0x0001000248414745ULL' not in source or 'menu_install(' in source:
        raise ValueError('Title-only restriction missing')
    (work / 'main.c').write_text(source, encoding='utf-8');shutil.copy2(root / 'kwce.h', work / 'kwce.h')
    elf = work / 'installer.elf';dol = work / 'boot.dol'
    cmd = [str(DKP / 'devkitPPC/bin/powerpc-eabi-gcc.exe'), '-O2', '-Wall', '-Wextra', '-Wno-unused-function',
           '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections', '-mrvl', '-mcpu=750', '-meabi',
           '-mhard-float', '-DGEKKO', '-I' + str(DKP / 'libogc/include'), '-L' + str(DKP / 'libogc/lib/wii'),
           str(work / 'main.c'), '-lwiiuse', '-lbte', '-lfat', '-logc', '-lm', '-o', str(elf)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    (work / 'compile.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode or 'warning:' in result.stderr: raise ValueError('Trace installer compiler failed or warned')
    nm = subprocess.run([str(DKP / 'devkitPPC/bin/powerpc-eabi-nm.exe'), str(elf)],
                        capture_output=True, text=True, check=True).stdout
    if any(line.rstrip().endswith(' ' + symbol) for line in nm.splitlines()
           for symbol in ('ES_DeleteTitle', 'ES_DeleteTicket', 'ES_DeleteTitleContent')):
        raise ValueError('Title removal linked')
    subprocess.run([str(DKP / 'tools/bin/elf2dol.exe'), str(elf), str(dol)], capture_output=True, check=True)
    app = out / 'apps/kwce-news-trace';app.mkdir(parents=True);shutil.copy2(dol, app / 'boot.dol')
    shutil.copy2(ROOT / 'workspace/hardware/kwce-channels-v1/apps/kwce-installer/icon.png', app / 'icon.png')
    (app / 'meta.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><app version="1"><name>KWCE News Branch Trace</name><coder>KWCE</coder><version>1.0</version><short_description>News diagnostics and v25 return</short_description></app>\n', encoding='utf-8')
    base = ROOT / 'workspace/channels/news';orig = (base / 'originals/news-usa-wiilink-archive.wad').read_bytes()
    lib = load_library();records = {}
    for key, rev in [('trace', 26), ('return', 25)]:
        source_wad = (base / f'build-v{rev}/news-ko-personal.wad').read_bytes()
        manifest = json.loads((base / f'build-v{rev}/build-manifest.json').read_text(encoding='utf-8'))
        if sha(source_wad) != manifest['wads']['personal']['sha256']: raise ValueError('Source WAD hash mismatch')
        target, facts = hardware_wad(source_wad, orig)
        a=lib.title.Title();a.load_wad(source_wad);b=lib.title.Title();b.load_wad(target)
        if [a.get_content_by_index(i) for i in range(12)] != [b.get_content_by_index(i) for i in range(12)]:
            raise ValueError('Hardware WAD changes content')
        folder = out / 'kwce-news-trace' / key;folder.mkdir(parents=True)
        (folder / 'korean.wad').write_bytes(target);records[key] = {'revision': rev, 'sha256': sha(target)}
    listing = out / 'kwce-news-trace/packages.txt'
    listing.write_text('trace|0001000248414745|News trace v26|1\nreturn|0001000248414745|News return v25|0\n',encoding='ascii')
    (out / 'KWCE-NEWS-TRACE-README-ko.txt').write_text(
        '뉴스 오류 분기 진단 전용. KWCE News Branch Trace에서 News trace v26을 1/A로 설치하고 뉴스 오류 번호를 기록합니다. '
        '진단 후 같은 앱에서 News return v25를 1/A로 설치하여 이전 채널로 돌아갑니다. '
        'v26의 000009는 마지막 데이터 검사 -1, 000010은 마지막 검사 값이 0이며 표시 조건 실패 또는 검사가 실행되지 않은 경우, '
        '000008은 마지막 검사 값 -2를 나타냅니다. 이 번호만으로 원인을 확정할 수 없습니다. 다른 오류는 기존과 다를 수 있습니다. '
        '진단용이며 해결판이 아닙니다. 뉴스 채널만 대상으로 하며 cIOS 249가 필요합니다.\n',encoding='utf-8')
    payload = [out / name for name in sorted(__import__('kwce.news_branch_diagnostic', fromlist=['ALLOWED']).ALLOWED)]
    rows = [{'path': p.relative_to(out).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())} for p in payload]
    meta = {'kind': 'news-branch-trace-v1', 'title_id': '0001000248414745', 'production': False,
            'menu_writer_linked': False, 'hardware_tested': False, 'wads': records, 'sd_files': rows}
    raw = (json.dumps(meta, indent=2) + '\n').encode('utf-8');(out / 'package-manifest.json').write_bytes(raw)
    (out / 'package-manifest.sha256').write_text(sha(raw) + '\n', encoding='ascii');sd_files(out)
    print('PASS: News-only trace and return package; source scope, WADs and hashes verified; real console untested')

if __name__ == '__main__': main()

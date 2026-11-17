"""Build the unmodified WiiLink Mail Patcher (GPLv3) as a KWCE package extra.

Source: external/other-tools/Mail-Patcher (a clean clone of https://github.com/WiiLink24/Mail-Patcher).
The tool is compiled as-is with the project's devkitPPC, no source change. Output folder
(new each run, ignored by Git):

    workspace/hardware/extras/wiilink-mail-patcher-<commit8>/
        boot.dol  meta.xml  icon.png      the Homebrew Channel app
        LICENSE                          GNU GPL v3 text from the repository
        SOURCE.txt                       upstream URL, exact commit, build recipe
        source.zip                       `git archive` of that commit (Corresponding Source)

The installer copies this folder into sd:/apps/WiiLink-Mail-Patcher only when the user chooses it
(console without WiiLink). Nothing here runs on, or sends anything to, a console.

    python scripts/build_wiilink_extra.py
"""
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DKP = ROOT / 'tools/devkitpro-root/opt/devkitpro'
SRC = ROOT / 'external/other-tools/Mail-Patcher'
SOURCES = ('main.cpp', 'patcher.cpp', 'config.cpp', 'utils.cpp', 'nwc24dl.cpp')
FLAGS = ['-std=c++20', '-O2', '-Wall', '-Wextra', '-Wno-unused-function', '-DGEKKO', '-mrvl', '-mcpu=750',
         '-meabi', '-mhard-float']
LIBS = ['-lwiiuse', '-lbte', '-lfat', '-logc', '-lm']


def git(*args):
    r = subprocess.run(['git', '-C', str(SRC), *args], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit('git failed: ' + ' '.join(args) + '\n' + r.stderr)
    return r.stdout.strip()


def main():
    if git('status', '--porcelain'):
        raise SystemExit('Mail-Patcher working tree is not clean; refusing to build a modified copy')
    commit = git('rev-parse', 'HEAD')
    remote = git('remote', 'get-url', 'origin')
    date = git('log', '-1', '--format=%cd', '--date=short')
    base = ROOT / 'workspace/hardware/extras'
    base.mkdir(parents=True, exist_ok=True)
    out = base / f'wiilink-mail-patcher-{commit[:8]}'
    if out.exists():
        raise SystemExit(f'{out.relative_to(ROOT)} already exists; preserved')
    out.mkdir()
    work = out / '_build'
    work.mkdir()
    elf = work / 'wiilink-mail-patcher.elf'
    cc = [str(DKP / 'devkitPPC/bin/powerpc-eabi-g++.exe'), *FLAGS, f'-I{SRC}', f'-I{DKP / "libogc/include"}',
          f'-L{DKP / "libogc/lib/wii"}', *[str(SRC / s) for s in SOURCES], *LIBS, '-o', str(elf)]
    r = subprocess.run(cc, capture_output=True, text=True, cwd=SRC)
    if r.returncode:
        shutil.rmtree(out)
        raise SystemExit('Mail Patcher compile failed:\n' + r.stderr[-2000:])
    version = subprocess.run([str(DKP / 'devkitPPC/bin/powerpc-eabi-g++.exe'), '--version'],
                             capture_output=True, text=True).stdout.splitlines()[0]
    subprocess.run([str(DKP / 'tools/bin/elf2dol.exe'), str(elf), str(out / 'boot.dol')], check=True,
                   capture_output=True)
    shutil.rmtree(work)
    app = SRC / 'apps/Mail-Patcher'
    shutil.copy2(app / 'meta.xml', out / 'meta.xml')
    shutil.copy2(app / 'icon.png', out / 'icon.png')
    shutil.copy2(SRC / 'LICENSE', out / 'LICENSE')
    r = subprocess.run(['git', '-C', str(SRC), 'archive', '--format=zip', '-o', str(out / 'source.zip'), 'HEAD'],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit('git archive failed: ' + r.stderr)
    (out / 'SOURCE.txt').write_text(
        'WiiLink Mail Patcher 2.2.2 -- unmodified, compiled by the KWCE project\n'
        f'Upstream : {remote.removesuffix(".git")}\n'
        f'Commit   : {commit} ({date})\n'
        'License  : GNU General Public License v3 (full text: LICENSE)\n'
        'Source   : source.zip in this folder is `git archive` of that exact commit (the Corresponding\n'
        '           Source); the same code is at the upstream URL above.\n'
        f'Build    : {version}; sources {" ".join(SOURCES)};\n'
        f'           flags {" ".join(FLAGS)}; libs {" ".join(LIBS)}; elf2dol.\n'
        '\n'
        'This program belongs to WiiLink, not to KWCE. KWCE only copies it into apps/ if you choose to.\n'
        'It registers the console\'s WiiConnect24 mail with WiiLink and contacts WiiLink\'s servers when\n'
        'YOU run it from the Homebrew Channel.\n', encoding='utf-8', newline='\n')
    for p in sorted(out.iterdir()):
        print(f'{p.name:<12} {p.stat().st_size:>9} B  sha256 {hashlib.sha256(p.read_bytes()).hexdigest()[:16]}')
    print('PASS:', out.relative_to(ROOT).as_posix())


if __name__ == '__main__':
    sys.exit(main())

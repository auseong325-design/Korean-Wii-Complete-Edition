"""Recreate the reviewed Linux tools; never change Windows sources or locks.

Run through setup_linux.sh to create the separate Python environment first.
Native Dolphin installation is immutable: a different binary needs a new prefix
and a reviewed new lock, never an automatic hash/lock update.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.linux_runtime import BASE, PRIVATE, default_profile, digest, prepare, sources, stopped
from kwce.toolchain import DKP, tool


def run(command, log):
    with (PRIVATE / log).open('ab') as out:
        subprocess.run([str(x) for x in command], cwd=ROOT, stdout=out, stderr=out, check=True)


def toolchain():
    import zstandard
    rows = json.loads((ROOT / 'configs/devkit-linux.lock.json').read_text())
    for row in rows:
        name = row['url'].rsplit('/', 1)[1]
        package = ROOT / ('tools/linux' if 'linux_x86_64' in name else 'tools/packages') / name
        package.parent.mkdir(parents=True, exist_ok=True)
        if not package.exists():
            temp = package.with_name(package.name + '.partial')
            run(['curl', '--fail', '--location', '--max-time', '180', '--output', temp, row['url']], 'toolchain-download.log')
            if digest(temp) != row['sha256']:
                raise ValueError('Toolchain download hash mismatch')
            temp.rename(package)
        if digest(package) != row['sha256']:
            raise ValueError('Cached toolchain archive hash mismatch')
    expected = json.loads((ROOT / 'configs/gc-comment-linux.lock.json').read_text())
    if tool('powerpc-eabi-gcc.exe').exists():
        if (digest(tool('powerpc-eabi-gcc.exe')) != expected['compiler_sha256']
                or digest(tool('powerpc-eabi-objcopy.exe')) != expected['objcopy_sha256']):
            raise ValueError('Existing Linux toolchain differs; refusing overwrite')
    else:
        dest = ROOT / 'tools/linux/devkitpro-root'
        if dest.exists() and any(dest.iterdir()):
            raise ValueError('Partial toolchain exists; inspect privately before retrying')
        dest.mkdir(parents=True, exist_ok=True)
        for row in rows:
            name = row['url'].rsplit('/', 1)[1]
            p = ROOT / ('tools/linux' if 'linux_x86_64' in name else 'tools/packages') / name
            with p.open('rb') as raw, zstandard.ZstdDecompressor().stream_reader(raw) as stream:
                with tarfile.open(fileobj=stream, mode='r|*') as archive:
                    archive.extractall(dest, filter='data')
    print('PASS exact-version Linux devkitPPC archives and compiler')


def dolphin(jobs):
    lock = json.loads((ROOT / 'configs/dolphin-linux.lock.json').read_text())
    exe = ROOT / lock['executable']
    if exe.exists():
        if digest(exe) != lock['executable_sha256']:
            raise ValueError('Existing native Dolphin differs; immutable prefix not overwritten')
        print('PASS pinned native Dolphin already installed')
        return
    prefix = ROOT / lock['prefix']
    if prefix.exists() and any(prefix.iterdir()):
        raise ValueError('Partial native install exists; refusing overwrite')
    src = ROOT / 'tools/linux/dolphin-2609a-src'
    if not src.exists():
        run(['git', 'clone', '--depth', '1', '--branch', lock['version'], '--recurse-submodules',
             '--shallow-submodules', lock['source_url'], src], 'dolphin-source.log')
    commit = subprocess.check_output(['git', '-C', str(src), 'rev-parse', 'HEAD'], text=True).strip()
    tag = subprocess.check_output(['git', '-C', str(src), 'rev-parse', lock['version']], text=True).strip()
    if commit != lock['source_commit'] or tag != lock['tag_object']:
        raise ValueError('Dolphin source/tag differs from reviewed lock')
    if not all(digest(src / rel) == sha for rel, sha in lock['source_derivative'].items()):
        status = subprocess.check_output(['git', '-C', str(src), 'status', '--porcelain', '--untracked-files=no'])
        if status:
            raise ValueError('Unreviewed Dolphin source changes; refusing patch')
        patch = ROOT / 'configs/dolphin-linux-v1.patch'
        run(['git', '-C', src, 'apply', '--check', patch], 'dolphin-patch.log')
        run(['git', '-C', src, 'apply', patch], 'dolphin-patch.log')
    if not all(digest(src / rel) == sha for rel, sha in lock['source_derivative'].items()):
        raise ValueError('Dolphin source derivative hash mismatch')
    build = ROOT / 'tools/linux/dolphin-2609a-build'
    options = ['-DCMAKE_BUILD_TYPE=Release', '-DENABLE_TESTS=OFF', '-DENABLE_NOGUI=ON',
               '-DENABLE_ANALYTICS=OFF', '-DENABLE_AUTOUPDATE=OFF', '-DUSE_DISCORD_PRESENCE=OFF',
               '-DUSE_RETRO_ACHIEVEMENTS=OFF', '-DUSE_UPNP=OFF', '-DUSE_MGBA=OFF',
               '-DENABLE_LLVM=OFF', '-DENCODE_FRAMEDUMPS=OFF']
    cmake = ROOT / '.venv-linux/bin/cmake'
    run([cmake, '-S', src, '-B', build, '-G', 'Ninja', f'-DCMAKE_INSTALL_PREFIX={prefix}', *options], 'dolphin-cmake.log')
    run([cmake, '--build', build, '--parallel', str(jobs)], 'dolphin-build.log')
    # Verify before installing, so a different compiler output cannot silently
    # replace the approved executable or create an apparently approved install.
    if digest(build / 'Binaries/dolphin-emu') != lock['executable_sha256']:
        raise ValueError('Rebuilt binary differs; retain build for review and use a new revision/lock')
    run([cmake, '--install', build], 'dolphin-install.log')
    print('PASS native Dolphin built from the exact reviewed source derivative')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--jobs', type=int, default=10)
    ap.add_argument('--profiles', action='store_true', help='prepare missing approved offline profile copies')
    args = ap.parse_args()
    if sys.platform != 'linux' or not 1 <= args.jobs <= 32:
        raise ValueError('Linux host and 1..32 build jobs required')
    stopped()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    toolchain()
    dolphin(args.jobs)
    if args.profiles:
        for source in sources():
            name = default_profile() if source == 'menu' else source + '-v1'
            if not (BASE / name).exists():
                prepare(source, with_gc_disc=source == 'menu', target_name=name)
            else:
                print(f'KEEP existing Linux profile {name}')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'FAIL Linux setup: {exc}' if isinstance(exc, ValueError) else 'FAIL Linux setup: see private setup logs')
        raise SystemExit(1)

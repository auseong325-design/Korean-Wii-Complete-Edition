"""Build a numbered WiiMC fork with the pinned Linux compiler and PPC SDK.

Windows caches, tools and profiles are never used or changed. No SD deployment.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import dvd_player_fork
from kwce.toolchain import DKP, tool


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_sdk():
    import zstandard
    target = ROOT/'tools/linux/dvd-player-sdk-r2490'
    lock = json.loads((ROOT/'configs/dvd-player-toolchain.lock.json').read_text())
    for entry in lock['packages']:
        if entry['target'] != 'devkitpro':
            continue
        if not entry['url'].endswith('-any.pkg.tar.zst'):
            raise ValueError('Expected host-independent PPC SDK package')
        archive = ROOT/'tools/packages'/entry['url'].rsplit('/', 1)[-1]
        if sha(archive) != entry['sha256']:
            raise ValueError('Pinned PPC SDK package mismatch')
        with archive.open('rb') as f, zstandard.ZstdDecompressor().stream_reader(f) as raw:
            with tarfile.open(fileobj=raw, mode='r|*') as tar:
                for member in tar:
                    if member.name.startswith(('opt/devkitpro/libogc2/', 'opt/devkitpro/portlibs/')):
                        tar.extract(member, target, filter='data')
    prefix = target/'opt/devkitpro'
    # Rules reference DEVKITPRO/tools, while the compiler is selected explicitly.
    link = prefix/'tools'
    if link.is_symlink():
        if link.resolve() != (DKP/'tools').resolve():
            raise ValueError('Unexpected Linux tool symlink')
    elif link.exists():
        raise ValueError('Unexpected tools directory')
    else:
        link.symlink_to(DKP/'tools', target_is_directory=True)
    return prefix


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--revision', type=int, required=True)
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--reproduce', action='store_true')
    a = ap.parse_args()
    if sys.platform != 'linux' or a.revision < 52 or a.jobs < 1:
        raise ValueError('New Linux player revision >=52 required')
    preserved = ROOT/f'workspace/channels/dvd-player/build-v{a.revision}'
    expected = None
    if a.reproduce:
        expected = json.loads((preserved/'build-manifest.json').read_text())
        if expected.get('host') != 'linux' or sha(preserved/'boot.dol') != expected['boot_dol_sha256']:
            raise ValueError('Preserved Linux player differs')
        n = 1
        while (ROOT/f'workspace/private/linux-dvd-reproduce-v{a.revision}-{n}').exists():
            n += 1
        out = ROOT/f'workspace/private/linux-dvd-reproduce-v{a.revision}-{n}'
    else:
        out = preserved
        if out.exists():
            raise ValueError('Existing numbered player preserved')
    upstream = ROOT/'external/other-tools/wiimc'
    head = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    if head != dvd_player_fork.SOURCE_COMMIT:
        raise ValueError('Upstream WiiMC commit differs')
    sdk = prepare_sdk()
    cache = ROOT/'workspace/linux/dvd-player-cache'
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT/'workspace/linux') as temp:
        stage = Path(temp)/'source'
        shutil.copytree(upstream, stage, ignore=shutil.ignore_patterns('.git', 'executables', 'build'))
        applied = dvd_player_fork.apply(stage, ROOT, a.revision)
        # Upstream tracks generated version.h from an older host. Copying it
        # over a cache alternates compiler strings between cold/warm builds.
        compiler_version = subprocess.check_output([str(tool('powerpc-eabi-gcc')), '-dumpversion'], text=True).strip()
        (stage/'source/mplayer/version.h').write_text(
            '#define VERSION "UNKNOWN-'+compiler_version+'"\n'
            '#define MP_TITLE "%s "VERSION" (C) 2000-2012 MPlayer Team\\n"\n')
        version_header = (stage/'source/mplayer/ffmpeg/version.h').read_text()
        ffmpeg_version = re.fullmatch(r'#define FFMPEG_VERSION "([^"\n]+)"\s*', version_header)
        if not ffmpeg_version:
            raise ValueError('Pinned FFmpeg version header changed')
        (stage/'source/mplayer/ffmpeg/VERSION').write_text(ffmpeg_version[1]+'\n')
        makefile = stage/'Makefile'
        text = makefile.read_text()
        old = '\tcd source/mplayer; $(MAKE) -f Makefile; cd ../..'
        if text.count(old) != 1:
            raise ValueError('Expected MPlayer build rule changed')
        makefile.write_text(text.replace(old, '\t$(MAKE) -C source/mplayer -f Makefile'))
        source_hashes = {}
        for src in stage.rglob('*'):
            if not src.is_file():
                continue
            rel = src.relative_to(stage)
            data = src.read_bytes()
            if src.suffix == '.sh':
                data = data.replace(b'\r\n', b'\n')
            source_hashes[str(rel)] = hashlib.sha256(data).hexdigest()
            dst = cache/rel
            if not dst.exists() or dst.read_bytes() != data:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(data)
            if src.suffix == '.sh':
                dst.chmod(0o755)
    signature = sha(cache/'source/mplayer/config.mak')
    flags = cache/'kwce-mplayer-flags.sha256'
    if flags.exists() and flags.read_text() != signature:
        for obj in (cache/'source/mplayer').rglob('*'):
            if obj.suffix in ('.o', '.a'):
                obj.unlink()
        (cache/'libmplayerwii.a').unlink(missing_ok=True)
    flags.write_text(signature)
    for suffix in ('elf', 'dol'):
        (cache/f'executables/wiimc.{suffix}').unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT/'workspace/linux') as temp:
        subprocess.run([str(tool('powerpc-eabi-ar')), 'x', str(sdk/'libogc2/wii/lib/libwiiuse.a'), 'wpad.o'], cwd=temp, check=True)
        subprocess.run([str(tool('powerpc-eabi-objcopy')), '--globalize-symbol=__wpads', str(Path(temp)/'wpad.o'), str(cache/'kwce_wpad.o')], check=True)
    env = dict(os.environ, DEVKITPRO=str(sdk), DEVKITPPC=str(DKP/'devkitPPC'),
               PORTLIBS_PATH=str(sdk/'portlibs'),
               PATH=os.pathsep.join([str(DKP/'devkitPPC/bin'), str(DKP/'tools/bin'), '/usr/bin', '/bin']))
    pp = sdk/'portlibs/ppc'
    cmd = ['make', '-j'+str(a.jobs),
           f'FREETYPE_CFLAGS=-I{pp}/include/freetype2 -I{pp}/include',
           f'FREETYPE_LIBS=-L{pp}/lib -lfreetype -lpng16 -lbz2 -lbrotlidec -lbrotlicommon -lz']
    logdir = ROOT/'workspace/private/dvd-investigation'
    logdir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f'linux-player-v{a.revision}-', suffix='.log', dir=logdir, delete=False) as log:
        result = subprocess.run(cmd, cwd=cache, env=env, stdout=log, stderr=subprocess.STDOUT)
        logname = log.name
    if result.returncode:
        raise ValueError('Linux player build failed; inspect '+logname)
    out.mkdir(parents=True)
    for suffix in ('elf', 'dol'):
        shutil.copy2(cache/f'executables/wiimc.{suffix}', out/f'boot.{suffix}')
    manifest = dict(revision=a.revision, host='linux', css_decryption=False,
                    upstream='dborth/wiimc', upstream_commit=head, license='GPL-3.0 (fork, personal use only)',
                    patches_applied=applied, boot_dol_sha256=sha(out/'boot.dol'),
                    boot_dol_bytes=(out/'boot.dol').stat().st_size,
                    compiler_sha256=sha(tool('powerpc-eabi-gcc')),
                    linux_toolchain_lock_sha256=sha(ROOT/'configs/devkit-linux.lock.json'),
                    sdk_lock_sha256=sha(ROOT/'configs/dvd-player-toolchain.lock.json'),
                    sources=source_hashes)
    (out/'build-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    if expected and manifest['boot_dol_sha256'] != expected['boot_dol_sha256']:
        raise ValueError('Linux player reproduction differs; preserved original untouched')
    print(f'PASS Linux DVD player R{a.revision}: {manifest["boot_dol_bytes"]} bytes; no SD writes')


if __name__ == '__main__':
    main()

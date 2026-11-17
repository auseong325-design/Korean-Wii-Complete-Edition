"""Build the small resident DVD forwarder pinned to one reviewed player build.

New numbered output only. The forwarder replaces the multi-megabyte resident
player in the menu bundle; the player itself is read from SD after handoff.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.toolchain import DKP, tool
from kwce.dvd_native_relocate import compile_relocator, validate_payload, validate_ash_mapping
from kwce.formats import ash_compress, ash_decompress

SOURCE = ROOT/'homebrew/kwce-dvd-forwarder/r1/source/main.c'
FORBIDDEN = ('ISFS_Write', 'ISFS_Delete', 'ISFS_CreateFile', 'ES_AddTitleStart',
             'ES_AddContentStart', 'ES_DeleteTitle', 'CONF_Set', 'IOS_ReloadIOS',
             'net_init', 'net_init_async', 'net_socket', 'DI_Init', 'WPAD_Init')


def sdk():
    path = ROOT/'tools/linux/dvd-player-sdk-r2490/opt/devkitpro/libogc2/wii'
    if sys.platform != 'linux': path = DKP/'libogc2/wii'
    if not (path/'lib/libogc.a').is_file(): raise ValueError('Pinned player SDK missing')
    return path


def compile_forwarder(player, revision):
    lib = sdk()
    with tempfile.TemporaryDirectory() as temp:
        tmp = Path(temp)
        shutil.copyfile(SOURCE, tmp/'main.c')
        row = lambda data: ','.join(str(b) for b in data)
        (tmp/'pin.h').write_text(
            f'#define PLAYER_SIZE {len(player)}u\n#define PLAYER_REVISION {revision}\n'
            'static const unsigned char PLAYER_SHA1[20]={'+row(hashlib.sha1(player).digest())+'};\n'
            'static const unsigned char RELOCATOR[]={'+row(compile_relocator(ash=False))+'};\n')
        cmd = [str(tool('powerpc-eabi-gcc.exe')), '-O2', '-Wall', '-Wextra', '-Werror',
               '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
               '-ffile-prefix-map='+str(tmp)+'=.', '-mrvl', '-mcpu=750', '-meabi',
               '-mhard-float', '-DGEKKO', '-I'+str(lib/'include'), '-I'+str(tmp),
               '-L'+str(lib/'lib'), 'main.c', '-lfat', '-logc', '-lm', '-o', 'forwarder.elf']
        run = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True)
        if run.returncode: raise ValueError('Forwarder build failed:\n'+run.stderr[-3000:])
        nm = subprocess.run([str(tool('powerpc-eabi-nm.exe')), 'forwarder.elf'], cwd=tmp,
                            capture_output=True, text=True, check=True).stdout
        if any(line.rstrip().endswith(' '+name) for line in nm.splitlines() for name in FORBIDDEN):
            raise ValueError('Out-of-scope subsystem linked into forwarder')
        subprocess.run([str(tool('elf2dol.exe', DKP/'tools/bin')), 'forwarder.elf', 'boot.dol'],
                       cwd=tmp, capture_output=True, check=True)
        return (tmp/'boot.dol').read_bytes()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--player', type=int, required=True)
    ap.add_argument('--revision', type=int, required=True, help='new native module number')
    a = ap.parse_args()
    out = ROOT/f'workspace/experiments/dvd-native-module-v{a.revision}'
    if out.exists(): raise SystemExit('Existing numbered module preserved')
    build = ROOT/f'workspace/channels/dvd-player/build-v{a.player}'
    player = (build/'boot.dol').read_bytes()
    if hashlib.sha256(player).hexdigest() != json.loads((build/'build-manifest.json').read_text())['boot_dol_sha256']:
        raise ValueError('Player build differs')
    validate_payload(player)
    dol = compile_forwarder(player, a.player)
    if compile_forwarder(player, a.player) != dol: raise ValueError('Forwarder is not reproducible')
    validate_payload(dol); validate_ash_mapping(dol)
    packed = ash_compress(dol)
    if ash_decompress(packed) != dol: raise ValueError('ASH roundtrip differs')
    out.mkdir()
    (out/'forwarder.dol').write_bytes(dol); (out/'player.ash').write_bytes(packed)
    shutil.copyfile(SOURCE, out/'main.c')
    record = dict(schema=2, kind='forwarder', forwarder_revision=1, source_build=a.player,
                  player_sha256=hashlib.sha256(player).hexdigest(), player_bytes=len(player),
                  forwarder_sha256=hashlib.sha256(dol).hexdigest(), forwarder_bytes=len(dol),
                  packed_sha256=hashlib.sha256(packed).hexdigest(), bytes=len(packed),
                  source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                  sd_player_path='kwce/dvd/player.dol', physical_hardware_verified=False)
    (out/'manifest.json').write_text(json.dumps(record, indent=2)+'\n')
    print(f'PASS forwarder module v{a.revision}: player R{a.player}; resident {len(packed)} bytes '
          f'(forwarder {len(dol)}), reproducible, exact ASH roundtrip')


if __name__ == '__main__': main()

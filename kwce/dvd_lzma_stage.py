"""Experimental bounded LZMA package; not yet accepted by SD deployment."""
import hashlib
import json
import lzma
import struct
import subprocess
import tempfile
from pathlib import Path

from .toolchain import tool

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'homebrew/kwce-disc-menu/lzma-stage-v1/decode.c'
BASE = 0x81200000
LIMIT = 0x81300000


def vendor():
    """Locate an exact pinned decoder without editing the external source."""
    base = ROOT / 'tools/linux/dolphin-2609a-src/Externals/mGBA/mgba/src/third-party/lzma'
    lock = json.loads((ROOT / 'configs/dvd-lzma-decoder-v1.lock.json').read_text())
    for name, expected in lock['files'].items():
        if hashlib.sha256((base / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Pinned LZMA decoder differs')
    return base


def compile_decoder():
    source = vendor()
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp)
        def run(name, *args):
            result = subprocess.run([str(tool(name)), *map(str, args)], cwd=out,
                                    capture_output=True, text=True)
            if result.returncode:
                raise ValueError('Decoder toolchain failed: ' + result.stderr)
            return result.stdout
        for name, path in [('adapter', SOURCE), ('lzma', source / 'LzmaDec.c')]:
            run('powerpc-eabi-gcc.exe', '-Os', '-mcpu=750', '-meabi', '-msdata=none',
                '-fno-pic', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
                '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
                '-ffunction-sections', '-fdata-sections', '-D_LZMA_SIZE_OPT',
                '-I', source, '-c', path, '-o', name + '.o')
        (out / 'link.ld').write_text(
            f'ENTRY(kwce_decode)\nSECTIONS {{ . = {BASE}; '
            '.text : { KEEP(*(.entry)) *(.text*) *(.rodata*) } '
            '.data : { *(.data*) } .bss : { *(.bss*) *(.sbss*) *(COMMON) } '
            'ASSERT(SIZEOF(.bss) == 0, "decoder must not require zeroed BSS") '
            '/DISCARD/ : { *(.comment) *(.gnu.attributes) *(.eh_frame*) } }')
        libgcc = run('powerpc-eabi-gcc.exe', '-print-libgcc-file-name').strip()
        run('powerpc-eabi-ld.exe', '--no-undefined', '--gc-sections', '-T', 'link.ld',
            'adapter.o', 'lzma.o', libgcc, '-o', 'decoder.elf')
        symbols = run('powerpc-eabi-nm.exe', 'decoder.elf')
        if f'{BASE:08x} T kwce_decode' not in symbols:
            raise ValueError('Decoder entry moved')
        run('powerpc-eabi-objcopy.exe', '-O', 'binary', 'decoder.elf', 'decoder.bin')
        data = (out / 'decoder.bin').read_bytes()
        if not data or BASE + len(data) > LIMIT:
            raise ValueError('Decoder exceeds reserved post-shutdown code range')
        return data


def pack(data, decoder):
    # Decoding into the final output buffer avoids a separate 8 MiB dictionary.
    if not data or 0x80003e00 + len(data) > BASE:
        raise ValueError('Expanded player overlaps decoder')
    compressed = lzma.compress(data, format=lzma.FORMAT_ALONE, preset=6)
    offset = (32 + len(decoder) + 31) & ~31
    header = struct.pack('>5I', 0x4b574c31, len(data), offset,
                         len(compressed), len(decoder)) + bytes(12)
    return header + decoder + bytes(offset - 32 - len(decoder)) + compressed


def unpack(package):
    if len(package) < 32:
        raise ValueError('Short LZMA package')
    magic, raw, offset, size, code = struct.unpack_from('>5I', package)
    if (magic != 0x4b574c31 or not code or offset % 32 or offset < 32 + code
            or size < 13 or offset + size != len(package)
            or not raw or 0x80003e00 + raw > BASE):
        raise ValueError('Invalid LZMA package')
    dec = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
    data = dec.decompress(package[offset:], max_length=raw + 1)
    if len(data) != raw or not dec.eof or dec.unused_data:
        raise ValueError('LZMA payload size/end mismatch')
    return data


def compile_relocator(package_size):
    from .ppc_patch import assemble
    source = (ROOT / 'homebrew/kwce-disc-menu/native-v1/relocate.s').read_text()
    prefix = f'''kwce_relocate:
    mr r31,r3
    lwz r5,16(r31)
    addi r6,r31,32
    lis r4,0x8120
    mr r7,r4
    mtctr r5
decoder_copy:
    lbz r9,0(r6)
    stb r9,0(r7)
    addi r6,r6,1
    addi r7,r7,1
    bdnz decoder_copy
    bl flush
    mr r3,r31
    lis r4,{package_size >> 16}
    ori r4,r4,{package_size & 65535}
    lis r5,0x8000
    ori r5,r5,0x3e00
    lwz r6,4(r31)
    lis r12,0x8120
    mtctr r12
    bctrl
    cmpwi r3,1
    bne decoder_failed
    lis r3,0x8000
    ori r3,r3,0x3e00
'''
    source = source.replace('kwce_relocate:\n', prefix)
    source += '\ndecoder_failed:\n    b decoder_failed\n'
    return assemble(source, 0, {})

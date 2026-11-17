"""Execute the built read-only News cache parser on synthetic FAT/VFF data."""
import argparse
import struct
import tempfile
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'workspace/private/unicorn-2.1.1'))
sys.path.insert(0, str(ROOT / 'workspace/channels/nintendo/rc3'))
from dol import Dol
from kwce.channel_vff import VFF
from kwce.channels import compress_lz10, load_library
from unicorn import Uc, UC_ARCH_PPC, UC_MODE_PPC32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
from unicorn.ppc_const import (UC_PPC_REG_1, UC_PPC_REG_3, UC_PPC_REG_4,
                               UC_PPC_REG_5, UC_PPC_REG_6, UC_PPC_REG_LR,
                               UC_PPC_REG_PC)

NOW = 1793550000
EPOCH_MINUTES = (NOW - 946684800) // 60


def run(dol, symbols, fixture, snapshot=False):
    machine = Uc(UC_ARCH_PPC, UC_MODE_PPC32 | UC_MODE_BIG_ENDIAN)
    machine.mem_map(0x80000000, 0x01000000)
    machine.mem_map(0x81000000, 0x02000000)
    for _, offset, address, size in dol.sections:
        machine.mem_write(address, dol.data[offset:offset + size])
    data, result = 0x81010000, 0x81a10000
    machine.mem_write(data, fixture)
    for register, value in ((UC_PPC_REG_1, 0x82f00000), (UC_PPC_REG_3, data),
                            (UC_PPC_REG_4, len(fixture)), (UC_PPC_REG_5, NOW),
                            (UC_PPC_REG_6, result), (UC_PPC_REG_LR, 0x81000000)):
        machine.reg_write(register, value)
    allocation = [0x82000000]
    captured = bytearray()
    if snapshot:
        machine.mem_write(symbols["news_snapshot_stream"], struct.pack(">I", 0x81008000))

    def hook(uc, address, _size, _user):
        if snapshot and address == symbols['fputc']:
            captured.append(uc.reg_read(UC_PPC_REG_3) & 255)
            uc.reg_write(UC_PPC_REG_PC, uc.reg_read(UC_PPC_REG_LR))
        elif address == symbols['malloc']:
            n = uc.reg_read(UC_PPC_REG_3)
            pointer = allocation[0]
            allocation[0] += (n + 31) & ~31
            if allocation[0] >= 0x82e00000:
                raise ValueError('Synthetic allocator limit')
            uc.reg_write(UC_PPC_REG_3, pointer)
            uc.reg_write(UC_PPC_REG_PC, uc.reg_read(UC_PPC_REG_LR))
        elif address == symbols['free']:
            uc.reg_write(UC_PPC_REG_PC, uc.reg_read(UC_PPC_REG_LR))

    machine.hook_add(UC_HOOK_CODE, hook)
    machine.emu_start(symbols['news_cache_inspect'], 0x81000000, count=5_000_000)
    response = machine.reg_read(UC_PPC_REG_3), struct.unpack('>19I', machine.mem_read(result, 76))
    return (response, bytes(captured)) if snapshot else response


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--elf', type=Path, required=True)
    ap.add_argument('--dol', type=Path, required=True)
    args = ap.parse_args()
    gcc = ROOT / 'tools/devkitpro-root/opt/devkitpro/devkitPPC/bin/powerpc-eabi-nm.exe'
    lines = subprocess.run([str(gcc), str(args.elf)], capture_output=True, text=True, check=True).stdout.splitlines()
    symbols = {line.split()[-1]: int(line.split()[0], 16) for line in lines if len(line.split()) == 3}
    dol = Dol(args.dol.read_bytes())
    load_library()
    empty = (ROOT / 'workspace/private/news-empty-vff.bin').read_bytes()
    if VFF(empty).entries():
        raise ValueError('Expected empty local synthetic VFF')
    if run(dol, symbols, empty) != (0, (1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)):
        raise ValueError('Empty fixture failed')
    fixture = empty
    for index, (country, expiry, future) in enumerate(((49, 60, 0), (136, -60, 0), (49, 60, 3000), (49, 60, 0), (49, 60, 0), (49, 60, 0))):
        header = bytearray(512)
        struct.pack_into('>5I', header, 0, 512, len(header), 0, EPOCH_MINUTES + future, EPOCH_MINUTES + expiry)
        header[20] = country
        header[28] = 1
        header[29] = 255
        header[44] = 1
        struct.pack_into('>I', header, 24, EPOCH_MINUTES + future)
        if index == 4:
            struct.pack_into('>I', header, 0x40, 2)
        if index == 5:
            header[28] = 255
        struct.pack_into('>I', header, 8, zlib.crc32(header[12:]) & 0xffffffff)
        if index == 3:
            header[-1] ^= 1
        fixture = VFF(fixture).add(f'NEWS{index}.BIN', compress_lz10(bytes(header)))
    if run(dol, symbols, fixture) != (0, (1, 6, 6, 5, 1, 1, 5, 1, 6, 0, 5, 1, 1, 1, 0, 0, 0, 0, 0)):
        raise ValueError('Fresh/expired/future fixture failed')
    # Exercise each bounded entry-table check on synthetic, CRC-valid metadata.
    bad_entries = empty
    for index, count_offset in enumerate((0x34, 0x44, 0x4c, 0x54)):
        header = bytearray(512)
        struct.pack_into('>5I', header, 0, 512, len(header), 0, EPOCH_MINUTES, EPOCH_MINUTES + 60)
        header[20], header[28], header[29], header[44] = 49, 1, 255, 1
        struct.pack_into('>I', header, 24, EPOCH_MINUTES)
        struct.pack_into('>II', header, count_offset, 1, 128)
        if index == 0:
            struct.pack_into('>I', header, 136, 1)  # unaligned topic list
        struct.pack_into('>I', header, 8, zlib.crc32(header[12:]) & 0xffffffff)
        bad_entries = VFF(bad_entries).add(f'BAD{index}.BIN', compress_lz10(bytes(header)))
    result = run(dol, symbols, bad_entries)
    if result[0] != 0 or result[1][15:19] != (1, 1, 1, 1):
        raise ValueError('Entry-table invalid fixture failed')
    header = bytearray(512)
    struct.pack_into('>5I', header, 0, 512, len(header), 0, EPOCH_MINUTES, EPOCH_MINUTES + 60)
    header[20], header[28], header[29], header[44] = 49, 1, 255, 1
    header[200:223] = b'PRIVATE_ARTICLE_MARKER!'
    struct.pack_into('>I', header, 24, EPOCH_MINUTES)
    struct.pack_into('>I', header, 8, zlib.crc32(header[12:]) & 0xffffffff)
    snap_fixture = VFF(empty).add('2BIN.00', compress_lz10(bytes(header)))
    response, captured = run(dol, symbols, snap_fixture, snapshot=True)
    if response[0] != 0 or not captured.startswith(b'F 0 512\nS 0 104 ') or b'PRIVATE_ARTICLE_MARKER' in captured:
        raise ValueError(f'Sanitized numeric snapshot fixture failed: rc={response[0]}, captured={len(captured)}, prefix={captured[:30]!r}')
    if any(ch not in b'0123456789FSE \n' for ch in captured):
        raise ValueError('Snapshot contains non-numeric data')
    from analyze_news_structure_report import parse
    with tempfile.TemporaryDirectory(dir=ROOT / 'workspace/private') as temp:
        path = Path(temp) / 'synthetic-structure.txt'
        path.write_bytes(b'KWCE_NEWS_STRUCT_V1\n' + captured + b'DONE\n')
        decoded = parse(path, expected_count=1)[0]
    if decoded[200:223] != bytes(23) or len(decoded) != 512:
        raise ValueError('Snapshot reconstruction leaked article fixture')
    invalid = bytearray(fixture)
    invalid[0] = 0
    if run(dol, symbols, bytes(invalid))[0] != 0xffffffff:
        raise ValueError('Malformed header fixture failed')
    print('PASS: PPC cache diagnostic on empty, fresh, expired, future, CRC, header, entry tables, numeric snapshot and malformed synthetic fixtures')


if __name__ == '__main__':
    main()

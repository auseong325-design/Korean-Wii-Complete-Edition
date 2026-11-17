"""Run News v25's PPC cache validator on numeric-only local diagnostic reports.

The report contains bounded header and table integers, never text or images.
Missing payload bytes are replaced by zero, and the synthetic CRC is refreshed.
No console identifiers or News content are printed or transmitted.
"""
import argparse
import datetime
import json
import struct
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from probe_news_service_locale import Dol, load_library
from unicorn import Uc, UC_ARCH_PPC, UC_MODE_PPC32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
from unicorn.ppc_const import (UC_PPC_REG_1, UC_PPC_REG_3, UC_PPC_REG_4,
                               UC_PPC_REG_5, UC_PPC_REG_6, UC_PPC_REG_LR, UC_PPC_REG_PC)


def parse(path, expected_count=24):
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Structure report exceeds limit')
    with path.open('rt', encoding='ascii') as f:
        if f.readline().strip() != 'KWCE_NEWS_STRUCT_V1':
            raise ValueError('Unexpected report format')
        files = {}; current = None; done = False; header_seen = False
        for line in f:
            parts = line.split()
            if not parts:
                raise ValueError('Empty report row')
            if parts[0] == 'F' and len(parts) == 3 and current is None:
                hour, size = (int(x) for x in parts[1:])
                if hour in files or not 0 <= hour < 24 or not 104 <= size <= 8 * 1024 * 1024:
                    raise ValueError('Invalid file header')
                current = (hour, bytearray(size)); header_seen = False
            elif parts[0] == 'S' and len(parts) >= 3 and current is not None:
                off, length = (int(x) for x in parts[1:3]); data = current[1]
                if off < 0 or length < 0 or (length % 4) or off + length > len(data) or len(parts) != 3 + length // 4:
                    raise ValueError('Invalid metadata segment')
                for i, word in enumerate(parts[3:]):
                    value = int(word)
                    if not 0 <= value <= 0xffffffff:
                        raise ValueError('Metadata integer out of range')
                    struct.pack_into('>I', data, off + 4 * i, value)
                if off == 0 and length == 104: header_seen = True
            elif parts == ['E'] and current is not None and header_seen:
                hour, data = current
                if struct.unpack_from('>I', data, 4)[0] != len(data):
                    raise ValueError('Payload size mismatch')
                struct.pack_into('>I', data, 8, zlib.crc32(data[12:]) & 0xffffffff)
                files[hour] = bytes(data); current = None
            elif parts == ['DONE'] and current is None:
                done = True; break
            else:
                raise ValueError('Unexpected report row')
        if not done or len(files) != expected_count or f.read().strip():
            raise ValueError('Incomplete report')
    return files


def validate(files, hour_offset, now=None):
    title = load_library().title.Title()
    title.load_wad((ROOT / 'workspace/channels/news/build-v25/news-ko-personal.wad').read_bytes())
    dol = Dol(title.get_content_by_index(1))
    u = Uc(UC_ARCH_PPC, UC_MODE_PPC32 | UC_MODE_BIG_ENDIAN)
    u.mem_map(0x80000000, 0x01000000); u.mem_map(0x81000000, 0x03000000)
    for _, offset, address, size in dol.sections:
        u.mem_write(address, dol.data[offset:offset + size])
    ptrs, sizes, out, cursor = 0x81000000, 0x81001000, 0x81002000, 0x81200000
    for index in range(24):
        data = files[index]
        if cursor + len(data) >= 0x83d00000: raise ValueError('Fixture exceeds mapped memory')
        u.mem_write(cursor, data);u.mem_write(ptrs + 4 * index, struct.pack('>I', cursor))
        u.mem_write(sizes + 4 * index, struct.pack('>I', len(data)));cursor = (cursor + len(data) + 31) & ~31
    for reg, value in ((UC_PPC_REG_1, 0x83f00000), (UC_PPC_REG_3, ptrs), (UC_PPC_REG_4, sizes),
                       (UC_PPC_REG_5, out), (UC_PPC_REG_6, out + 4), (UC_PPC_REG_LR, 0x81100000)):
        u.reg_write(reg, value)
    reference = time.time() if now is None else now
    minutes = int((reference - 946684800) // 60) + 60 * hour_offset
    def hook(uc, address, _size, _user):
        if address == 0x80044f08:
            uc.reg_write(UC_PPC_REG_3, minutes)
        elif address == 0x8007621c:
            pointer, size = uc.reg_read(UC_PPC_REG_3), uc.reg_read(UC_PPC_REG_4)
            uc.reg_write(UC_PPC_REG_3, zlib.crc32(uc.mem_read(pointer, size)) & 0xffffffff)
        elif address == 0x80106e9c:
            uc.reg_write(UC_PPC_REG_3, 0)
        elif address == 0x80076138:
            pointer = uc.reg_read(UC_PPC_REG_3)
            hour = (datetime.datetime.fromtimestamp(reference, datetime.timezone.utc).hour + hour_offset) % 24
            uc.mem_write(pointer + 8, struct.pack('>I', hour));uc.reg_write(UC_PPC_REG_3, 1)
        else:
            return
        uc.reg_write(UC_PPC_REG_PC, uc.reg_read(UC_PPC_REG_LR))
    u.hook_add(UC_HOOK_CODE, hook)
    u.emu_start(0x8000afc8, 0x81100000, count=10000000)
    if u.reg_read(UC_PPC_REG_PC) != 0x81100000: raise ValueError('Validator instruction limit')
    result = u.reg_read(UC_PPC_REG_3)
    if result >= 0x80000000: result -= 0x100000000
    return {'result': result, 'retry_hour_count': int.from_bytes(u.mem_read(out + 4, 4), 'big').bit_count()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('report', type=Path)
    parser.add_argument('--paired-network-report', type=Path,
                        help='Use paired local-clock report for capture-time scenarios')
    args = parser.parse_args();files = parse(args.report)
    if args.paired_network_report:
        from summarize_news_network_report import summarize
        summary = summarize(args.paired_network_report, now=0)
        if not summary.get('complete') or 'wii_clock_vs_pc_read_minutes' not in summary:
            raise ValueError('Incomplete paired clock report')
        # For fixed-offset tests, use the raw report clock without printing it.
        lines = args.paired_network_report.read_text(encoding='ascii').splitlines()
        values = [line.split('=', 1)[1] for line in lines if line.startswith('clock_unix=')]
        if len(values) != 1: raise ValueError('Missing or duplicated report clock')
        clock = int(values[0]);now = clock - 9 * 3600
        label = 'report_clock_minus_9h_assumed_utc'
    else:
        now = time.time();label = 'pc_clock_at_analysis'
    print(json.dumps({'files': len(files), 'clock_scenario': label,
                      'utc': validate(files, 0, now), 'utc_plus_9': validate(files, 9, now),
                      'report_contains_payload': False, 'actual_channel_runtime': False}))

if __name__ == '__main__': main()

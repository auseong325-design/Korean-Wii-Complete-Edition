"""Summarize a preserved channel WAD's contents (types, U8 file lists, text counts).

Local-only analysis: prints resource names, sizes and counts, never text
bodies, keys or tickets. Nested U8/LZ/Yaz0 archives are expanded one level.
"""
import argparse
import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library, ChannelArchive  # noqa: E402
from kwce.votes_resources import decode_yaz0  # noqa: E402
from kwce.wiiroom_formats import decompress_lz11  # noqa: E402


def unwrap(raw):
    """Return (label, payload) after removing one compression layer."""
    if raw[:4] == b'Yaz0':
        return 'Yaz0', decode_yaz0(raw)
    if raw[:4] == b'LZ77' and raw[4:5] == b'\x11':
        return 'LZ77+11', decompress_lz11(raw[4:])
    if raw[:1] == b'\x11' and len(raw) > 8:
        try:
            return 'LZ11', decompress_lz11(raw)
        except ValueError:
            pass
    if raw[:1] == b'\x10' and len(raw) > 8:
        try:
            from kwce.channel_lz import decompress_lz10
            return 'LZ10', decompress_lz10(raw)
        except Exception:
            pass
    return '', raw


def kind(raw):
    if raw[0x40:0x44] == b'IMET' or raw[0x80:0x84] == b'IMET':
        return 'IMET'
    if raw[:4] == bytes.fromhex('55aa382d'):
        return 'U8'
    for magic in (b'MESGbmg1', b'RLYT', b'RLAN', b'TPL\0', b'RFNT', b'RFNA', b'RSAR', b'RSTM', b'THP\0', b'BNS '):
        if raw.startswith(magic):
            return magic.decode('ascii', 'replace').strip('\0')
    if raw[:4] == bytes.fromhex('0020af30'):
        return 'TPL'
    if raw[:4] in (b'ttcf', b'\0\1\0\0', b'OTTO'):
        return 'font'
    if raw[:5] in (b'<?xml', b'<html', b'<HTML', b'<!DOC'):
        return 'html/xml'
    if len(raw) > 0x100 and raw[0:4] == b'\0\0\1\0':
        return 'DOL'
    return 'raw'


def wide_strings(raw, minimum=3):
    """Count aligned UTF-16BE runs containing kana/kanji/latin letters."""
    count = 0
    for match in re.finditer(rb'(?:(?:[\x00][\x20-\x7e])|(?:[\x30][\x00-\xff])|(?:[\x4e-\x9f][\x00-\xff])|(?:\xff[\x01-\x5e]))' + b'{%d,}' % minimum + rb'\x00\x00', raw):
        if match.start() % 2 == 0 and re.search(rb'[\x30\x4e-\x9f]', match.group()[::2]):
            count += 1
    return count


def describe_archive(archive, indent, depth):
    by_ext = collections.Counter()
    for name in archive.files:
        raw = archive.get(name)
        label, payload = unwrap(raw)
        k = kind(payload)
        by_ext[(Path(name).suffix.lower() or '(none)', k)] += 1
        if k in ('MESGbmg1',) or name.lower().endswith(('.bmg', '.msbt', '.txt', '.html', '.htm', '.xml', '.csv')):
            print(f'{indent}{name} {len(raw)} {label} {k}')
        elif k == 'U8' and depth < 2:
            nested = ChannelArchive(payload)
            print(f'{indent}{name} {len(raw)} {label} U8 files={len(nested.files)}')
            describe_archive(nested, indent + '    ', depth + 1)
    print(indent + 'summary: ' + ', '.join(f'{e}/{k}={n}' for (e, k), n in sorted(by_ext.items())))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('wad')
    args = parser.parse_args()
    lib = load_library()
    title = lib.title.Title()
    title.load_wad(Path(args.wad).read_bytes())
    print('title', title.tmd.title_id, 'v', title.tmd.title_version, 'boot', title.tmd.boot_index, 'ios', title.tmd.ios_tid[-2:], 'region', title.tmd.region)
    for index in range(title.tmd.num_contents):
        raw = title.get_content_by_index(index)
        label, payload = unwrap(raw)
        k = kind(payload)
        extra = ''
        if k in ('DOL', 'raw') and len(payload) > 4096:
            extra = f' wide_jp_strings~{wide_strings(payload)}'
        print(f'[{index}] cid={title.tmd.content_records[index].content_id:08x} size={len(raw)} {label} {k}{extra}')
        if k == 'U8':
            describe_archive(ChannelArchive(payload), '    ', 0)


if __name__ == '__main__':
    main()

"""Pure-Python BSDIFF40 applier for WiiLink patcher files (bsdiff4 format).

The WiiLink patcher applies these patches with the bsdiff4 package; this
module implements the same public BSDIFF40 layout with the standard library
so no extra dependency is installed. Only bounded, well-formed patches are
accepted: every control step must stay inside the declared new size and the
three bzip2 streams must be fully consumed.
"""
import bz2
import struct

MAGIC = b'BSDIFF40'
LIMIT = 256 * 1024 * 1024


def _offtin(raw, at):
    value = int.from_bytes(raw[at:at + 8], 'little')
    return -(value & ~(1 << 63)) if value >> 63 else value


def apply(old, patch):
    old = bytes(old)
    if len(patch) < 32 or patch[:8] != MAGIC:
        raise ValueError('Not a BSDIFF40 patch')
    control_size, diff_size, new_size = (_offtin(patch, i) for i in (8, 16, 24))
    if min(control_size, diff_size, new_size) < 0 or new_size > LIMIT or 32 + control_size + diff_size > len(patch):
        raise ValueError('BSDIFF40 header bounds')
    control = bz2.decompress(patch[32:32 + control_size])
    diff = bz2.decompress(patch[32 + control_size:32 + control_size + diff_size])
    extra = bz2.decompress(patch[32 + control_size + diff_size:])
    if len(control) % 24:
        raise ValueError('BSDIFF40 control block size')
    new = bytearray(new_size)
    new_pos = old_pos = diff_pos = extra_pos = 0
    for at in range(0, len(control), 24):
        add, copy, seek = (_offtin(control, at + i) for i in (0, 8, 16))
        if add < 0 or copy < 0 or new_pos + add + copy > new_size or diff_pos + add > len(diff) or extra_pos + copy > len(extra):
            raise ValueError('BSDIFF40 control step bounds')
        segment = diff[diff_pos:diff_pos + add]
        lo, hi = max(old_pos, 0), min(old_pos + add, len(old))
        if lo < hi:
            # Bytes without an old counterpart are taken from the diff unchanged.
            source = old[lo:hi]
            start = lo - old_pos
            mixed = bytes((a + b) & 255 for a, b in zip(segment[start:start + len(source)], source))
            segment = segment[:start] + mixed + segment[start + len(source):]
        new[new_pos:new_pos + add] = segment
        new_pos += add
        old_pos += add
        diff_pos += add
        new[new_pos:new_pos + copy] = extra[extra_pos:extra_pos + copy]
        new_pos += copy
        extra_pos += copy
        old_pos += seek
    if new_pos != new_size or diff_pos != len(diff) or extra_pos != len(extra):
        raise ValueError('BSDIFF40 streams not fully consumed')
    return bytes(new)


def describe(patch):
    """Header summary only; safe to print."""
    control_size, diff_size, new_size = (_offtin(patch, i) for i in (8, 16, 24))
    return dict(magic=patch[:8].decode('ascii', 'replace'), control=control_size, diff=diff_size, new_size=new_size)

"""Hangul for the Internet Channel software keyboard (revision 6+).

The keyboard builds an nw4r ArchiveFont from /cnt/00000008/wbf1.brfna and loads
only the glyph group "wii_name" (executable 0x80054dd4: SCGetProductArea != JPN;
the Japanese channel loads every group). In the console's 43K Korean wbf1 that
group holds sheets 38 and 49-55, while the 2,350 KS X 1001 Hangul syllables lie
on sheets 38-48 (group "ksx_level_1"). ArchiveFont treats a glyph on an unloaded
sheet as missing and draws the alternate character, so Korean labels showed '?'.

keyboard_font() sets the "wii_name" sheet bits of the group named in the config
inside the GLGR block. Sheets, widths, code maps and every other byte stay as
they are (the file keeps its size); the loaded sheet count grows by 10 (64 KiB
each once expanded), still far below the Japanese channel's 56 sheets.
"""
import hashlib
import struct

from .channels import ChannelArchive

NOT_FOUND = 0xffff


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def glyph_groups(rfna):
    """Parse the GLGR block: group names and the file offset of each sheet bit set."""
    if rfna[:6] != b'RFNA\xfe\xff' or rfna[16:20] != b'GLGR':
        raise ValueError('Expected an RFNA font with a GLGR block')
    if struct.unpack_from('>I', rfna, 8)[0] != len(rfna):
        raise ValueError('RFNA size field differs')
    glgr_size = struct.unpack_from('>I', rfna, 20)[0]
    sheet_size, per_sheet, nset, nsheet, ncwdh, ncmap = struct.unpack_from('>IHHHHH', rfna, 24)
    offsets = struct.unpack_from(f'>{nset}H', rfna, 38)
    names = [rfna[o:rfna.index(b'\0', o)].decode('ascii') for o in offsets]
    align = (14 + 2 * nset + 3) // 4 * 4
    flags = 24 + align + 4 * (nsheet + ncwdh + ncmap)
    words = (nsheet + 31) // 32
    if flags + 4 * words * nset > 16 + glgr_size or min(offsets) < flags:
        raise ValueError('GLGR layout differs')
    return dict(names=names, sheets=nsheet, per_sheet=per_sheet, sheet_size=sheet_size, flags=flags, words=words,
                finf=16 + glgr_size)


def group_sheets(rfna, name):
    g = glyph_groups(rfna)
    at = g['flags'] + 4 * g['words'] * g['names'].index(name)
    bits = struct.unpack_from(f'>{g["words"]}I', rfna, at)
    return [s for s in range(g['sheets']) if bits[s // 32] >> (31 - s % 32) & 1]


def with_group_sheets(rfna, name, sheets):
    """Return the font with exactly `sheets` flagged for group `name` (MSB-first bits)."""
    g = glyph_groups(rfna)
    if any(not 0 <= s < g['sheets'] for s in sheets):
        raise ValueError('Sheet index outside the font')
    words = [0] * g['words']
    for s in sheets:
        words[s // 32] |= 1 << (31 - s % 32)
    out = bytearray(rfna)
    at = g['flags'] + 4 * g['words'] * g['names'].index(name)
    struct.pack_into(f'>{g["words"]}I', out, at, *words)
    return bytes(out), (at, at + 4 * g['words'])


def find_glyph(rfna, code):
    """ResFontBase::FindGlyphIndex: the first code map whose range holds `code` decides."""
    finf = glyph_groups(rfna)['finf']
    if rfna[finf:finf + 4] != b'FINF':
        raise ValueError('FINF block expected after GLGR')
    ptr = struct.unpack_from('>I', rfna, finf + 8 + 16)[0]
    seen = 0
    while ptr:
        seen += 1
        if seen > 64 or rfna[ptr - 8:ptr - 4] != b'CMAP':
            raise ValueError('Code map chain differs')
        lo, hi, method = struct.unpack_from('>HHH', rfna, ptr)
        nxt = struct.unpack_from('>I', rfna, ptr + 8)[0]
        if lo <= code <= hi:
            if method == 0:
                return struct.unpack_from('>H', rfna, ptr + 12)[0] + code - lo
            if method == 1:
                return struct.unpack_from('>H', rfna, ptr + 12 + 2 * (code - lo))[0]
            if method == 2:
                n = struct.unpack_from('>H', rfna, ptr + 12)[0]
                a, b = 0, n - 1
                while a <= b:
                    m = (a + b) // 2
                    c, glyph = struct.unpack_from('>HH', rfna, ptr + 14 + 4 * m)
                    if c == code:
                        return glyph
                    a, b = (m + 1, b) if c < code else (a, m - 1)
            return NOT_FOUND
        ptr = nxt
    return NOT_FOUND


def missing_in_group(rfna, group, texts):
    """Characters of `texts` that the keyboard would draw as the alternate character."""
    g = glyph_groups(rfna)
    loaded = set(group_sheets(rfna, group))
    out = set()
    for text in texts:
        for c in text:
            if ord(c) < 0x20 or c == '\n':
                continue
            glyph = find_glyph(rfna, ord(c))
            if glyph == NOT_FOUND or glyph // g['per_sheet'] not in loaded:
                out.add(c)
    return sorted(out)


def keyboard_font(content, cfg, texts):
    """content: content-8 U8 archive (wbf1/wbf2); cfg: v6 'keyboard_font'; texts: every keyboard string."""
    archive = ChannelArchive(content)
    name, group, extra = cfg['file'], cfg['group'], cfg['add_sheets_of']
    rfna = archive.get(name)
    before = group_sheets(rfna, group)
    missing_before = missing_in_group(rfna, group, texts)
    sheets = sorted(set(before) | set(group_sheets(rfna, extra)))
    new, (lo, hi) = with_group_sheets(rfna, group, sheets)
    diff = [i for i in range(len(rfna)) if rfna[i] != new[i]]
    if not diff or diff[0] < lo or diff[-1] >= hi:
        raise ValueError('Glyph group change escaped the group bit set')
    for other in glyph_groups(new)['names']:
        if other != group and group_sheets(new, other) != group_sheets(rfna, other):
            raise ValueError('Another glyph group changed')
    missing = missing_in_group(new, group, texts)
    if missing:
        raise ValueError(f'Keyboard glyphs still on unloaded sheets: {missing}')
    result = archive.replace(name, new)
    if ChannelArchive(result).get('wbf2.brfna') != archive.get('wbf2.brfna'):
        raise ValueError('wbf2 changed')
    g = glyph_groups(new)
    return result, dict(file=name, group=group, added_from=extra, sheets_before=before, sheets_after=sheets,
                        added_sheets=len(sheets) - len(before), expanded_bytes_added=(len(sheets) - len(before)) * g['sheet_size'],
                        bytes_changed=len(diff), font_sha256=[sha256(rfna), sha256(new)],
                        texts=len(texts), characters_missing_before=len(missing_before), characters_missing_after=0)

"""Append Hangul glyphs to an I4 RFNT with a chosen glyph size and advance.

kwce.channel_font.extend_font renders new glyphs at the full cell width.
The Kirby TV dialog font has 38x35 cells but a 29-pixel nominal width, so
full-cell Hangul would be about twice as wide as its Latin capitals. This
variant keeps the same sheet geometry and block rebuilding but renders the
syllables at `px` and advances by `advance`, matching the Latin proportions.
Original sheets, glyph indexes and widths are preserved.
"""
import math
import struct
from .channels import load_library
from .channel_font import font_data


def extend_font_sized(data, characters, ttf, px, advance, weight=500):
    load_library()
    from PIL import Image, ImageDraw, ImageFont
    blocks, mapping, widths = font_data(data)
    _, tglp = blocks[b'TGLP']
    cw, ch, baseline, _ = tglp[8:12]
    sheet_size = struct.unpack_from('>I', tglp, 12)[0]
    sheets, fmt, cols, rows, sw, sh = struct.unpack_from('>6H', tglp, 16)
    pointer = struct.unpack_from('>I', tglp, 28)[0]
    if fmt != 0 or sheet_size != sw * sh // 2 or sw % 8 or sh % 8:
        raise ValueError('Only tiled I4 fonts are supported')
    if not 0 < px <= ch or not 0 < advance <= cw:
        raise ValueError('Glyph size outside the cell')
    missing = sorted({ord(c) for c in characters if ord(c) >= 32 and ord(c) not in mapping})
    if not missing:
        return data, dict(added_glyphs=0)
    per_sheet = cols * rows
    first = sheets * per_sheet
    if first + len(missing) >= 65535:
        raise ValueError('Font glyph capacity')
    font = ImageFont.truetype(str(ttf), px)
    font.set_variation_by_axes([weight])
    extra = []
    for page in range(math.ceil(len(missing) / per_sheet)):
        image = Image.new('L', (sw, sh))
        for item in range(per_sheet):
            n = page * per_sheet + item
            if n >= len(missing):
                break
            cell = Image.new('L', (cw, ch))
            ImageDraw.Draw(cell).text((0, baseline), chr(missing[n]), font=font, fill=255, anchor='ls')
            image.paste(cell, ((item % cols) * (cw + 1), (item // cols) * (ch + 1)))
            mapping[missing[n]] = first + n
            widths[first + n] = bytes([0, min(advance, 255), min(advance + 1, 255)])
        tiled = bytearray()
        for by in range(0, sh, 8):
            for bx in range(0, sw, 8):
                for y in range(8):
                    for x in range(0, 8, 2):
                        tiled.append((image.getpixel((bx + x, by + y)) >> 4) << 4 | (image.getpixel((bx + x + 1, by + y)) >> 4))
        extra.append(bytes(tiled))
    finf = bytearray(blocks[b'FINF'][1])
    tg = bytearray(tglp[:32])
    tg.extend(bytes(-(16 + len(finf) + len(tg)) % 32))
    sheet_offset = 16 + len(finf) + len(tg)
    tg.extend(data[pointer:pointer + sheet_size * sheets])
    tg.extend(b''.join(extra))
    struct.pack_into('>I', tg, 4, len(tg))
    struct.pack_into('>H', tg, 16, sheets + len(extra))
    struct.pack_into('>I', tg, 28, sheet_offset)
    count = first + len(missing)
    wd = bytearray(b'CWDH' + bytes(12))
    struct.pack_into('>HHI', wd, 8, 0, count - 1, 0)
    wd.extend(b''.join(widths.get(i, finf[12:15]) for i in range(count)))
    wd.extend(bytes(-len(wd) % 4))
    struct.pack_into('>I', wd, 4, len(wd))
    cm = bytearray(b'CMAP' + bytes(16))
    struct.pack_into('>HHHHI', cm, 8, min(mapping), max(mapping), 2, 0, 0)
    cm.extend(struct.pack('>H', len(mapping)))
    for code, glyph in sorted(mapping.items()):
        cm.extend(struct.pack('>HH', code, glyph))
    cm.extend(bytes(-len(cm) % 4))
    struct.pack_into('>I', cm, 4, len(cm))
    struct.pack_into('>III', finf, 16, 16 + len(finf) + 8, 16 + len(finf) + len(tg) + 8, 16 + len(finf) + len(tg) + len(wd) + 8)
    result = bytearray(data[:16] + finf + tg + wd + cm)
    struct.pack_into('>I', result, 8, len(result))
    struct.pack_into('>H', result, 14, 4)
    _, checked, checked_widths = font_data(bytes(result))
    if any(checked[c] != g for c, g in mapping.items()):
        raise ValueError('Font mapping verification failed')
    if any(checked_widths[g] != widths[g] for g in range(count) if g in widths):
        raise ValueError('Font width verification failed')
    return bytes(result), dict(added_glyphs=len(missing), original_sheet_bytes_preserved=True, sheets_before=sheets,
                               sheets_after=sheets + len(extra), glyph_px=px, advance=advance, weight=weight)

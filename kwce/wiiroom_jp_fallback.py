"""Append Japanese fallback glyphs (JIS level 1 kanji) to the Room list fonts.

The Room's list/news text is WiiLink-supplied: with the title's resource slot
pinned to Japanese (every build >= v4), the server serves Japanese `News`,
category and room-list rows. Our content[9] fonts are the console's 43K Korean
shared RFNA (wbf1/wbf2): full Hangul + kana, but ZERO kanji, so every kanji in
the supplied text falls to the alter glyph and shows as a '?' box on hardware.

This restores kanji coverage by appending the JIS level 1 set, rendered from the
channel's OWN original Japanese wbf font (public WiiLink English archive), each
glyph resampled into the Korean cell and re-tiled/CX-compressed into new sheets.
It keeps every original glyph byte-for-byte and prepends a kanji-only CMAP
(0x4e00-0x9f8d) that cannot shadow Hangul (0xAC00-0xD7A3) or the kana/ASCII maps
(the Korean font maps nothing in 0x4e00-0x9f8d, so no in-range lookup regresses).

Memory: the font is loaded whole into the fixed `FONT` heap (0x46c650 =
4,638,288 B). ArchiveFont sizes the buffer from the loaded sheets, so the added
sheets must keep the total within that heap. The original JP font shipped 70
such sheets, so 70 is the proven-safe ceiling; we never exceed it and trim the
highest codepoints first if a font would. Fail-safe: on any overflow or render
gap we keep that font unchanged and record why.
"""
import math
import struct

from .channel_font import font_data
from .channels import load_library
from .korean_font_narrow import _tile_i4
from . import photoprints_cx
# Read-only reuse of the reviewed RFNA structure/lookup helpers.
from .photoprints_font import _parse_rfna, find_glyph, check_rfna, ExactCellRenderer

HEAP_FONT = 0x46c650            # FONT heap created at 0x800de044 (lis 0x47; addi -0x39b0)
SAFE_SHEETS = 70                # JP original wbf1 ships 70 sheets into the same heap
KANJI_LO, KANJI_HI = 0x4e00, 0x9fff
HANGUL_LO, HANGUL_HI = 0xac00, 0xd7a3


def jis_level1_kanji(source_rfna):
    """Codes in the source font's `jis_level_1` glyph group that are CJK kanji."""
    P = _parse_rfna(source_rfna)
    names = []
    for o in P['names']:
        e = source_rfna.index(b'\0', o); names.append(source_rfna[o:e].decode())
    if 'jis_level_1' not in names:
        raise ValueError('Source font has no jis_level_1 group')
    T = P['tglp'][2]
    cols, rows = struct.unpack_from('>2H', T, 12)
    per = cols * rows
    idx = names.index('jis_level_1')
    sheets_in = {s for s in range(P['nsheet']) if P['useS'][idx][s]}
    _, mapping, _ = font_data(b'RFNT' + source_rfna[4:])
    return {c for c, g in mapping.items()
            if KANJI_LO <= c <= KANJI_HI and (g // per) in sheets_in}


def _require_estimate(nsheet, sheet_size):
    """ArchiveFont::GetRequireBufferSize for the whole-font ('all') group.

    Validated against the shipped fonts: JP wbf1 (70 sheets) -> 4,588,288 which
    fits the 4,638,288 heap; KO v50 (56) -> 3,670,752. The decompressed sheet
    sum dominates; header and block terms are the small fixed remainder.
    """
    a4 = lambda x: (x + 3) & ~3
    a32 = lambda x: (x + 31) & ~31
    header = a32(a4(2 * nsheet) + 0x4f)
    blocks = max(0x220, a4(2 * nsheet))
    return header + blocks + a4(nsheet * sheet_size)


def append_japanese(rfna, source_rfna, codes, heap=HEAP_FONT):
    """Append `codes` (rendered from source_rfna) to rfna. Returns (rfna, record).

    Fail-safe: trims the highest codepoints until the font fits `heap` and the
    proven 70-sheet ceiling; every original glyph lookup is re-verified unchanged.
    """
    load_library()
    from PIL import Image
    P = _parse_rfna(rfna)
    T = P['tglp'][2]
    cw, ch, baseline = T[0], T[1], T[2]
    nsheet = P['nsheet']
    fmt, cols, rows, sw, sh = struct.unpack_from('>5H', T, 10)
    if fmt != 0x8000 or P['sheet_size'] != sw * sh // 2:
        raise ValueError('Only CX Huffman I4 RFNA supported')
    _, mapping, _ = font_data(b'RFNT' + rfna[4:])
    source_map = font_data(b'RFNT' + source_rfna[4:])[1]
    per = cols * rows

    # Only codes the source can draw, the target lacks, inside the kanji band
    # (disjoint from Hangul and from every map the Korean font already serves).
    want = sorted(c for c in codes
                  if KANJI_LO <= c <= KANJI_HI and c in source_map and c not in mapping)
    if any(HANGUL_LO <= c <= HANGUL_HI for c in want):
        raise ValueError('Fallback code inside Hangul range')

    # Fail-safe budget: cap total sheets so the loaded font fits the FONT heap
    # and never exceeds the original Japanese font's proven sheet count.
    max_total = SAFE_SHEETS
    while max_total > nsheet and _require_estimate(max_total, P['sheet_size']) > heap:
        max_total -= 1
    capacity = max(0, (max_total - nsheet) * per)
    requested = len(want)
    dropped = want[capacity:]
    want = want[:capacity]
    if not want:
        return rfna, dict(added_glyphs=0, requested=requested, dropped=len(dropped),
                          reason='no heap budget for fallback glyphs', font_unchanged=True,
                          sheets=nsheet, heap=heap)

    renderer = ExactCellRenderer(source_rfna)
    sys_adv = max(renderer.widths[renderer.mapping[c]][2] for c in want)
    f = cw / sys_adv
    first = nsheet * per
    streams, widths, layouts = [], [], []
    for page in range(math.ceil(len(want) / per)):
        image = Image.new('L', (sw, sh))
        for item in range(per):
            n = page * per + item
            if n >= len(want):
                break
            cell, left, gw, adv = renderer.glyph(want[n])
            x = (item % cols) * (cw + 1); y = (item // cols) * (ch + 1)
            left_n = round(left * f); advance = min(cw, round(adv * f))
            tw = max(1, min(round(gw * f), cw - max(left_n, 0), max(1, advance - left_n)))
            th = max(1, min(ch, round(renderer.ch * f)))
            off_y = max(0, min(ch - th, round(baseline - renderer.baseline * f)))
            window = Image.new('L', (cw, ch))
            window.paste(cell.resize((tw, th), Image.LANCZOS), (0, off_y))
            image.paste(window, (x + 1, y + 1))
            widths.append(bytes([left_n & 0xff, tw, advance]))
        packed, layout = photoprints_cx.compress(_tile_i4(image.tobytes(), sw, sh))
        packed += bytes(-len(packed) % 4)
        layouts.append(layout)
        streams.append(packed)

    bl = P['blocks']
    cwb = [b for b in bl if b[0] == b'CWDH']
    cmb = [b for b in bl if b[0] == b'CMAP']
    cw_data = struct.pack('>HHI', first, first + len(want) - 1, 0) + b''.join(widths)
    cw_block = bytearray(b'CWDH' + struct.pack('>I', 0) + cw_data)
    cw_block.extend(bytes(-len(cw_block) % 4)); struct.pack_into('>I', cw_block, 4, len(cw_block))
    # Sparse (method 2) kanji CMAP, prepended so it resolves before the Korean
    # font's 0000-ffff scan map; its [lo,hi] stays inside the empty kanji band.
    cm_data = (struct.pack('>HHHHI', want[0], want[-1], 2, 0, 0)
               + struct.pack('>H', len(want))
               + b''.join(struct.pack('>HH', c, first + i) for i, c in enumerate(want)))
    cm_block = bytearray(b'CMAP' + struct.pack('>I', 0) + cm_data)
    cm_block.extend(bytes(-len(cm_block) % 4)); struct.pack_into('>I', cm_block, 4, len(cm_block))

    useS = [u + [1] * len(streams) for u in P['useS']]
    useC = [u + [1] for u in P['useC']]
    useM = [[1] + u for u in P['useM']]

    def pack(bitlist):
        out = [0] * ((len(bitlist) + 31) // 32)
        for i, b in enumerate(bitlist):
            if b:
                out[i // 32] |= 1 << (31 - i % 32)
        return out

    nset = P['nset']
    sizeS = [len(s) for s in P['streams']] + [len(s) for s in streams]
    sizeC = [b[2] for b in cwb] + [len(cw_block)]
    sizeM = [len(cm_block)] + [b[2] for b in cmb]
    A = (14 + 2 * nset + 3) & ~3
    head = struct.pack('>IHHHHH', P['sheet_size'], P['gps'], nset,
                       nsheet + len(streams), len(sizeC), len(sizeM))
    arrays = b''.join(struct.pack('>I', x) for x in sizeS + sizeC + sizeM)
    use = (b''.join(struct.pack('>I', w) for u in useS for w in pack(u))
           + b''.join(struct.pack('>I', w) for u in useC for w in pack(u))
           + b''.join(struct.pack('>I', w) for u in useM for w in pack(u)))
    names_rel = 16 + 8 + A + len(arrays) + len(use)
    base = min(P['names'])
    newnames = [o - base + names_rel for o in P['names']]
    if max(newnames) > 0xffff:
        raise ValueError('GLGR name offsets exceed u16')
    gdata = bytearray(head + struct.pack(f'>{nset}H', *newnames))
    gdata.extend(bytes(A - len(gdata))); gdata += arrays + use + P['name_blob']
    glgr = b'GLGR' + struct.pack('>I', 8 + len(gdata)) + bytes(gdata)
    if len(glgr) % 4:
        raise ValueError('GLGR alignment')

    tp, tsz = P['tglp'][0], P['tglp'][1]
    finf_start = 16 + len(glgr)
    finf = bytearray(rfna[bl[1][1]:bl[1][1] + bl[1][2]])
    tglp_start = finf_start + len(finf)
    image_at = (tglp_start + 32 + 31) & ~31
    tglp = bytearray(rfna[tp:tp + 32]); tglp.extend(bytes(image_at - tglp_start - 32))
    for s in P['streams'] + streams:
        tglp += struct.pack('>I', len(s)) + s
    struct.pack_into('>H', tglp, 16, nsheet + len(streams))
    struct.pack_into('>I', tglp, 28, image_at); struct.pack_into('>I', tglp, 4, len(tglp))
    cw_start = tglp_start + len(tglp)
    old_cw = [bytearray(rfna[p:p + s]) for _, p, s in cwb]
    pos = cw_start; cw_starts = []
    for b in old_cw + [cw_block]:
        cw_starts.append(pos); pos += len(b)
    cm_all = [cm_block] + [bytearray(rfna[p:p + s]) for _, p, s in cmb]
    cm_starts = []
    for b in cm_all:
        cm_starts.append(pos); pos += len(b)
    for i, b in enumerate(old_cw + [cw_block]):
        struct.pack_into('>I', b, 12, cw_starts[i + 1] + 8 if i + 1 < len(cw_starts) else 0)
    for i, b in enumerate(cm_all):
        struct.pack_into('>I', b, 16, cm_starts[i + 1] + 8 if i + 1 < len(cm_starts) else 0)
    struct.pack_into('>III', finf, 16, tglp_start + 8, cw_starts[0] + 8, cm_starts[0] + 8)
    body = (glgr + bytes(finf) + bytes(tglp)
            + b''.join(bytes(b) for b in old_cw) + bytes(cw_block)
            + b''.join(bytes(b) for b in cm_all))
    out = bytearray(rfna[:16] + body)
    struct.pack_into('>I', out, 8, len(out)); struct.pack_into('>H', out, 14, len(bl) + 2)
    out = bytes(out)

    rec = check_rfna(out)
    for i, c in enumerate(want):
        if find_glyph(out, c) != first + i:
            raise ValueError('Kanji chain lookup failed')
    # Regression guard: EVERY glyph the original font resolved still resolves the
    # same (the prepended kanji map must shadow nothing the Korean UI relies on).
    for c in mapping:
        if find_glyph(out, c) != find_glyph(rfna, c):
            raise ValueError('Original glyph lookup changed')
    used_sheets = nsheet + len(streams)
    record = dict(added_glyphs=len(want), requested=requested, dropped=len(dropped),
                  dropped_codepoints=[hex(c) for c in dropped[:8]],
                  sheets_before=nsheet, sheets_after=used_sheets,
                  cmap_range=[hex(want[0]), hex(want[-1])], cmap_method=2,
                  source='channel original Japanese wbf (JIS level 1)',
                  cell=[cw, ch], scale=round(f, 4),
                  heap=heap, require_estimate=_require_estimate(used_sheets, P['sheet_size']),
                  heap_headroom=heap - _require_estimate(used_sheets, P['sheet_size']),
                  cx_layout=dict(bfs=layouts.count('bfs'), deadline=layouts.count('deadline')),
                  **rec)
    return out, record


def korean_list_fallback(content9_bytes, source_content9_bytes):
    """Apply the kanji fallback to wbf1/wbf2 inside content[9]. Returns (bytes, record)."""
    from .channels import ChannelArchive
    target = ChannelArchive(content9_bytes)
    source = ChannelArchive(source_content9_bytes)
    if set(target.files) != {'wbf1.brfna', 'wbf2.brfna'}:
        raise ValueError('Unexpected content[9] fonts')
    fonts = {}
    data = content9_bytes
    for name in ('wbf1.brfna', 'wbf2.brfna'):
        codes = jis_level1_kanji(source.get(name))
        new_font, rec = append_japanese(target.get(name), source.get(name), codes)
        data = ChannelArchive(data).replace(name, new_font)
        fonts[name] = rec
    return ChannelArchive(data).compact(), dict(fonts=fonts,
        note='kana already present in the Korean shared font; JIS level 1 kanji added as fallback')

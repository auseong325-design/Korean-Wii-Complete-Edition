"""Internet Channel Wii Menu title in a heavier, larger Korean face (user choice 2026-11-16, sheet item 5-B).

The KOR banner/icon text boxes draw "인터넷 채널" with the console's system font (wbf1.brfna, Korean
Round Gothic, height 28 / width 24 / Hangul advance 22). On the console that title looked thin and small
next to the original "Internet Channel". Choice B = the same typeface 1.38x larger with a ~0.03 em outline.

The system font cannot be thickened in place, so the menu art gets its own tiny RFNT
(`arc/font/kwce_inet_title.brfnt`, the six characters of the title) drawn from the same typeface
(the console's shared 'Wii-kr_Round Gothic B.ttf') at TWICE the wbf1 metrics, with the outline.
fnl1 gains that font as index 1; only the KOR boxes (the *_ENG panes the KOR group shows) switch to it
and their font size grows by SIZE. Other languages, animations and textures are unchanged.
nw4r's Layout::Build loads an fnl1 font that is not a registered system font from the archive's
'font' resources, so the banner carries the font itself.
"""
import hashlib
import struct

from .channels import load_library, ChannelArchive, layout_sections, rebuild_layout, compress_lz10
from .u8_build import build_u8

FONT_NAME = 'kwce_inet_title.brfnt'
FONT_PATH = 'arc/font/' + FONT_NAME
TEXT = '인터넷 채널'
SIZE = 1.38                  # sheet 5-B: 1.38x the current title
STROKE_EM = 0.029            # sheet 5-B: 1 px outline on a 34.5 px em
SS = 8                       # supersampling
# 2x the wbf1 metrics (height 28, width 24, ascent 22, cell 22x23, baseline 19, Hangul 2/18/22, space 10/0/10)
HEIGHT, WIDTH, ASCENT, LINEFEED = 56, 48, 44, 56
CELL_W, CELL_H, BASELINE = 48, 48, 39       # 2x cell + one spare row above and below for the outline
HANGUL_ADVANCE, SPACE_ADVANCE = 44, 20
SHEET_W, SHEET_H = 256, 128
BOXES = {'banner': ('T_title_00_ENG', 'T_title_01_ENG', 'T_title_03_ENG'), 'icon': ('T_title_ENG',)}
# The Wii Menu stops on an icon.bin larger than ~102.4 KB unpacked ([Dolphin] 101,856 B original and
# 102,432 B zero-padded run, 104,448 B and up halt with a dialog on the channel grid) -- no room for a
# 16 KB font. hardware-v11+ thickens the icon title instead with four child copies of the KOR text box
# (system font, same material, offset +-ICON_OFFSET) that inherit the parent's animated alpha.
ICON_BOX = 'T_title_ENG'
ICON_OFFSET = 0.8            # ~0.029 em of the 1.38x icon title (em ~ fontSize.x 28.7)
ICON_COPIES = ((ICON_OFFSET, 0.0), (-ICON_OFFSET, 0.0), (0.0, ICON_OFFSET), (0.0, -ICON_OFFSET))
ICON_RAW_LIMIT = 102432      # largest unpacked icon.bin seen working in Dolphin
# hardware-v11's four NEW child panes also halted the menu (the icon heap holds the built panes too).
# hardware-v12+ reuses four title boxes a Korean console never shows (their language groups are hidden)
# as the offset copies: same pane count, same animation entries (all seven language titles animate
# byte-identically), so no extra memory. Each donor becomes the KOR text box at ENG + (dx, dy) and moves
# from its language group to KOR; its animated TransY keys get +dy.
ICON_DONORS = (('T_title_GER', ICON_OFFSET, 0.0), ('T_title_FRA', -ICON_OFFSET, 0.0),
               ('T_title_SPA', 0.0, ICON_OFFSET), ('T_title_ITA', 0.0, -ICON_OFFSET))


def _system_ttf():
    from .wiiroom_visual import _font
    return _font


def _wbf1_hangul_ink():
    """Mean ink height of the title's syllables in the console's wbf1 (cell px)."""
    from .channel_korean_font import korean_shared_fonts
    from .wbf_text import WiiFontRenderer
    fonts, _ = korean_shared_fonts()
    renderer = WiiFontRenderer(ChannelArchive(fonts).get('wbf1.brfna'))
    heights = []
    for c in TEXT.replace(' ', ''):
        image = renderer.glyph(ord(c))[0].convert('L').point(lambda v: 255 if v > 96 else 0)
        box = image.getbbox(); heights.append(box[3] - box[1])
    return sum(heights) / len(heights)


def glyph_images():
    """{char: (L image CELL_W x CELL_H, left, glyph width, advance)} -- outlined, baseline at BASELINE."""
    load_library()
    from PIL import Image, ImageDraw
    font_for = _system_ttf()
    target = 2 * _wbf1_hangul_ink() * SS
    size = int(target)
    syllables = TEXT.replace(' ', '')
    for _ in range(8):
        font = font_for(size)
        boxes = [font.getbbox(c, anchor='ls') for c in syllables]
        ink = sum(b[3] - b[1] for b in boxes) / len(boxes)
        size = max(8, int(round(size * target / ink)))
    font = font_for(size)
    stroke = max(1, int(round(STROKE_EM * size)))
    out = {}
    for c in syllables:
        big = Image.new('L', (CELL_W * 2 * SS, CELL_H * SS))
        ImageDraw.Draw(big).text((CELL_W * SS // 2, BASELINE * SS), c, font=font, fill=255, anchor='ls',
                                 stroke_width=stroke, stroke_fill=255)
        small = big.resize((CELL_W * 2, CELL_H), Image.Resampling.LANCZOS)
        box = small.point(lambda v: 255 if v > 8 else 0).getbbox()
        if box[1] < 1 or box[3] > CELL_H - 1 or box[2] - box[0] > CELL_W:
            raise ValueError('Title glyph outside its cell')
        ink = small.crop((box[0], 0, box[2], CELL_H))
        width = ink.width
        out[c] = (ink, (HANGUL_ADVANCE - width) // 2, width, HANGUL_ADVANCE)
    out[' '] = (Image.new('L', (1, CELL_H)), SPACE_ADVANCE // 2, 0, SPACE_ADVANCE)
    return out, dict(ttf_px=size / SS, outline_px=stroke / SS, wbf1_ink_rows=round(target / SS / 2, 2))


def _i4(image):
    data = bytearray()
    for by in range(0, SHEET_H, 8):
        for bx in range(0, SHEET_W, 8):
            for y in range(8):
                for x in range(0, 8, 2):
                    data.append((image.getpixel((bx + x, by + y)) >> 4) << 4 | (image.getpixel((bx + x + 1, by + y)) >> 4))
    return bytes(data)


def title_font():
    """RFNT 1.4: FINF, TGLP (one I4 sheet), CWDH, CMAP (scan). Glyph i sits at cell i, sampled from
    (cellX+1, cellY+1) like nw4r's ResFontBase."""
    from PIL import Image
    glyphs, record = glyph_images()
    order = sorted(glyphs, key=ord)
    cols, rows = SHEET_W // (CELL_W + 1), SHEET_H // (CELL_H + 1)
    if len(order) > cols * rows:
        raise ValueError('Title font sheet capacity')
    sheet = Image.new('L', (SHEET_W, SHEET_H))
    for i, c in enumerate(order):
        x, y = (i % cols) * (CELL_W + 1) + 1, (i // cols) * (CELL_H + 1) + 1
        sheet.paste(glyphs[c][0], (x, y))
    space = order.index(' ')
    finf_at, tglp_at = 16, 16 + 32
    sheet_at = (tglp_at + 32 + 31) // 32 * 32
    pixels = _i4(sheet)
    cwdh_at = sheet_at + len(pixels)
    cwdh = bytearray(b'CWDH' + bytes(12)); struct.pack_into('>HHI', cwdh, 8, 0, len(order) - 1, 0)
    for c in order:
        _, left, width, advance = glyphs[c]; cwdh += struct.pack('>bBb', left, width, advance)
    cwdh += bytes(-len(cwdh) % 4); struct.pack_into('>I', cwdh, 4, len(cwdh))
    cmap_at = cwdh_at + len(cwdh)
    cmap = bytearray(b'CMAP' + bytes(16)); struct.pack_into('>HHHHI', cmap, 8, ord(order[0]), ord(order[-1]), 2, 0, 0)
    cmap += struct.pack('>H', len(order)) + b''.join(struct.pack('>HH', ord(c), i) for i, c in enumerate(order))
    cmap += bytes(-len(cmap) % 4); struct.pack_into('>I', cmap, 4, len(cmap))
    total = cmap_at + len(cmap)
    header = b'RFNT\xfe\xff\x01\x04' + struct.pack('>IHH', total, 16, 4)
    finf = b'FINF' + struct.pack('>IBbHbBbBIIIBBBB', 32, 1, LINEFEED, space, SPACE_ADVANCE // 2, 0, SPACE_ADVANCE, 1,
                                  tglp_at + 8, cwdh_at + 8, cmap_at + 8, HEIGHT, WIDTH, ASCENT, 0)
    tglp = bytearray(b'TGLP' + struct.pack('>I', sheet_at - tglp_at + len(pixels)))
    tglp += struct.pack('>BBbBIHHHHHHI', CELL_W, CELL_H, BASELINE, CELL_W, len(pixels), 1, 0, cols, rows, SHEET_W, SHEET_H, sheet_at)
    tglp += bytes(sheet_at - tglp_at - len(tglp))
    data = header + finf + bytes(tglp) + pixels + bytes(cwdh) + bytes(cmap)
    if len(data) != total:
        raise ValueError('Title font size')
    from .channel_font import font_data
    _, mapping, widths = font_data(data)
    if {chr(k): v for k, v in mapping.items()} != {c: i for i, c in enumerate(order)}:
        raise ValueError('Title font map')
    record.update(glyphs=''.join(order), sha256=hashlib.sha256(data).hexdigest(), size=len(data),
                  metrics=dict(height=HEIGHT, width=WIDTH, ascent=ASCENT, cell=[CELL_W, CELL_H], baseline=BASELINE))
    return data, record


def _fnl_with(section, name):
    count = struct.unpack_from('>H', section, 8)[0]
    names = []
    for i in range(count):
        off = struct.unpack_from('>I', section, 12 + 8 * i)[0]
        names.append(section[12 + off:section.index(b'\0', 12 + off)])
    names.append(name.encode('ascii'))
    table = bytearray(); blob = bytearray(); base = 8 * len(names)
    for n in names:
        table += struct.pack('>II', base + len(blob), 0); blob += n + b'\0'
    body = struct.pack('>HH', len(names), 0) + bytes(table) + bytes(blob)
    body += bytes(-(8 + len(body)) % 4)
    return b'fnl1' + struct.pack('>I', 8 + len(body)) + body, len(names) - 1


def patch_layout(layout, boxes, size=SIZE):
    sections = layout_sections(layout); index = None; done = []
    for i, s in enumerate(sections):
        if s[:4] == b'fnl1':
            if index is not None:
                raise ValueError('Two font lists')
            sections[i], index = _fnl_with(s, FONT_NAME)
    if index is None:
        raise ValueError('No font list')
    for i, s in enumerate(sections):
        if s[:4] == b'txt1' and s[0xc:0x1c].split(b'\0')[0].decode() in boxes:
            s = bytearray(s)
            if struct.unpack_from('>H', s, 0x52)[0] != 0:
                raise ValueError('Unexpected title font index')
            struct.pack_into('>H', s, 0x52, index)
            fx, fy = struct.unpack_from('>ff', s, 0x64)
            struct.pack_into('>ff', s, 0x64, fx * size, fy * size)
            sections[i] = bytes(s); done.append(s[0xc:0x1c].split(b'\0')[0].decode())
    if sorted(done) != sorted(boxes):
        raise ValueError(f'Title boxes not found: {done}')
    return rebuild_layout(layout, sections)


def bold_copies_layout(layout, name=ICON_BOX, copies=ICON_COPIES, size=SIZE):
    """KOR icon title: font size x size, influenced-alpha on, plus child copies offset by `copies`."""
    sections = layout_sections(layout); out = []; found = 0
    for i, s in enumerate(sections):
        if s[:4] == b'txt1' and s[0xc:0x1c].split(b'\0')[0].decode() == name:
            if i + 1 < len(sections) and sections[i + 1][:4] == b'pas1':
                raise ValueError('Title box already has children')
            s = bytearray(s); fx, fy = struct.unpack_from('>ff', s, 0x64)
            struct.pack_into('>ff', s, 0x64, fx * size, fy * size)
            child_flags = s[8]; s[8] |= 0x02          # children follow the animated pane alpha
            out.append(bytes(s)); out.append(b'pas1' + struct.pack('>I', 8))
            strlen, stroff = struct.unpack_from('>H', s, 0x4e)[0], struct.unpack_from('>I', s, 0x58)[0]
            text = bytes(s[stroff:stroff + strlen])
            if text[-2:] != b'\0\0':
                raise ValueError('Unterminated title string')
            # compact copy: header + the KOR string only (the parent still carries the old English
            # buffer before its string; copying it would cost 56 B per copy of the icon budget)
            base = bytearray(s[:0x74]); struct.pack_into('>HH', base, 0x4c, strlen, strlen)
            struct.pack_into('>I', base, 0x58, 0x74)
            compact = base + text + bytes(-len(text) % 4); struct.pack_into('>I', compact, 4, len(compact))
            for n, (dx, dy) in enumerate(copies):
                c = bytearray(compact); c[8] = child_flags; c[0xa] = 255
                c[0xc:0x1c] = (f'{name}_b{n}'.encode()).ljust(16, b'\0')
                struct.pack_into('>fff', c, 0x24, dx, dy, 0.0); struct.pack_into('>fff', c, 0x30, 0, 0, 0)
                struct.pack_into('>ff', c, 0x3c, 1.0, 1.0)
                out.append(bytes(c))
            out.append(b'pae1' + struct.pack('>I', 8)); found += 1
        else:
            out.append(s)
    if found != 1:
        raise ValueError('Icon title box not found')
    return rebuild_layout(layout, out)


def _compact_text_box(s):
    """txt1 header + its string only (drops the old English buffer kept before the KOR string)."""
    strlen, stroff = struct.unpack_from('>H', s, 0x4e)[0], struct.unpack_from('>I', s, 0x58)[0]
    text = bytes(s[stroff:stroff + strlen])
    if text[-2:] != b'\0\0':
        raise ValueError('Unterminated title string')
    base = bytearray(s[:0x74]); struct.pack_into('>HH', base, 0x4c, strlen, strlen); struct.pack_into('>I', base, 0x58, 0x74)
    out = base + text + bytes(-len(text) % 4); struct.pack_into('>I', out, 4, len(out))
    return out


def repurpose_layout(layout, name=ICON_BOX, donors=ICON_DONORS, size=SIZE):
    sections = layout_sections(layout)
    names = lambda s: s[0xc:0x1c].split(b'\0')[0].decode()
    at = [i for i, s in enumerate(sections) if s[:4] == b'txt1' and names(s) == name]
    if len(at) != 1:
        raise ValueError('Icon title box not found')
    eng = bytearray(sections[at[0]]); fx, fy = struct.unpack_from('>ff', eng, 0x64)
    struct.pack_into('>ff', eng, 0x64, fx * size, fy * size); sections[at[0]] = bytes(eng)
    tx, ty, tz = struct.unpack_from('>fff', eng, 0x24); compact = _compact_text_box(eng)
    moved = {d for d, _, _ in donors}; done = set()
    for i, s in enumerate(sections):
        if s[:4] == b'txt1' and names(s) in moved:
            dx, dy = next((x, y) for d, x, y in donors if d == names(s))
            c = bytearray(compact); c[0xc:0x1c] = s[0xc:0x1c]           # keep the donor's name (animation, groups)
            struct.pack_into('>fff', c, 0x24, tx + dx, ty + dy, tz)
            sections[i] = bytes(c); done.add(names(s))
        elif s[:4] == b'grp1':
            count = struct.unpack_from('>H', s, 0x18)[0]
            panes = [s[0x1c + 16 * q:0x2c + 16 * q] for q in range(count)]
            group = s[8:24].split(b'\0')[0]
            keep = [n for n in panes if n.split(b'\0')[0].decode() not in moved]
            if group == b'KOR':
                keep += [d.encode().ljust(16, b'\0') for d, _, _ in donors]
            if keep != panes:
                g = bytearray(s[:0x1c]); struct.pack_into('>H', g, 0x18, len(keep)); g += b''.join(keep)
                struct.pack_into('>I', g, 4, len(g)); sections[i] = bytes(g)
    if done != moved:
        raise ValueError('Donor title boxes not found')
    return rebuild_layout(layout, sections)


def shift_title_animation(brlan, donors=ICON_DONORS):
    """Donor pane entries: RLPA TransY (target 1) key values + dy; entries must equal the ENG entry."""
    d = bytearray(brlan); pai = d.find(b'pai1')
    count = struct.unpack_from('>H', d, pai + 0xe)[0]; table = pai + struct.unpack_from('>I', d, pai + 0x10)[0]
    entries = {d[e:e + 20].split(b'\0')[0].decode(): e for e in (pai + struct.unpack_from('>I', d, table + 4 * i)[0] for i in range(count))}
    ends = sorted(entries.values()) + [len(d)]
    body = lambda e: bytes(d[e + 20:ends[ends.index(e) + 1]])
    for donor, dx, dy in donors:
        e = entries[donor]
        if body(e) != body(entries[ICON_BOX]):
            raise ValueError(f'{donor} animation differs from {ICON_BOX}')
        for j in range(d[e + 20]):
            tag = e + struct.unpack_from('>I', d, e + 24 + 4 * j)[0]
            if d[tag:tag + 4] != b'RLPA':
                continue
            for k in range(d[tag + 4]):
                at = tag + struct.unpack_from('>I', d, tag + 8 + 4 * k)[0]
                _, target, curve, _, keys, _, offset = struct.unpack_from('>BBBBHHI', d, at)
                if target == 0 and dx:
                    raise ValueError('Animated TransX')
                if target == 1 and dy:
                    if curve != 2:
                        raise ValueError('Unexpected TransY curve')
                    for q in range(keys):
                        v = struct.unpack_from('>f', d, at + offset + 12 * q + 4)[0]
                        struct.pack_into('>f', d, at + offset + 12 * q + 4, v + dy)
    return bytes(d)


def patch_icon_repurpose(wrapped):
    """icon.bin: icon.brlyt (repurpose_layout) and icon.brlan (shift_title_animation) only."""
    load_library()
    from libWiiPy.archive import decompress_lz77
    if wrapped[:4] != b'IMD5' or hashlib.md5(wrapped[32:]).digest() != wrapped[16:32]:
        raise ValueError('Menu artwork integrity')
    before = ChannelArchive(decompress_lz77(wrapped[32:])); lay, anim = 'arc/blyt/icon.brlyt', 'arc/anim/icon.brlan'
    archive = ChannelArchive(before.replace(lay, repurpose_layout(before.get(lay))))
    archive = ChannelArchive(archive.replace(anim, shift_title_animation(before.get(anim))))
    raw = archive.compact(); after = ChannelArchive(raw)
    if set(after.files) != set(before.files) or any(after.get(p) != before.get(p) for p in before.files if p not in (lay, anim)):
        raise ValueError('Icon change escaped layout + animation')
    if len(raw) > len(before.data):
        raise ValueError('Repurposed icon grew')
    payload = b'LZ77' + compress_lz10(raw)
    if decompress_lz77(payload) != raw:
        raise ValueError('Menu artwork compression')
    return b'IMD5' + len(payload).to_bytes(4, 'big') + bytes(8) + hashlib.md5(payload).digest() + payload, len(raw)


def patch_icon_copies(wrapped):
    """icon.bin: only arc/blyt/icon.brlyt changes (bold_copies_layout); U8 topology kept, data repacked."""
    load_library()
    from libWiiPy.archive import decompress_lz77
    if wrapped[:4] != b'IMD5' or hashlib.md5(wrapped[32:]).digest() != wrapped[16:32]:
        raise ValueError('Menu artwork integrity')
    before = ChannelArchive(decompress_lz77(wrapped[32:])); path = 'arc/blyt/icon.brlyt'
    raw = ChannelArchive(ChannelArchive(before.replace(path, bold_copies_layout(before.get(path)))).compact()).compact()
    after = ChannelArchive(raw)
    if set(after.files) != set(before.files) or any(after.get(p) != before.get(p) for p in before.files if p != path):
        raise ValueError('Icon change escaped the layout')
    if len(raw) > ICON_RAW_LIMIT:
        raise ValueError(f'icon.bin {len(raw)} B exceeds the Wii Menu limit seen in Dolphin')
    payload = b'LZ77' + compress_lz10(raw)
    if decompress_lz77(payload) != raw:
        raise ValueError('Menu artwork compression')
    return b'IMD5' + len(payload).to_bytes(4, 'big') + bytes(8) + hashlib.md5(payload).digest() + payload, len(raw)


def u8_has_dot_root(data):
    """True when the U8 root's first child is Nintendo's virtual '.' directory."""
    root = struct.unpack_from('>I', data, 4)[0]
    count = struct.unpack_from('>I', data, root + 8)[0]
    if count < 2:
        return False
    word = struct.unpack_from('>I', data, root + 12)[0]
    strings = root + count * 12
    name = data[strings + (word & 0xffffff):data.index(b'\0', strings + (word & 0xffffff))]
    return word >> 24 == 1 and name == b'.'


def patch_member(wrapped, kind, font, keep_u8_root=True):
    """IMD5/LZ77 banner.bin or icon.bin -> same archive + arc/font/kwce_inet_title.brfnt + patched layout.
    keep_u8_root: rebuild the U8 with the parent's root shape. The Internet menu archives have no '.'
    directory (root -> arc); hardware-v9 inserted one (keep_u8_root=False) and the Wii Menu could not
    find arc/blyt/icon.brlyt (Dolphin stopped with a dialog on the channel grid)."""
    load_library()
    from libWiiPy.archive import decompress_lz77
    if wrapped[:4] != b'IMD5' or hashlib.md5(wrapped[32:]).digest() != wrapped[16:32]:
        raise ValueError('Menu artwork integrity')
    before = ChannelArchive(decompress_lz77(wrapped[32:]))
    if FONT_PATH in before.files:
        raise ValueError('Title font already present')
    files = {p: before.get(p) for p in before.files}
    layout_path = f'arc/blyt/{kind}.brlyt'
    files[layout_path] = patch_layout(files[layout_path], BOXES[kind])
    files[FONT_PATH] = font
    raw = build_u8(files, dot=u8_has_dot_root(before.data) if keep_u8_root else True)
    after = ChannelArchive(raw)
    if keep_u8_root and u8_has_dot_root(raw) != u8_has_dot_root(before.data):
        raise ValueError('U8 root shape changed')
    if set(after.files) != set(before.files) | {FONT_PATH} or any(
            after.get(p) != before.get(p) for p in before.files if p != layout_path):
        raise ValueError('Title change escaped layout + font')
    payload = b'LZ77' + compress_lz10(raw)
    if decompress_lz77(payload) != raw:
        raise ValueError('Menu artwork compression')
    return b'IMD5' + len(payload).to_bytes(4, 'big') + bytes(8) + hashlib.md5(payload).digest() + payload, len(raw)


def content0(parent_content0, keep_u8_root=True, icon_mode='repurpose'):
    """icon_mode 'repurpose' (hardware-v12+); defective: 'copies' (v11, new panes) and 'font' (v9/v10,
    icon.bin too large)."""
    font, record = title_font()
    outer = ChannelArchive(parent_content0[0x640:]); prefix = bytearray(parent_content0[:0x640])
    for kind in ('banner', 'icon'):
        if kind == 'icon' and icon_mode == 'repurpose':
            wrapped, size = patch_icon_repurpose(outer.get('meta/icon.bin'))
        elif kind == 'icon' and icon_mode == 'copies':
            wrapped, size = patch_icon_copies(outer.get('meta/icon.bin'))
        else:
            wrapped, size = patch_member(outer.get(f'meta/{kind}.bin'), kind, font, keep_u8_root)
        outer = ChannelArchive(outer.replace(f'meta/{kind}.bin', wrapped))
        struct.pack_into('>I', prefix, 0x40 + (0x50 if kind == 'banner' else 0x4c), size)
        record[f'{kind}_size'] = size
    prefix[0x630:0x640] = bytes(16); prefix[0x630:0x640] = hashlib.md5(prefix[0x40:0x640]).digest()
    record.update(boxes=BOXES, font_path=FONT_PATH, size_factor=SIZE, stroke_em=STROKE_EM, u8_root_kept=keep_u8_root, icon_mode=icon_mode)
    if icon_mode == 'copies':
        record.update(boxes=dict(BOXES, icon=()), icon_box=ICON_BOX, icon_copies=[list(c) for c in ICON_COPIES], icon_raw_limit=ICON_RAW_LIMIT)
    if icon_mode == 'repurpose':
        record.update(boxes=dict(BOXES, icon=()), icon_box=ICON_BOX, icon_donors=[list(c) for c in ICON_DONORS])
    return bytes(prefix) + outer.compact(), record

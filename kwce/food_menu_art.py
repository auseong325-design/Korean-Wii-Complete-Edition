"""Korean Wii Menu banner and icon art for the Food channel (content 0).

The stock wordmark is seven CI4 glyph tiles (出前|チャン|ネル) in both the
banner and the icon, with an orange alpha-ramp palette. Each tile is redrawn
with the Korean Round Gothic B system font as 음식 | 배달 | 채널 (one common
font size and baseline per archive); the small ャ tile becomes transparent and
the 배/달 panes move to the same spacing as the other two pairs. Only pane X
translations change in the layouts: no X track is animated for these panes.
The banner textbox T_yume (operator line, kanji blank on a Korean menu) and the
icon's '注文中' bubble text are translated too. Palettes, sizes, GX formats,
animations and every other resource stay byte-identical. The IMET sizes and
MD5 are recomputed; the Korean IMET names come from kwce.food_banner.
"""
import hashlib
import struct

from .channels import ChannelArchive, compress_lz10, layout_sections, load_library, rebuild_layout, replace_textbox, textbox
from .channel_texture import texture_records

WORD = ['음', '식', '배', '', '달', '채', '널']   # tile 03 (small ャ) left blank
YUME_JA = 'このサービスは、夢の街創造委員会(株)が運営しています。'
YUME_KO = '이 서비스는 유메노마치소조위원회(주)가 운영합니다.'          # build-v6 / hardware-v5
YUME_KO_V7 = '이 서비스는 유메노마치소조이인카이(주)가 운영합니다.'     # v7+: operator name in one form (lead review)
ORDER_KO = '주문 중'
BANNER = dict(member='meta/banner.bin', layout='arc/blyt/banner.brlyt', size_at=0x90,
              textures=['bannder_logo_00_de', 'bannder_logo_01_ma', 'bannder_logo_02_chi', 'bannder_logo_03_ya',
                        'bannder_logo_04_n', 'bannder_logo_05_ne', 'bannder_logo_06_ru'],
              panes=['Ban_logo_%02d' % i for i in range(7)], weight=0.015,
              x={'Ban_logo_02': -33.0, 'Ban_logo_04': 33.0})
ICON = dict(member='meta/icon.bin', layout='arc/blyt/icon.brlyt', size_at=0x8c,
            textures=['icon_logo_00_de', 'icon_logo_01_ma', 'icon_logo_02_chi', 'icon_logo_03_ya',
                      'icon_logo_04_n', 'icon_logo_05_ne', 'icon_logo_06_ru'],
            panes=['Ico_logo_%02d' % i for i in range(7)], weight=0.0,
            x={'Ico_logo_02': -8.0, 'Ico_logo_04': 8.0, 'Ico_logo_05': 30.0, 'Ico_logo_06': 46.0})
ORDER_TEXTURE = 'arc/timg/icon_order00a.tpl'


# ---- palette (CI4 / CI8) textures: decode, and encode against the ORIGINAL palette ----

def _palette(data, index):
    from .tpl import _rgb565, _rgb5a3
    r = texture_records(data)[index]
    if r['format'] not in (8, 9) or not r['palette']:
        raise ValueError('Expected a CI4/CI8 texture')
    n, _, fmt, at = struct.unpack_from('>HBxII', data, r['palette'])
    if not 0 < n <= (16 if r['format'] == 8 else 256) or at + 2 * n > len(data):
        raise ValueError('TPL palette bounds')
    out = []
    for i in range(n):
        v = struct.unpack_from('>H', data, at + 2 * i)[0]
        out.append((v & 255, v & 255, v & 255, v >> 8) if fmt == 0 else _rgb565(v) + (255,) if fmt == 1 else _rgb5a3(v))
    return r, out


def _texels(r):
    """(byte offset, x, y) of every texel; CI4 blocks are 8x8 (4 bytes/row), CI8 8x4 (8 bytes/row)."""
    w, h, fmt = r['width'], r['height'], r['format']
    bw, bh = (8, 8) if fmt == 8 else (8, 4); pos = r['offset']
    for by in range(0, h, bh):
        for bx in range(0, w, bw):
            for y in range(bh):
                for x in range(bw):
                    yield (pos + y * 4 + x // 2) if fmt == 8 else (pos + y * 8 + x), bx + x, by + y
            pos += 32


def decode_ci(data, index=0):
    load_library(); from PIL import Image
    r, pal = _palette(data, index); w, h = r['width'], r['height']
    image = Image.new('RGBA', (w, h)); px = image.load()
    for pos, x, y in _texels(r):
        v = data[pos]
        if r['format'] == 8:
            v = v >> 4 if x % 2 == 0 else v & 15
        if x < w and y < h:
            if v >= len(pal):
                raise ValueError('Palette index out of range')
            px[x, y] = pal[v]
    return image


def _nearest(pal):
    pre = [(c[0] * c[3] / 255, c[1] * c[3] / 255, c[2] * c[3] / 255, c[3]) for c in pal]
    cache = {}

    def pick(c):
        if c not in cache:
            a = c[3]; q = (c[0] * a / 255, c[1] * a / 255, c[2] * a / 255, a)
            cache[c] = min(range(len(pre)), key=lambda i: sum((p - s) ** 2 for p, s in zip(pre[i], q)) + 0.5 * (pre[i][3] - a) ** 2)
        return cache[c]
    return pick


def encode_ci(data, index, image):
    """Re-index image onto the texture's existing palette; palette and header unchanged."""
    r, pal = _palette(data, index); w, h = r['width'], r['height']
    image = image.convert('RGBA')
    if image.size != (w, h):
        raise ValueError('Replacement texture size')
    pick = _nearest(pal); px = image.load(); out = bytearray(data)
    for pos, x, y in _texels(r):
        v = pick(px[min(x, w - 1), min(y, h - 1)])
        if r['format'] == 8:
            out[pos] = (out[pos] & 0x0f) | (v << 4) if x % 2 == 0 else (out[pos] & 0xf0) | v
        else:
            out[pos] = v
    return bytes(out)


def decode_any(data, index=0):
    from .tpl import decode
    return decode_ci(data, index) if texture_records(data)[index]['format'] in (8, 9) else decode(data, index)


def encode_any(data, index, image):
    from .tpl import encode
    return encode_ci(data, index, image) if texture_records(data)[index]['format'] in (8, 9) else encode(data, index, image)


# ---- glyph tiles ----

_FONT = {}


def font(px):
    """Korean shared Round Gothic B (the font kwce.wiiroom_visual draws with), cached."""
    import io
    from PIL import ImageFont
    if 'data' not in _FONT:
        from .opera_font import KOREAN_SHARED
        from .wiiroom_visual import FONT_ENTRY
        _FONT['data'] = ChannelArchive(KOREAN_SHARED.read_bytes()).get(FONT_ENTRY)
    return ImageFont.truetype(io.BytesIO(_FONT['data']), px)


def glyph_masks(sizes, syllables, pad, weight=0.0):
    """One Round Gothic B size for all syllables; each centred on its advance, common baseline.

    weight > 0 thickens strokes (stroke width = weight * font size) to match the heavy stock logo."""
    from PIL import Image, ImageDraw
    w, h = sizes
    text = [s for s in syllables if s]
    for px in range(h + 8, 5, -1):
        face = font(px); stroke = int(round(weight * px))
        boxes = [face.getbbox(s, stroke_width=stroke) for s in text]
        top = min(b[1] for b in boxes); bottom = max(b[3] for b in boxes)
        if max(b[2] - b[0] for b in boxes) <= w - 2 * pad and bottom - top <= h - 2 * pad:
            break
    else:
        raise ValueError('Korean wordmark does not fit its tiles')
    masks = []
    for s in syllables:
        layer = Image.new('L', (w, h), 0)
        if s:
            l, _, r, _ = face.getbbox(s, stroke_width=stroke)
            ImageDraw.Draw(layer).text(((w - (r - l)) / 2 - l, (h - (bottom - top)) / 2 - top), s, font=face, fill=255,
                                       stroke_width=stroke, stroke_fill=255)
        masks.append(layer)
    return masks, px


def _ramp(data, mask):
    """Alpha mask -> image using the tile's own palette colour."""
    from PIL import Image
    _, pal = _palette(data, 0)
    solid = max(pal, key=lambda c: (c[3], -sum(c[:3])))       # the opaque orange entry
    image = Image.new('RGBA', mask.size, solid[:3] + (0,))
    image.putalpha(mask)
    return image


def _outlined(size, text, fill, outline, stroke, box):
    from PIL import Image, ImageDraw
    from .wiiroom_visual import _coverage
    inner, outer = _coverage(size, text, stroke, box)
    image = Image.new('RGBA', size, outline[:3] + (0,))
    image.putalpha(outer)
    top = Image.new('RGBA', size, fill[:3] + (0,)); top.putalpha(inner)
    return Image.alpha_composite(image, top)


def _wrap(archive):
    raw = archive.compact(); payload = b'LZ77' + compress_lz10(raw)
    return raw, b'IMD5' + len(payload).to_bytes(4, 'big') + bytes(8) + hashlib.md5(payload).digest() + payload


def _pane_textures(layout):
    """{pic1 pane name: texture name} through the pane's material index and its first texture map."""
    sections = layout_sections(layout)
    txl = next(s for s in sections if s[:4] == b'txl1'); mats = next(s for s in sections if s[:4] == b'mat1')
    names = []
    for i in range(struct.unpack_from('>H', txl, 8)[0]):
        at = 12 + struct.unpack_from('>I', txl, 12 + 8 * i)[0]
        names.append(txl[at:txl.index(b'\0', at)].decode('ascii'))
    count = struct.unpack_from('>H', mats, 8)[0]
    offsets = [struct.unpack_from('>I', mats, 12 + 4 * i)[0] for i in range(count)]
    out = {}
    for s in sections:
        if s[:4] == b'pic1':
            pane = s[12:28].split(b'\0')[0].decode('ascii'); m = struct.unpack_from('>H', s, 0x5c)[0]
            if m >= count:
                raise ValueError('Pane material index bounds')
            at = offsets[m]
            if struct.unpack_from('>I', mats, at + 0x3c)[0] & 15:
                out[pane] = names[struct.unpack_from('>H', mats, at + 0x40)[0]]
    return out


BOLD_BUMP = 0.035       # revision >= 10: thicker, rounder strokes closer to the heavy stock logo (counters stay open)


def _archive(before, spec, banner, yume=YUME_KO, bold=False):
    layout_path = spec['layout']; layout = before.get(layout_path)
    mapping = _pane_textures(layout)
    if [mapping.get(p) for p in spec['panes']] != [t + '.tpl' for t in spec['textures']]:
        raise ValueError('Food wordmark pane/texture mapping differs')
    first = before.get('arc/timg/' + spec['textures'][0] + '.tpl'); size = decode_ci(first).size
    weight = spec['weight'] + (BOLD_BUMP if bold else 0.0)
    masks, font_px = glyph_masks(size, WORD, 2 if banner else 0, weight)
    archive = before; changed = {layout_path}
    for name, syllable, mask in zip(spec['textures'], WORD, masks):
        path = 'arc/timg/' + name + '.tpl'; raw = archive.get(path); tile = decode_ci(raw)
        if syllable == '':
            mask = mask.resize(tile.size)          # small tile: fully transparent
        elif tile.size != size:
            raise ValueError('Unexpected wordmark tile size')
        archive = ChannelArchive(archive.replace(path, encode_ci(raw, 0, _ramp(raw, mask)))); changed.add(path)
    sections = layout_sections(layout); moved = {}
    for i, s in enumerate(sections):
        if s[:4] == b'pic1':
            pane = s[12:28].split(b'\0')[0].decode('ascii')
            if pane in spec['x']:
                s = bytearray(s); moved[pane] = (struct.unpack_from('>f', s, 0x24)[0], spec['x'][pane])
                struct.pack_into('>f', s, 0x24, spec['x'][pane]); sections[i] = bytes(s)
        tb = textbox(s) if banner else None
        if tb and tb[0] == 'T_yume':
            if tb[1] != YUME_JA:
                raise ValueError('Banner operator line differs')
            sections[i] = replace_textbox(sections[i], yume); moved['T_yume'] = 'text'
    if set(moved) != set(spec['x']) | ({'T_yume'} if banner else set()):
        raise ValueError('Food wordmark panes missing')
    archive = ChannelArchive(archive.replace(layout_path, rebuild_layout(layout, sections)))
    record = dict(member=spec['member'], glyphs=''.join(WORD), font='Round Gothic B %dpx' % font_px,
                  stroke_weight=round(weight, 3), bold=bold,
                  moved_panes={k: v for k, v in moved.items() if k != 'T_yume'}, blank_tile=spec['textures'][3])
    if not banner:
        raw = archive.get(ORDER_TEXTURE); old = decode_ci(raw); w, h = old.size
        _, pal = _palette(raw, 0)
        dark = min((c for c in pal if c[3] == 255), key=lambda c: sum(c[:3]))
        image = _outlined((w, h), ORDER_KO, (255, 255, 255, 255), dark, 2, (2, 2, w - 2, h - 2))
        archive = ChannelArchive(archive.replace(ORDER_TEXTURE, encode_ci(raw, 0, image))); changed.add(ORDER_TEXTURE)
        record['order_badge'] = ORDER_KO
    else:
        record['operator_line'] = yume
    if set(archive.files) != set(before.files) or any(archive.get(p) != before.get(p) for p in before.files if p not in changed):
        raise ValueError('Food menu art change escaped its resources')
    return archive, record


def korean_menu_art(content, yume=YUME_KO, bold=False):
    """Return (content 0 with Korean wordmark/badge/operator line, records). IMET names untouched here.

    bold=True (revision >= 10) thickens the wordmark strokes (kwce rc6 W-Food logo polish)."""
    load_library(); from libWiiPy.archive import decompress_lz77
    from .food_banner import _imet_md5, MD5_AT
    if content[0x80:0x84] != b'IMET' or _imet_md5(content) != content[MD5_AT:MD5_AT + 16]:
        raise ValueError('Food banner IMET identity')
    outer = ChannelArchive(content[0x640:]); prefix = bytearray(content[:0x640]); records = []
    for spec, banner in ((BANNER, True), (ICON, False)):
        wrapped = outer.get(spec['member'])
        if wrapped[:4] != b'IMD5' or hashlib.md5(wrapped[32:]).digest() != wrapped[16:32] or wrapped[32:36] != b'LZ77':
            raise ValueError('Food menu art archive integrity')
        before = ChannelArchive(decompress_lz77(wrapped[32:]))
        if struct.unpack_from('>I', prefix, spec['size_at'])[0] != len(before.data):
            raise ValueError('IMET size field differs from the archive')
        archive, record = _archive(before, spec, banner, yume, bold)
        raw, wrapped = _wrap(archive)
        if decompress_lz77(wrapped[32:]) != raw:
            raise ValueError('Food menu art compression')
        outer = ChannelArchive(outer.replace(spec['member'], wrapped))
        struct.pack_into('>I', prefix, spec['size_at'], len(raw)); records.append(record)
    out = bytearray(bytes(prefix) + outer.compact())
    out[MD5_AT:MD5_AT + 16] = _imet_md5(out)
    return bytes(out), records

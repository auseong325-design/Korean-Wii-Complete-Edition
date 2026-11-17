"""Mii Contest build-v34 menu art (user choice 2026-11-16, sheet items 1-A and 2-A).

Banner: the v32/v33 block-face syllables, but the syllable cells no longer overlap (v33 overlapped
them by 6 px, so neighbouring letters touched on the console). Everything else is the v33 recipe:
`animated_korean_title_v20(cell=(54,52), gap=6, drop=3.0, row2_y=28.0)` + the v32 block textures.
Icon: the blank v33 icon wordmark becomes the Japanese icon's layout -- the teal "Mii" art cut from
the Japanese icon (stMcLogoJp) over 콘테스트 / 채널 in the banner's block face, RGB5A3 112x65.

`banner_member(us_content0, 6)` rebuilds v33's banner.bin exactly (the builder checks this before it
makes v34); the icon is v33's icon.bin with only the wordmark texture replaced.
"""
import hashlib
import struct
from pathlib import Path

from .channels import ROOT, load_library, ChannelArchive, layout_sections, rebuild_layout, compress_lz10
from . import mii_contest_visual as mv
from . import mii_contest_wordmark_v32 as wm
from . import tpl as ktpl

FONT = ROOT / 'workspace/channels/forecast/references/NotoSansKR.ttf'
JP_WAD = ROOT / 'workspace/channels/mii-contest/originals/mii-contest-japan-v512.wad'
BANNER = dict(cell=(54, 52), gap=6, drop=3.0, row2_y=28.0, glyph=dict(outline=2.0, bold=0, rim=1, weight=700, close=.6))
ICON_SIZE = (112, 65)
ICON_TEXTURE = 'arc/timg/stMcLogoUsEn.tpl'


def _rgb5a3(v):
    if v & 0x8000:
        return ((v >> 10 & 31) * 255 // 31, (v >> 5 & 31) * 255 // 31, (v & 31) * 255 // 31, 255)
    return ((v >> 8 & 15) * 17, (v >> 4 & 15) * 17, (v & 15) * 17, (v >> 12 & 7) * 255 // 7)


def decode_c8(data):
    """TPL image 0 in C8 (palette IA8/RGB565/RGB5A3) -> RGBA."""
    from PIL import Image
    _, table = struct.unpack_from('>II', data, 4)
    image_at, palette_at = struct.unpack_from('>II', data, table)
    h, w, fmt, data_at = struct.unpack_from('>HHII', data, image_at)
    if fmt != 9:
        raise ValueError('Expected a C8 texture')
    count, _, _, pfmt, pal_at = struct.unpack_from('>HBBII', data, palette_at)
    palette = []
    for i in range(count):
        v = struct.unpack_from('>H', data, pal_at + 2 * i)[0]
        palette.append((v & 255,) * 3 + (v >> 8,) if pfmt == 0 else
                       ((v >> 11) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31, 255) if pfmt == 1 else _rgb5a3(v))
    image = Image.new('RGBA', (w, h)); px = image.load(); pos = data_at
    for by in range(0, h, 4):
        for bx in range(0, w, 8):
            for y in range(4):
                for x in range(8):
                    i = data[pos]; pos += 1
                    if bx + x < w and by + y < h:
                        px[bx + x, by + y] = palette[i]
    return image


def encode_rgb5a3(image):
    """One-image TPL, RGB5A3 (format 5), clamp wrap, linear filters."""
    from .tpl import _q5a3
    w, h = image.size; image = image.convert('RGBA')
    head = struct.pack('>III', 0x20af30, 1, 12) + struct.pack('>II', 20, 0)
    info = struct.pack('>HHII', h, w, 5, 64) + struct.pack('>IIIIfBBBB', 0, 0, 1, 1, 0, 0, 0, 0, 0)
    out = bytearray((head + info).ljust(64, b'\0'))
    for by in range(0, (h + 3) // 4 * 4, 4):
        for bx in range(0, (w + 3) // 4 * 4, 4):
            for y in range(4):
                for x in range(4):
                    c = image.getpixel((bx + x, by + y)) if bx + x < w and by + y < h else (0, 0, 0, 0)
                    out += struct.pack('>H', _q5a3(c))
    return bytes(out)


def japanese_mii_art():
    """The teal 'Mii' of the Japanese icon wordmark (first ink band of stMcLogoJp), cropped to ink."""
    load_library()
    from libWiiPy.archive import decompress_lz77
    title = load_library().title.Title(); title.load_wad(JP_WAD.read_bytes())
    c0 = title.get_content_by_index(0); outer = ChannelArchive(c0[c0.find(b'U\xaa8-'):])
    data = outer.get('meta/icon.bin')[32:]; data = decompress_lz77(data) if data[:4] == b'LZ77' else data
    image = decode_c8(ChannelArchive(data).get('arc/timg/stMcLogoJp.tpl'))
    alpha = image.split()[3]
    rows = [y for y in range(image.height) if any(alpha.getpixel((x, y)) > 8 for x in range(image.width))]
    band = [rows[0]]
    for y in rows[1:]:
        if y != band[-1] + 1:
            break
        band.append(y)
    mii = image.crop((0, band[0], image.width, band[-1] + 1))
    return mii.crop(mii.split()[3].getbbox())


def block_row(text, height, max_width):
    """Block-face syllables (v32 glyphs), ink-cropped and set 1 px apart; squeezed to max_width."""
    from PIL import Image
    cell = (int(height * 1.04), height)
    tiles = [wm.syllable(c, cell) for c in text]
    inks = [t.split()[3].getbbox() for t in tiles]
    width = sum(b[2] - b[0] for b in inks) + (len(tiles) - 1)
    row = Image.new('RGBA', (width, height)); x = 0
    for tile, box in zip(tiles, inks):
        row.alpha_composite(tile.crop((box[0], 0, box[2], height)), (x, 0)); x += box[2] - box[0] + 1
    if row.width > max_width:
        row = row.resize((max_width, height), Image.LANCZOS)
    return row


def icon_image():
    """Sheet item 2-A: Japanese layout, three rows -- Mii / 콘테스트 / 채널."""
    from PIL import Image
    w, h = ICON_SIZE
    image = Image.new('RGBA', (w, h), (0, 0, 0, 0)); art = japanese_mii_art()
    mii = art.resize((int(art.width * 19 / art.height), 19), Image.LANCZOS)
    row1, row2 = block_row('콘테스트', 23, 110), block_row('채널', 23, 60)
    y = 0
    image.alpha_composite(mii, ((w - mii.width) // 2, y)); y += mii.height - 1
    image.alpha_composite(row1, ((w - row1.width) // 2, y)); y += row1.height - 1
    image.alpha_composite(row2, ((w - row2.width) // 2, y))
    return image


def _unwrap(outer, name):
    from libWiiPy.archive import decompress_lz77
    wrapped = outer.get(name)
    if wrapped[:4] != b'IMD5' or hashlib.md5(wrapped[32:]).digest() != wrapped[16:32]:
        raise ValueError('Menu artwork integrity')
    return ChannelArchive(decompress_lz77(wrapped[32:]))


def _wrap(archive):
    from libWiiPy.archive import decompress_lz77
    raw = archive.compact()
    payload = b'LZ77' + compress_lz10(raw)
    if decompress_lz77(payload) != raw:
        raise ValueError('Menu artwork compression')
    return b'IMD5' + len(payload).to_bytes(4, 'big') + bytes(8) + hashlib.md5(payload).digest() + payload, len(raw)


def banner_member(us_content0, overlap):
    """meta/banner.bin of the US WiiLink channel -> Korean block-face title (v33 recipe, given overlap)."""
    load_library()
    archive = _unwrap(ChannelArchive(us_content0[0x640:]), 'meta/banner.bin')
    layout_name = 'arc/blyt/banner.brlyt'
    layout = archive.get(layout_name); sections = layout_sections(layout)
    for i, s in enumerate(sections):
        if s[:4] == b'grp1' and s[8:24].split(b'\0')[0] == b'ENG':
            s = bytearray(s); s[8:24] = b'KOR' + bytes(13); sections[i] = bytes(s)
    archive = ChannelArchive(archive.replace(layout_name, rebuild_layout(layout, sections)))
    archive = mv.animated_korean_title_v20(archive, FONT, overlap=overlap, renderer=mv._clean_syllable, **BANNER)
    for ch, texture in wm.TEXTURES.items():
        path = next(p for p in archive.files if p.endswith('/' + texture)); raw = archive.get(path)
        archive = ChannelArchive(archive.replace(path, ktpl.encode(raw, 0, wm.syllable(ch, ktpl.decode(raw, 0).size))))
    return _wrap(ChannelArchive(archive.compact()))


def icon_member(parent_content0, image):
    """The parent's meta/icon.bin with only the wordmark texture replaced (RGB5A3)."""
    load_library()
    before = _unwrap(ChannelArchive(parent_content0[0x640:]), 'meta/icon.bin')
    after = ChannelArchive(before.replace(ICON_TEXTURE, encode_rgb5a3(image)))
    if set(after.files) != set(before.files) or any(after.get(p) != before.get(p) for p in before.files if p != ICON_TEXTURE):
        raise ValueError('Icon change escaped the wordmark texture')
    return _wrap(after)


def content0(parent_content0, us_content0, overlap=0, icon=None):
    """v33 content 0 -> v34: banner.bin rebuilt with `overlap`, icon.bin wordmark = icon_image()."""
    outer = ChannelArchive(parent_content0[0x640:]); prefix = bytearray(parent_content0[:0x640])
    members = {'meta/banner.bin': banner_member(us_content0, overlap),
               'meta/icon.bin': icon_member(parent_content0, icon if icon is not None else icon_image())}
    for name, (wrapped, size) in members.items():
        outer = ChannelArchive(outer.replace(name, wrapped))
        struct.pack_into('>I', prefix, 0x40 + (0x50 if 'banner' in name else 0x4c), size)
    prefix[0x630:0x640] = bytes(16); prefix[0x630:0x640] = hashlib.md5(prefix[0x40:0x640]).digest()
    return bytes(prefix) + outer.compact(), {n: s for n, (_, s) in members.items()}

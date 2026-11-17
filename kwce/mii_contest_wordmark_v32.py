"""Revision 32: banner '콘테스트 채널' in a heavy block face (user choice B, 2026-11-16).

The native banner letters ("Check ... Out Channel") are a very heavy, wide, square face with
slit counters, black with a white outline. Each of the six Hangul syllables is built from
rectangles and a few diagonals on a 100x100 grid with the same weight, then given the same
white outline and thin dark rim as before. Only the six banner letter textures change (same
size and format); the 'Mii' logo, layouts, animations and the icon texture are untouched.
"""
import hashlib, struct
from .channels import ChannelArchive, load_library, compress_lz10
from . import tpl

TEXTURES = {'콘': 'st_alf_capC_00.tpl', '테': 'st_alf_capO_00.tpl', '스': 'st_alf_capR_00.tpl',
            '트': 'st_alf_a_00.tpl', '채': 'st_alf_c_00.tpl', '널': 'st_alf_d_00.tpl'}
# ('r', x0, y0, x1, y1) rectangles and ('p', x, y, ...) polygons; stroke 16-17, slits 4-7.
BLOCK = {
 '콘': [('r', 0, 0, 100, 16), ('r', 83, 0, 100, 40), ('r', 0, 23, 100, 40), ('r', 41, 40, 59, 52), ('r', 0, 49, 100, 66), ('r', 0, 72, 17, 100), ('r', 0, 84, 100, 100)],
 '테': [('r', 0, 0, 17, 100), ('r', 0, 0, 54, 17), ('r', 0, 41, 66, 58), ('r', 0, 83, 54, 100), ('r', 64, 0, 79, 100), ('r', 85, 0, 100, 100)],
 '스': [('p', 40, 0, 60, 0, 60, 14, 22, 68, 0, 68, 0, 60), ('p', 40, 0, 60, 0, 100, 60, 100, 68, 78, 68, 40, 14), ('r', 0, 82, 100, 100)],
 '트': [('r', 0, 0, 17, 66), ('r', 0, 0, 100, 16), ('r', 0, 25, 100, 41), ('r', 0, 50, 100, 66), ('r', 0, 82, 100, 100)],
 '채': [('r', 14, 0, 42, 12), ('r', 0, 17, 56, 33), ('p', 19, 33, 37, 33, 37, 50, 18, 100, 0, 100, 0, 88), ('p', 19, 33, 37, 33, 56, 88, 56, 100, 38, 100, 19, 50),
        ('r', 64, 0, 79, 100), ('r', 85, 0, 100, 100), ('r', 64, 41, 90, 58)],
 '널': [('r', 0, 0, 17, 56), ('r', 0, 40, 58, 56), ('r', 83, 0, 100, 58), ('r', 62, 19, 90, 35),
        ('r', 0, 62, 100, 72), ('r', 83, 62, 100, 86), ('r', 0, 76, 100, 86), ('r', 0, 76, 17, 100), ('r', 0, 90, 100, 100)],
}
OUTLINE, RIM, MARGIN, SS = 2.5, 1.0, 1.0, 8


def syllable(ch, size):
    """RGBA tile: black block body, white outline, thin dark rim, inside `size` with a 1 px margin."""
    load_library(); from PIL import Image, ImageDraw, ImageFilter
    w, h = size; inset = OUTLINE + RIM + MARGIN
    bw, bh = (w - 2 * inset) * SS, (h - 2 * inset) * SS; ox, oy = inset * SS, inset * SS
    body = Image.new('L', (w * SS, h * SS), 0); d = ImageDraw.Draw(body)
    for s in BLOCK[ch]:
        if s[0] == 'r': d.rectangle([ox + s[1] * bw / 100, oy + s[2] * bh / 100, ox + s[3] * bw / 100 - 1, oy + s[4] * bh / 100 - 1], fill=255)
        else: d.polygon([(ox + s[i] * bw / 100, oy + s[i + 1] * bh / 100) for i in range(1, len(s), 2)], fill=255)
    def grow(mask, px):
        r = round(px * SS); return mask.filter(ImageFilter.MaxFilter(2 * r + 1))
    white = grow(body, OUTLINE); rim = grow(body, OUTLINE + RIM)
    big = Image.new('RGBA', body.size, (0, 0, 0, 0))
    big.paste((40, 40, 40, 255), (0, 0), rim); big.paste((255, 255, 255, 255), (0, 0), white); big.paste((0, 0, 0, 255), (0, 0), body)
    return big.resize(size, Image.Resampling.LANCZOS)


def banner(content):
    from libWiiPy.archive import decompress_lz77
    outer = ChannelArchive(content[0x640:]); prefix = bytearray(content[:0x640]); name = 'meta/banner.bin'
    wrapped = outer.get(name)
    if wrapped[:4] != b'IMD5' or hashlib.md5(wrapped[32:]).digest() != wrapped[16:32]: raise ValueError('Mii Contest banner integrity')
    before = ChannelArchive(decompress_lz77(wrapped[32:])); archive = before; touched = []
    for ch, texture in TEXTURES.items():
        path = next(p for p in archive.files if p.endswith('/' + texture)); raw = archive.get(path)
        new = tpl.encode(raw, 0, syllable(ch, tpl.decode(raw, 0).size))
        if len(new) != len(raw): raise ValueError('Letter texture size changed')
        archive = ChannelArchive(archive.replace(path, new)); touched.append(path)
    if any(archive.get(p) != before.get(p) for p in before.files if p not in touched): raise ValueError('Unrelated banner resource changed')
    raw = archive.compact(); payload = b'LZ77' + compress_lz10(raw)
    outer = ChannelArchive(outer.replace(name, b'IMD5' + len(payload).to_bytes(4, 'big') + bytes(8) + hashlib.md5(payload).digest() + payload))
    struct.pack_into('>I', prefix, 0x40 + 0x50, len(raw))
    out = bytearray(bytes(prefix) + outer.compact())
    out[0x630:0x640] = bytes(16); out[0x630:0x640] = hashlib.md5(out[0x40:0x640]).digest()
    return bytes(out), dict(file=name, textures=touched, style='block', outline=OUTLINE, rim=RIM)

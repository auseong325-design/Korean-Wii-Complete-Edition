"""Food hardware-v15: 음식 / 배달 / 채널 wordmark in Noto Sans CJK KR Black (user choice B, 2026-11-16).

The previous wordmark thickened Round Gothic B until the final consonants of 달 and 널
closed up. The six syllable tiles of the banner and of the icon are redrawn with one font
size and baseline per archive, in the tile's own palette colour. Tile sizes, palettes,
formats, pane positions, animations and every other resource stay byte-identical.
"""
import hashlib, struct
from pathlib import Path
from .channels import ChannelArchive, load_library
from . import food_menu_art as fm

FONT = Path('/usr/share/fonts/noto-cjk/NotoSansCJK-Black.ttc')
FONT_SHA256 = '3cffb10242b4b7e6edd439ebf3bd7e392345525e093ea08149e0a0158a1b5151'
FONT_INDEX = 1
PAD = 3 / 58          # free margin as a fraction of the tile


def masks(size):
    """Seven L masks (tile 3 blank) for a square tile of `size` pixels."""
    from PIL import Image, ImageDraw, ImageFont
    if hashlib.sha256(FONT.read_bytes()).hexdigest() != FONT_SHA256: raise ValueError('Pinned Noto Sans CJK Black differs')
    S = 8; n = size * S; text = [c for c in fm.WORD if c]; limit = n - 2 * PAD * n
    for px in range(n + 64, 40, -4):
        face = ImageFont.truetype(str(FONT), px, index=FONT_INDEX); boxes = [face.getbbox(c) for c in text]
        top = min(b[1] for b in boxes); bottom = max(b[3] for b in boxes)
        if max(b[2] - b[0] for b in boxes) <= limit and bottom - top <= limit: break
    else: raise ValueError('Wordmark does not fit its tiles')
    out = []
    for c in fm.WORD:
        layer = Image.new('L', (n, n), 0)
        if c:
            l, _, r, _ = face.getbbox(c)
            ImageDraw.Draw(layer).text(((n - (r - l)) / 2 - l, (n - (bottom - top)) / 2 - top), c, font=face, fill=255)
        out.append(layer.resize((size, size), Image.Resampling.LANCZOS))
    return out


def wordmark(content):
    load_library(); from libWiiPy.archive import decompress_lz77
    from .food_banner import _imet_md5, MD5_AT
    if content[0x80:0x84] != b'IMET' or _imet_md5(content) != content[MD5_AT:MD5_AT + 16]: raise ValueError('Food banner IMET identity')
    outer = ChannelArchive(content[0x640:]); prefix = bytearray(content[:0x640]); records = []
    for spec in (fm.BANNER, fm.ICON):
        wrapped = outer.get(spec['member'])
        if wrapped[:4] != b'IMD5' or hashlib.md5(wrapped[32:]).digest() != wrapped[16:32]: raise ValueError('Food menu art integrity')
        before = ChannelArchive(decompress_lz77(wrapped[32:])); archive = before; touched = []
        paths = ['arc/timg/' + n + '.tpl' for n in spec['textures']]
        sizes = {fm.texture_records(before.get(p))[0]['width'] for i, p in enumerate(paths) if fm.WORD[i]}
        heights = {fm.texture_records(before.get(p))[0]['height'] for i, p in enumerate(paths) if fm.WORD[i]}
        if len(sizes) != 1 or sizes != heights: raise ValueError('Wordmark tiles are not one square size')
        for path, ch, mask in zip(paths, fm.WORD, masks(sizes.pop())):
            if not ch: continue
            raw = before.get(path); new = fm.encode_ci(raw, 0, fm._ramp(raw, mask))
            if len(new) != len(raw): raise ValueError('Tile size changed')
            archive = ChannelArchive(archive.replace(path, new)); touched.append(path)
        if any(archive.get(p) != before.get(p) for p in before.files if p not in touched): raise ValueError('Unrelated menu art changed')
        raw, wrapped = fm._wrap(archive)
        outer = ChannelArchive(outer.replace(spec['member'], wrapped))
        struct.pack_into('>I', prefix, spec['size_at'], len(raw)); records.append(dict(member=spec['member'], tiles=touched))
    out = bytearray(bytes(prefix) + outer.compact()); out[MD5_AT:MD5_AT + 16] = _imet_md5(out)
    return bytes(out), records

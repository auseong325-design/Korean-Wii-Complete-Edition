"""Revision 62/63: '의' '방' in Noto Sans CJK KR Black, 6% narrower (user choice K, 2026-11-16).

Only the four Hangul wordmark places are redrawn: banner No/Ma, icon No/Ma, title scene
Title_Logo_No/Ma and the 'Wii' transition texture. Texture sizes, formats, layouts,
animations and the native Wii letters are unchanged, so the glyphs sit exactly where the
revision 56-60 wordmark did (one font size and baseline for both syllables on a square
canvas, as wiiroom_wordmark_v36.letter_mask).
"""
import hashlib, struct
from pathlib import Path
from .channels import ChannelArchive, load_library, compress_lz10
from . import tpl

FONT = Path('/usr/share/fonts/noto-cjk/NotoSansCJK-Black.ttc')
FONT_SHA256 = '3cffb10242b4b7e6edd439ebf3bd7e392345525e093ea08149e0a0158a1b5151'
FONT_INDEX = 1          # Noto Sans CJK KR in the collection
NARROW = 0.94


def _font(size):
    from PIL import ImageFont
    if hashlib.sha256(FONT.read_bytes()).hexdigest() != FONT_SHA256: raise ValueError('Pinned Noto Sans CJK Black differs')
    return ImageFont.truetype(str(FONT), size, index=FONT_INDEX)


FIT = True    # False reproduces build-v62 (glyphs about a quarter too small; not used)


def _old_extent(n):
    """Ink box (top, bottom) of the revision 56-60 pair on an n x n canvas."""
    from .wiiroom_wordmark_v36 import letter_mask as old
    boxes = [old(c, (n, n)).point(lambda v: 255 if v > 127 else 0).getbbox() for c in ('의', '방')]
    return min(b[1] for b in boxes), max(b[3] for b in boxes)


def letter_mask(letter, size, canvas=64):
    load_library(); from PIL import Image, ImageDraw
    scale = 8; n = round(canvas * scale); px = round(canvas * .94 * scale); font = _font(px)
    boxes = [font.getbbox(c) for c in ('의', '방')]
    top = min(b[1] for b in boxes); bottom = max(b[3] for b in boxes); y = (n - (bottom - top)) / 2 - top
    if FIT:
        # Same ink height and vertical position as the wordmark it replaces.
        old_top, old_bottom = _old_extent(n)
        px = round(px * (old_bottom - old_top) / (bottom - top)); font = _font(px)
        boxes = [font.getbbox(c) for c in ('의', '방')]
        top = min(b[1] for b in boxes); y = old_top - top
    b = boxes[0 if letter == '의' else 1]; im = Image.new('L', (n, n))
    ImageDraw.Draw(im).text(((n - (b[2] - b[0])) / 2 - b[0], y), letter, font=font, fill=255)
    w = round(n * NARROW); narrow = Image.new('L', (n, n)); narrow.paste(im.resize((w, n), Image.Resampling.LANCZOS), ((n - w) // 2, 0))
    return narrow.resize(size, Image.Resampling.LANCZOS)


TIGHT = True  # False reproduces build-v64 (old pane positions: gaps wider than the chosen preview)


def ink_fractions(mask_fn):
    """{letter: (left, right)} ink edges as fractions of the square canvas."""
    out = {}
    for c in ('의', '방'):
        box = mask_fn(c, (512, 512)).point(lambda v: 255 if v > 127 else 0).getbbox()
        out[c] = (box[0] / 512, box[2] / 512)
    return out


def tight_targets(kind):
    """Pane centres for one letter gap (the native i-to-i gap) before and after '의', re-centred."""
    from .wiiroom_wordmark_v36 import BANNER_V56, ICON_V56, letter_mask as old_mask
    base, names, pane, stem, gap = ((BANNER_V56, ('W', 'Rect_a', 'Rect_b', 'No', 'Ma'), 80., 13., 13.) if kind == 'banner'
                                    else (ICON_V56, ('Pic_W', 'Pic_I1', 'Pic_I2', 'Pic_No', 'Pic_Ma'), 18., 3., 3.))
    new, old = ink_fractions(letter_mask), ink_fractions(old_mask)
    stem_right = base[names[2]][0] + stem / 2
    no = stem_right + gap - pane * new['의'][0] + pane / 2
    ma = no - pane / 2 + pane * new['의'][1] + gap - pane * new['방'][0] + pane / 2
    shift = ((base[names[4]][0] - pane / 2 + pane * old['방'][1]) - (ma - pane / 2 + pane * new['방'][1])) / 2
    targets = {n: (round(base[n][0] + shift, 2),) + base[n][1:] for n in names[:3]}
    targets[names[3]] = (round(no + shift, 2),) + base[names[3]][1:]
    targets[names[4]] = (round(ma + shift, 2),) + base[names[4]][1:]
    return targets


def letter_image(letter, size, inverted=False):
    from PIL import Image, ImageChops
    mask = letter_mask(letter, size)
    if inverted: mask = ImageChops.invert(mask)
    return Image.merge('RGBA', (mask, mask, mask, mask))


def _replace(archive, suffix, image_fn):
    path = next(p for p in archive.files if p.endswith(suffix)); raw = archive.get(path)
    new = tpl.encode(raw, 0, image_fn(tpl.decode(raw, 0)))
    if len(new) != len(raw): raise ValueError('Wordmark texture size changed: ' + suffix)
    return ChannelArchive(archive.replace(path, new)), path


def banner(content):
    """Content 0: banner and icon No/Ma textures."""
    from libWiiPy.archive import decompress_lz77
    outer = ChannelArchive(content[0x640:]); prefix = bytearray(content[:0x640]); record = []
    for name, names in (('meta/banner.bin', ('/timg/No.tpl', '/timg/Ma.tpl')), ('meta/icon.bin', ('/timg/Icon_Logo_No.tpl', '/timg/Icon_Logo_Ma.tpl'))):
        wrapped = outer.get(name)
        if wrapped[:4] != b'IMD5' or hashlib.md5(wrapped[32:]).digest() != wrapped[16:32]: raise ValueError('Room banner integrity')
        before = ChannelArchive(decompress_lz77(wrapped[32:])); archive = before; touched = []
        for suffix, letter in zip(names, ('의', '방')):
            archive, path = _replace(archive, suffix, lambda im, c=letter: letter_image(c, im.size, inverted=name.endswith('banner.bin')))
            touched.append(path)
        geometry_record = None
        if TIGHT:
            from .wiiroom_wordmark_v36 import geometry
            archive, geometry_record = geometry(archive, tight_targets('banner' if name.endswith('banner.bin') else 'icon'))
        if any(archive.get(p) != before.get(p) for p in before.files
               if p not in touched and not (TIGHT and p.endswith(('.brlyt', '.brlan')))): raise ValueError('Unrelated banner resource changed')
        raw = archive.compact(); payload = b'LZ77' + compress_lz10(raw)
        outer = ChannelArchive(outer.replace(name, b'IMD5' + len(payload).to_bytes(4, 'big') + bytes(8) + hashlib.md5(payload).digest() + payload))
        struct.pack_into('>I', prefix, 0x40 + (0x4c if name.endswith('icon.bin') else 0x50), len(raw))
        record.append(dict(file=name, textures=touched, geometry=geometry_record))
    body = outer.compact(); struct.pack_into('>I', prefix, 0x40 + 0x54, struct.unpack_from('>I', prefix, 0x40 + 0x54)[0])
    out = bytearray(bytes(prefix) + body)
    out[0x630:0x640] = bytes(16); out[0x630:0x640] = hashlib.md5(out[0x40:0x640]).digest()
    return bytes(out), record


def resources(content):
    """Content 2: title scene letters and the transition wordmark; size preserved by padding."""
    from .wiiroom_formats import decompress_lz11, compress_lz11_optimal
    from PIL import Image
    a = ChannelArchive(content); record = []
    title = 'layout/Title/Title_Scene.lex'; ar = ChannelArchive(decompress_lz11(a.get(title)))
    for suffix, letter in (('/Title_Logo_No.tpl', '의'), ('/Title_Logo_Ma.tpl', '방')):
        ar, path = _replace(ar, suffix, lambda im, c=letter: letter_image(c, im.size)); record.append(title + ':' + path)
    if TIGHT:
        from .wiiroom_wordmark_v36 import geometry, TITLE, letter_mask as old_mask
        new, old = ink_fractions(letter_mask), ink_fractions(old_mask); pane, gap = 64., 13.
        no = TITLE['Pic_Logo_No'][0] + pane * (old['의'][0] - new['의'][0])      # same ink-left edge as before
        ma = no - pane / 2 + pane * new['의'][1] + gap - pane * new['방'][0] + pane / 2
        ar, g = geometry(ar, {'Pic_Logo_No': (round(no, 2),) + TITLE['Pic_Logo_No'][1:], 'Pic_Logo_Ma': (round(ma, 2),) + TITLE['Pic_Logo_Ma'][1:]})
        record.append(dict(title_geometry=g))
    a = ChannelArchive(a.replace(title, compress_lz11_optimal(ar.compact())))
    wipe = 'layout/Wipe/Fade_White_Logo.lex'; ar = ChannelArchive(decompress_lz11(a.get(wipe)))
    def transition(native):
        if native.size != (324, 74): raise ValueError('Transition wordmark dimensions')
        im = Image.new('RGBA', native.size); im.paste(native.crop((0, 0, 145, 74)), (0, 0))   # native 'Wii' kept
        slots = {'의': 159, '방': 245}
        if TIGHT:
            from .wiiroom_wordmark_v36 import letter_mask as old_mask
            new, old = ink_fractions(letter_mask), ink_fractions(old_mask)
            slots['의'] = round(159 + 70 * (old['의'][0] - new['의'][0]))
            slots['방'] = round(slots['의'] + 70 * new['의'][1] + 13 - 70 * new['방'][0])
        for c, x in slots.items():
            im.paste((255, 255, 255, 255), (x, 2, x + 70, 72), letter_mask(c, (70, 70)))
        return im
    ar, path = _replace(ar, '/Title_Logo.tpl', transition); record.append(wipe + ':' + path)
    a = ChannelArchive(a.replace(wipe, compress_lz11_optimal(ar.compact())))
    out = a.compact()
    if len(out) > len(content): raise ValueError('Room resource archive exceeds its fixed size')
    return out + bytes(len(content) - len(out)), record

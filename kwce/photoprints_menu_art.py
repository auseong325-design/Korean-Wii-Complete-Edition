"""Korean Wii Menu icon and banner title for the Photo Prints Channel (content 0).

The Japanese title 'デジカメプリント(チャンネル)' exists only as baked pixels in five
textures of opening.bnr (content 0):

  meta/banner.bin  arc/timg/banner_Textcomp.tpl        CMPR   580x44  gloss colour  (pane `text`, map 0)
                   arc/timg/text_alfa.tpl              I4     580x44  title mask    (pane `text`, map 1)
                   arc/timg/banner_LogoText_normal.tpl RGB5A3 530x40  flat title    (pane `text`, map 2)
  meta/icon.bin    arc/timg/icon_LogoText_01.tpl       I4     328x40  one-line title (pane `digicame`)
                   arc/timg/icon_logo_text.tpl         I4     142x39  two-line title (pane `Picture_01`)

The three banner maps cover the same 522x40 pane with identity texture
coordinates, so the Korean title is drawn once in pane space and resampled to
each texture size (the maps stay aligned under the native RLMC blend). The
icon textures are tinted by the material's TEV colours; only their masks
change. Glyphs come from the console's own 'Wii-kr_Round Gothic B.ttf'. The
gloss colour per row, the flat colour and the background are measured from the
original textures themselves.

Every texture keeps its GX format, size and byte length, so both U8 archives
keep their layout; every other file (layouts, animations, pictures, the
'prints by FUJIFILM' credit) and sound.bin stay byte-identical. The IMET
header keeps its sizes; names are set by kwce.photoprints_banner and its MD5
recomputed. No keys, tickets or console data are read.
"""
import hashlib
import io
import struct

from .channels import ChannelArchive, compress_lz10, load_library
from .channel_texture import texture_records
from . import tpl

FONT_ENTRY = 'Wii-kr_Round Gothic B.ttf'
SS = 4                      # supersampling factor for glyph rendering
# Extra glyph weight in supersampled pixels (SS=4 -> 1 unit = 0.25 texture px),
# per title texture; the Japanese title is a heavy display face.
# Chosen on the before/after sheet: the 18 px two-line icon stays legible ('털').
STROKES = {'banner': 5, 'icon_line': 4, 'icon_two_lines': 2}
MIN_CONDENSE = 0.85         # same lower bound as the channel's text fit

BANNER_TITLE = '디지털 카메라 프린트 채널'
ICON_TITLE = '디지털 카메라 프린트'
ICON_TWO_LINES = ('디지털 카메라', '프린트 채널')

BANNER_PANE = (522, 40)
BANNER_TEXTURES = ('arc/timg/banner_Textcomp.tpl', 'arc/timg/text_alfa.tpl', 'arc/timg/banner_LogoText_normal.tpl')
ICON_TEXTURES = ('arc/timg/icon_LogoText_01.tpl', 'arc/timg/icon_logo_text.tpl')
EXPECTED = {  # path: (GX format, width, height)
    'arc/timg/banner_Textcomp.tpl': (14, 580, 44), 'arc/timg/text_alfa.tpl': (0, 580, 44),
    'arc/timg/banner_LogoText_normal.tpl': (5, 530, 40),
    'arc/timg/icon_LogoText_01.tpl': (0, 328, 40), 'arc/timg/icon_logo_text.tpl': (0, 142, 39)}
# Rim of the gloss fill: share of the fill colour at mask depth 1 and 2 (measured
# on the original: depth 1 ~0.7-0.8, depth 2 ~0.9, depth >= 3 full fill).
RIM = {1: 0.75, 2: 0.9}

_FONT = {}


def _font_bytes():
    if 'ttf' not in _FONT:
        from .opera_font import KOREAN_SHARED
        _FONT['ttf'] = ChannelArchive(KOREAN_SHARED.read_bytes()).get(FONT_ENTRY)
    return _FONT['ttf']


def font_sha256():
    return hashlib.sha256(_font_bytes()).hexdigest()


def _font(px):
    from PIL import ImageFont
    return ImageFont.truetype(io.BytesIO(_font_bytes()), px)


def _line(text, px, stroke):
    """One line of white ink on black, cropped to its exact ink box (supersampled px)."""
    from PIL import Image, ImageDraw
    font = _font(px)
    l, t, r, b = ImageDraw.Draw(Image.new('L', (1, 1))).textbbox((0, 0), text, font=font, stroke_width=stroke)
    pad = 4 + stroke
    image = Image.new('L', (r - l + 2 * pad, b - t + 2 * pad), 0)
    ImageDraw.Draw(image).text((pad - l, pad - t), text, font=font, fill=255, stroke_width=stroke, stroke_fill=255)
    return image.crop(image.getbbox())


def _fit(lines, box_w, box_h, stroke, min_condense=MIN_CONDENSE):
    """Largest common size whose tallest line fits box_h; condense (>= min_condense) to fit box_w."""
    for px in range(2 * box_h, 7, -1):
        images = [_line(text, px, stroke) for text in lines]
        if max(i.height for i in images) > box_h:
            continue
        condense = min(1.0, box_w / max(i.width for i in images))
        if condense >= min_condense:
            return px, condense, images
    raise ValueError(f'Korean title does not fit: {lines!r}')


def title_mask(design, rows, *, stroke):
    """Coverage mask (mode L) at design*SS; rows = [(text, (x0, y0, x1, y1))] in design pixels.

    All rows share one glyph size and one horizontal condense; each row's ink is
    centred on its box."""
    from PIL import Image, ImageChops
    w, h = design
    box_w = min(b[2] - b[0] for _, b in rows) * SS
    box_h = min(b[3] - b[1] for _, b in rows) * SS
    px, condense, images = _fit([text for text, _ in rows], box_w, box_h, stroke)
    canvas = Image.new('L', (w * SS, h * SS), 0)
    for (_, (x0, y0, x1, y1)), image in zip(rows, images):
        if condense < 1:
            image = image.resize((max(1, round(image.width * condense)), image.height), Image.Resampling.BOX)
        layer = Image.new('L', canvas.size, 0)
        layer.paste(image, (round((x0 + x1) * SS / 2 - image.width / 2), round((y0 + y1) * SS / 2 - image.height / 2)))
        canvas = ImageChops.lighter(canvas, layer)
    return canvas, dict(font_px=round(px / SS, 2), condense=round(condense, 3))


def _down(mask, size):
    from PIL import Image
    return mask.resize(size, Image.Resampling.BOX)


def _grey(mask):
    """I4/I8 textures read intensity and alpha from the same channel."""
    from PIL import Image
    return Image.merge('RGBA', (mask, mask, mask, mask))


def _depth(mask, limit=3):
    """Per-pixel distance into the thresholded mask, capped at limit (0 = outside)."""
    from PIL import Image, ImageFilter
    inside = mask.point(lambda v: 255 if v >= 128 else 0)
    depth = Image.new('L', mask.size, 0)
    for d in range(1, limit + 1):
        depth = Image.composite(Image.new('L', mask.size, d), depth, inside)
        inside = inside.filter(ImageFilter.MinFilter(3))
    return depth


def _common(pixels):
    counts = {}
    for p in pixels:
        counts[p] = counts.get(p, 0) + 1
    return max(sorted(counts), key=lambda p: counts[p])


def gloss_style(comp, alfa):
    """(background colour, per-row fill colours) measured on the original gloss texture."""
    comp = comp.convert('RGB')
    w, h = comp.size
    depth = _depth(alfa.getchannel('A'))
    background = _common([comp.getpixel((x, y)) for y in range(h) for x in range(w) if not depth.getpixel((x, y))])
    rows = []
    for y in range(h):
        core = [comp.getpixel((x, y)) for x in range(w) if depth.getpixel((x, y)) >= 3]
        rows.append(tuple(round(sum(c[i] for c in core) / len(core)) for i in range(3)) if core else None)
    known = [y for y, c in enumerate(rows) if c]
    if not known:
        raise ValueError('Gloss texture has no measurable fill')
    rows = [rows[y] or rows[min(known, key=lambda k: (abs(k - y), k))] for y in range(h)]
    return background, rows


def _gloss(mask, background, rows):
    from PIL import Image
    w, h = mask.size
    depth = _depth(mask)
    image = Image.new('RGBA', (w, h))
    pixels = []
    for y in range(h):
        fill = rows[y]
        for x in range(w):
            share = 1.0 if depth.getpixel((x, y)) >= 3 else RIM.get(depth.getpixel((x, y)), 0.0)
            pixels.append(tuple(round(b + (f - b) * share) for b, f in zip(background, fill)) + (255,))
    image.putdata(pixels)
    return image


def _flat_colour(image):
    opaque = [p[:3] for p in image.getdata() if p[3] == 255]
    if not opaque:
        raise ValueError('Flat title has no opaque ink')
    return _common(opaque)


def _check(data, path):
    rec = texture_records(data)
    if len(rec) != 1 or (rec[0]['format'], rec[0]['width'], rec[0]['height']) != EXPECTED[path]:
        raise ValueError(f'Photo Prints title texture identity: {path}')


def banner_textures(archive):
    """{path: new TPL bytes} for the banner title maps of meta/banner.bin."""
    from PIL import Image
    for path in BANNER_TEXTURES:
        _check(archive.get(path), path)
    comp_raw, alfa_raw, flat_raw = (archive.get(p) for p in BANNER_TEXTURES)
    background, rows = gloss_style(tpl.decode(comp_raw, 0), tpl.decode(alfa_raw, 0))
    flat = _flat_colour(tpl.decode(flat_raw, 0))
    w, h = BANNER_PANE
    mask, fit = title_mask(BANNER_PANE, [(BANNER_TITLE, (2, 1, w - 2, h - 1))], stroke=STROKES['banner'])
    m580, m530 = _down(mask, (580, 44)), _down(mask, (530, 40))
    flat_image = Image.new('RGBA', (530, 40), flat + (255,))
    flat_image.putalpha(m530)
    out = {BANNER_TEXTURES[0]: tpl.encode(comp_raw, 0, _gloss(m580, background, rows)),
           BANNER_TEXTURES[1]: tpl.encode(alfa_raw, 0, _grey(m580)),
           BANNER_TEXTURES[2]: tpl.encode(flat_raw, 0, flat_image)}
    return out, dict(text=BANNER_TITLE, pane=list(BANNER_PANE), fit=fit, gloss_background=list(background),
                     flat_colour=list(flat), maps=list(BANNER_TEXTURES))


def icon_textures(archive):
    """{path: new TPL bytes} for the two icon title masks of meta/icon.bin."""
    for path in ICON_TEXTURES:
        _check(archive.get(path), path)
    one_raw, two_raw = (archive.get(p) for p in ICON_TEXTURES)
    one, fit_one = title_mask((328, 40), [(ICON_TITLE, (2, 1, 326, 39))], stroke=STROKES['icon_line'])
    two, fit_two = title_mask((142, 39), [(ICON_TWO_LINES[0], (1, 0, 141, 18)), (ICON_TWO_LINES[1], (1, 21, 141, 39))],
                              stroke=STROKES['icon_two_lines'])
    out = {ICON_TEXTURES[0]: tpl.encode(one_raw, 0, _grey(_down(one, (328, 40)))),
           ICON_TEXTURES[1]: tpl.encode(two_raw, 0, _grey(_down(two, (142, 39))))}
    return out, [dict(texture=ICON_TEXTURES[0], text=ICON_TITLE, fit=fit_one),
                 dict(texture=ICON_TEXTURES[1], text='\n'.join(ICON_TWO_LINES), fit=fit_two)]


def _rebuild_outer(outer):
    """U8 compaction, padded to 32 bytes like Nintendo's archive (its 24 tail bytes are unreferenced)."""
    data = outer.compact()
    return data + bytes(-len(data) % 32)


def korean_menu_art(content):
    """Return (content 0 bytes, record) with the Korean icon/banner title."""
    load_library()
    from libWiiPy.archive import decompress_lz77
    from .photoprints_banner import korean_banner_name
    if content[0x80:0x84] != b'IMET':
        raise ValueError('Photo Prints banner IMET missing')
    outer = ChannelArchive(content[0x640:])
    model = outer.compact()
    if content[0x640:0x640 + len(model)] != model or len(content) - 0x640 - len(model) >= 32:
        raise ValueError('Photo Prints banner archive layout model differs')
    prefix = bytearray(content[:0x640])
    records = {}
    for name, builder, size_at in (('meta/banner.bin', banner_textures, 0x40 + 0x50), ('meta/icon.bin', icon_textures, 0x40 + 0x4c)):
        wrapped = outer.get(name)
        if wrapped[:4] != b'IMD5' or hashlib.md5(wrapped[32:]).digest() != wrapped[16:32] or wrapped[32:36] != b'LZ77':
            raise ValueError(f'{name}: IMD5/LZ77 identity')
        raw = decompress_lz77(wrapped[32:])
        if struct.unpack_from('>I', prefix, size_at)[0] != len(raw):
            raise ValueError(f'{name}: IMET size field differs')
        before = ChannelArchive(raw)
        replacements, record = builder(before)
        archive = before
        for path, data in replacements.items():
            start = texture_records(before.get(path))[0]['offset']
            if len(data) != len(before.get(path)) or data[:start] != before.get(path)[:start]:
                raise ValueError(f'{path}: TPL header or length changed')
            archive = ChannelArchive(archive.replace(path, data))
        if set(archive.files) != set(before.files) or len(archive.data) != len(raw):
            raise ValueError(f'{name}: archive topology changed')
        changed = {p for p in before.files if archive.get(p) != before.get(p)}
        if changed != set(replacements):
            raise ValueError(f'{name}: change escaped the title textures')
        payload = b'LZ77' + compress_lz10(archive.data)
        if decompress_lz77(payload) != archive.data:
            raise ValueError(f'{name}: LZ77 roundtrip')
        wrapped = b'IMD5' + len(payload).to_bytes(4, 'big') + bytes(8) + hashlib.md5(payload).digest() + payload
        outer = ChannelArchive(outer.replace(name, wrapped))
        records[name] = dict(changed_textures=sorted(changed), unchanged_files=len(before.files) - len(changed),
                             raw_size=len(raw), compressed_size=len(payload), title=record)
    rebuilt, names = korean_banner_name(bytes(prefix) + _rebuild_outer(outer))
    if ChannelArchive(rebuilt[0x640:]).get('meta/sound.bin') != ChannelArchive(content[0x640:]).get('meta/sound.bin'):
        raise ValueError('sound.bin changed')
    return rebuilt, dict(font=FONT_ENTRY, font_sha256=font_sha256(), supersampling=SS, stroke_supersampled_px=dict(STROKES),
                         min_condense=MIN_CONDENSE, archives=records, imet=names,
                         layouts_and_animations_unchanged=True, fujifilm_credit_unchanged=True)


def nested(content, name):
    """Decompressed inner U8 of meta/banner.bin or meta/icon.bin."""
    load_library()
    from libWiiPy.archive import decompress_lz77
    return ChannelArchive(decompress_lz77(ChannelArchive(content[0x640:]).get(name)[32:]))


def contact_sheet(before, after, out_path, max_side=1600):
    """Before/after sheet: the five raw textures, then simulated panes over white."""
    from PIL import Image, ImageDraw
    rows = []

    def raw(content, name, path):
        image = tpl.decode(nested(content, name).get(path), 0)
        back = Image.new('RGBA', image.size, (64, 64, 64, 255))
        back.alpha_composite(image)
        return back

    def panes(content):
        banner, icon = nested(content, 'meta/banner.bin'), nested(content, 'meta/icon.bin')
        comp, alfa, flat = (tpl.decode(banner.get(p), 0) for p in BANNER_TEXTURES)
        gloss = comp.copy()
        gloss.putalpha(alfa.getchannel('A'))
        out = []
        for label, image in (('banner pane, gloss map', gloss.resize(BANNER_PANE, Image.Resampling.BILINEAR)),
                             ('banner pane, flat map', flat.resize(BANNER_PANE, Image.Resampling.BILINEAR))):
            back = Image.new('RGBA', BANNER_PANE, (255, 255, 255, 255))
            back.alpha_composite(image)
            out.append((label, back))
        for label, path, scale in (('icon one-line (x1)', ICON_TEXTURES[0], 1), ('icon two-line (x2)', ICON_TEXTURES[1], 2)):
            mask = tpl.decode(icon.get(path), 0).getchannel('A')
            tint = Image.new('RGBA', mask.size, (0, 161, 233, 255))
            tint.putalpha(mask)
            back = Image.new('RGBA', mask.size, (255, 255, 255, 255))
            back.alpha_composite(tint)
            out.append((label, back.resize((mask.width * scale, mask.height * scale), Image.Resampling.NEAREST)))
        return out

    for name, paths in (('meta/banner.bin', BANNER_TEXTURES), ('meta/icon.bin', ICON_TEXTURES)):
        for path in paths:
            rows.append((name.split('/')[1] + ' ' + path.rsplit('/', 1)[1], raw(before, name, path), raw(after, name, path)))
    for (label, b), (_, a) in zip(panes(before), panes(after)):
        rows.append((label, b, a))
    pad, label_h = 8, 14
    col = max(r[1].width for r in rows)
    width = min(max_side, pad * 3 + col * 2)
    height = sum(label_h + r[1].height + pad for r in rows) + pad
    if height > max_side:
        raise ValueError('Contact sheet exceeds the size budget')
    sheet = Image.new('RGBA', (width, height), (32, 32, 32, 255))
    draw = ImageDraw.Draw(sheet)
    y = pad
    draw.text((pad, 0), 'before (Japanese)', fill=(200, 200, 200, 255))
    draw.text((pad * 2 + col, 0), 'after (Korean)', fill=(200, 200, 200, 255))
    for label, b, a in rows:
        draw.text((pad, y), label, fill=(255, 220, 120, 255))
        y += label_h
        sheet.alpha_composite(b, (pad, y))
        sheet.alpha_composite(a, (pad * 2 + col, y))
        y += b.height + pad
    sheet.convert('RGB').save(out_path)
    return dict(path=str(out_path), size=list(sheet.size), rows=len(rows))

"""Korean images for the Kirby TV Channel HOME Menu: the operations-guide
JPEG (hbm/<set>/manual.jpg) and the guide frame word textures (content 8).

Lettering is redrawn with the console's own Korean Round Gothic font
(kwce.wiiroom_visual._font, read from the local 43K shared content). Icons,
table geometry and texture formats/sizes are kept.
"""
import io
from .channels import ChannelArchive, compress_lz10, load_library
from . import tpl


def _font(px):
    from .wiiroom_visual import _font as korean_font
    return korean_font(px)


def _fit(text, box, max_px, min_px=10):
    from PIL import Image, ImageDraw
    probe = ImageDraw.Draw(Image.new('L', (1, 1)))
    x0, y0, x1, y1 = box
    for px in range(max_px, min_px - 1, -1):
        font = _font(px)
        left, top, right, bottom = probe.textbbox((0, 0), text, font=font)
        if right - left <= x1 - x0 and bottom - top <= y1 - y0:
            return font, (left, top, right, bottom)
    raise ValueError(f'Korean text does not fit: {text!r}')


def _draw(draw, text, box, max_px, fill, align='left'):
    font, (left, top, right, bottom) = _fit(text, box, max_px)
    x0, y0, x1, y1 = box
    x = x0 - left if align == 'left' else x0 + ((x1 - x0) - (right - left)) / 2 - left
    y = y0 + ((y1 - y0) - (bottom - top)) / 2 - top
    draw.text((x, y), text, font=font, fill=fill)
    return font.size


def _runs(values):
    out, start = [], None
    for i, v in enumerate(values + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i))
            start = None
    return out


def korean_manual(jpeg, table, quality=92):
    """Redraw the English operations-guide JPEG with Korean lettering."""
    load_library()
    from PIL import Image, ImageDraw
    image = Image.open(io.BytesIO(jpeg))
    image.load()
    image = image.convert('RGB')
    w, h = image.size
    if (w, h) != (554, 256):
        raise ValueError('Unexpected manual image size')
    px = image.load()

    def blue(c):
        return c[2] > 150 and c[2] - c[0] > 80

    column = [blue(px[w - 12, y]) for y in range(h)]
    rows = [r for r in _runs(column) if r[1] - r[0] >= 20]
    if len(rows) != len(table['rows']):
        raise ValueError(f'Manual row count differs: {len(rows)}')
    draw = ImageDraw.Draw(image)
    # Title band above the table: plain black background.
    top = rows[0][0] - 4
    draw.rectangle((0, 0, w - 1, top - 1), fill=(0, 0, 0))
    sizes = [_draw(draw, table['title'][1], (8, 4, w - 8, top - 6), 20, (255, 255, 255))]
    for (y0, y1), (_, text) in zip(rows, table['rows']):
        # The row's top edge holds no lettering: it gives the cell extent and colour.
        line = [blue(px[x, y0 + 2]) for x in range(w)]
        x0, x1 = max(_runs(line), key=lambda r: r[1] - r[0])
        samples = sorted(px[x, y0 + 2] for x in range(x0 + 2, x1 - 2, 5))
        sample = samples[len(samples) // 2]
        draw.rectangle((x0 + 2, y0 + 2, x1 - 3, y1 - 3), fill=sample)
        sizes.append(_draw(draw, text, (x0 + 6, y0 + 4, x1 - 8, y1 - 4), 19, (255, 255, 255)))
    out = io.BytesIO()
    image.save(out, 'JPEG', quality=quality, subsampling=0, optimize=False)
    return out.getvalue(), dict(size=[w, h], rows=len(rows), font='Wii-kr Round Gothic B (console 43K shared)',
                                font_px=sizes, jpeg_quality=quality)


def _word_texture(original, text, align):
    from PIL import Image, ImageDraw
    w, h = original.size
    ink = original.getchannel('A').getbbox()
    if not ink:
        raise ValueError('Texture has no lettering')
    x0, y0, x1, y1 = ink
    height = y1 - y0
    box = (x0, max(0, y0 - 2), w - x0, min(h, y1 + 2)) if align == 'left' else (2, max(0, y0 - 2), w - 2, min(h, y1 + 2))
    mask = Image.new('L', (w, h), 0)
    size = _draw(ImageDraw.Draw(mask), text, box, max(10, int(height * 1.15)), 255, align)
    # I8 texture: intensity is used for colour and coverage alike.
    return Image.merge('RGBA', (mask, mask, mask, mask)), size


def korean_home_manual_frame(archive_lz, table):
    """Copy of HomeButton3/LZ77_homeBtn_nwm_eng.arc with Korean word textures."""
    load_library()
    from libWiiPy.archive import decompress_lz77
    from . import kirbytv_u8
    raw = decompress_lz77(archive_lz)
    archive = ChannelArchive(raw)
    replace, record = {}, {}
    for path, (source, target) in table.items():
        data = archive.get(path)
        image = tpl.decode(data, 0)
        align = 'center' if path.endswith('it_btn_01.tpl') else 'left'
        texture, size = _word_texture(image, target, align)
        replace[path] = tpl.encode(data, 0, texture)
        record[path] = dict(text=target, font_px=size, align=align)
    rebuilt = kirbytv_u8.edit(raw, replace=replace)
    packed = compress_lz10(rebuilt)
    if decompress_lz77(packed) != rebuilt:
        raise ValueError('HOME manual frame compression roundtrip failed')
    return packed, dict(textures=record, format='I8 (unchanged)', compression='LZ10 (same as source)')

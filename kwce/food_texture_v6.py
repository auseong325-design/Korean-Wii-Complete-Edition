"""Style-preserving Korean redraw of Food UI textures (content 2, build revision >= 6).

v4 decided the text colour from the average luminance of the opaque pixels, so
white headers with a thick black outline (title bars, `*_obi`) came out as plain
black text. Here every texture names its own style in
configs/food-textures-v6-ko.json:

  mode 'text'   text-only texture: replaced completely on transparency.
  mode 'button' button art kept; the Japanese lettering inside `erase` is
                painted over column by column (blend of the rows just above
                and below the box, i.e. the button's own interior), an optional
                inner frame is redrawn, then the Korean is drawn into `box`.

fill / fill_bottom (vertical gradient), outline + stroke, outer + outer_stroke
(second, outer outline) and align (left/center) describe the lettering. The
Korean Round Gothic B system font is fitted to the box. GX format, size and
offset are kept (palette formats keep their palette, see kwce.food_menu_art).
"""
from .food_menu_art import decode_any, encode_any, font


def _rgb(value):
    value = value.lstrip('#')
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _fit(text, box, stroke, spacing):
    from PIL import Image, ImageDraw
    x0, y0, x1, y1 = box; probe = ImageDraw.Draw(Image.new('L', (1, 1)))
    for px in range(max(y1 - y0, 8) + 6, 5, -1):
        face = font(px); gap = max(0, int(px * spacing))
        l, t, r, b = probe.multiline_textbbox((0, 0), text, font=face, stroke_width=stroke, spacing=gap, align='center')
        if r - l <= x1 - x0 and b - t <= y1 - y0:
            return face, px, gap, (l, t, r, b)
    raise ValueError('Korean texture text does not fit: %r' % text)


def _inpaint_columns(image, area):
    """Paint `area` with, per column, a vertical blend of the pixel rows just outside it."""
    x0, y0, x1, y1 = area; w, h = image.size; px = image.load()
    top, bottom = max(y0 - 1, 0), min(y1, h - 1)
    for x in range(max(x0, 0), min(x1, w)):
        a, b = px[x, top], px[x, bottom]
        for y in range(y0, y1):
            k = (y - top) / max(bottom - top, 1)
            px[x, y] = tuple(int(round(a[i] + (b[i] - a[i]) * k)) for i in range(4))


def restyle(payload, spec, index=0):
    from PIL import Image, ImageDraw
    original = decode_any(payload, index).convert('RGBA'); w, h = original.size
    mode = spec['mode']; text = spec['ko']
    if mode == 'text':
        base = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        box = tuple(spec.get('box', (1, 1, w - 1, h - 1)))
    elif mode == 'button':
        base = original.copy(); box = tuple(spec['box']); erase = tuple(spec.get('erase', box))
        if 'bg_at' in spec:                     # flat background: fill with one sampled colour
            colour = original.getpixel(tuple(spec['bg_at'])); draw = ImageDraw.Draw(base)
            draw.rounded_rectangle((erase[0], erase[1], erase[2] - 1, erase[3] - 1), radius=spec.get('erase_radius', 0), fill=colour)
            for x0, y0, x1, y1 in spec.get('erase_extra', []):
                draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=colour)
        else:
            _inpaint_columns(base, erase)
        frame = spec.get('frame')
        if frame:
            colour = original.getpixel(tuple(frame['colour_at']))
            ImageDraw.Draw(base).rounded_rectangle(frame['rect'], radius=frame['radius'], outline=colour, width=frame['width'])
    else:
        raise ValueError('Unknown v6 texture mode: ' + mode)
    stroke = spec.get('stroke', 0) if spec.get('outline') else 0
    outer = spec.get('outer_stroke', 0) if spec.get('outer') else 0
    face, px, gap, (l, t, r, b) = _fit(text, box, stroke + outer, spec.get('spacing', 0.12))
    x0, y0, x1, y1 = box
    x = x0 - l if spec.get('align', 'center') == 'left' else x0 + ((x1 - x0) - (r - l)) / 2 - l
    y = y0 + ((y1 - y0) - (b - t)) / 2 - t
    align = 'left' if spec.get('align', 'center') == 'left' else 'center'

    def layer(width_px):
        mask = Image.new('L', (w, h), 0)
        ImageDraw.Draw(mask).multiline_text((x, y), text, font=face, fill=255, spacing=gap, align=align,
                                            stroke_width=width_px, stroke_fill=255)
        return mask

    out = base
    for colour, width_px in ((spec.get('outer'), stroke + outer), (spec.get('outline'), stroke)):
        if colour and width_px:
            tint = Image.new('RGBA', (w, h), _rgb(colour) + (255,)); tint.putalpha(layer(width_px))
            out = Image.alpha_composite(out, tint)
    top_colour = _rgb(spec['fill']); bottom_colour = _rgb(spec.get('fill_bottom', spec['fill']))
    fill = Image.new('RGBA', (w, h)); fpx = fill.load(); ink_top, ink_bottom = y + t, y + b
    for yy in range(h):
        k = min(max((yy - ink_top) / max(ink_bottom - ink_top, 1), 0.0), 1.0)
        c = tuple(int(round(top_colour[i] + (bottom_colour[i] - top_colour[i]) * k)) for i in range(3)) + (255,)
        for xx in range(w):
            fpx[xx, yy] = c
    fill.putalpha(layer(0)); out = Image.alpha_composite(out, fill)
    new = encode_any(payload, index, out)
    decode_any(new, index)
    return new, dict(size=px, box=list(box), align=align)

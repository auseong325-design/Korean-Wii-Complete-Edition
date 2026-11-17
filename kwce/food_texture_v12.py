"""Korean redraw of Food baked-text textures whose lettering sits inside coloured art (revision >= 12).

mode 'retext' (configs/food-textures-v12-ko.json): the Japanese lettering is removed from inside the
shape and Korean is drawn in the stock lettering style; every pixel that is not lettering stays
byte-identical before encoding.

  1. bg     colours of the shape the lettering sits on: `bg` hex list and/or `bg_at` sample points
            (a gradient is covered by sampling it at a few heights); a pixel is background when its
            RGB is within `tol` of one of them and it is opaque.
  2. text   with `rects` (boxes strictly inside the shape's frame): the non-background pixels inside
            them. Without `rects` (irregular shapes: hearts, circles, speech bubbles): the
            non-background pixels a flood fill from the texture border through non-background
            pixels cannot reach, i.e. lettering enclosed by the shape colour; the shape's own
            frame/ring/shadow and the transparent margin are reachable and never touched.
  3. fill   each text pixel is repainted row-wise by linear interpolation between the nearest
            background pixels to its left and right (fallback: the nearest background pixel
            above/below, then bg[0]). `grow` first dilates the text mask (antialias/highlight rim).
            `erase_rows` / `erase_cols` rects (pill interiors with a gloss or gradient) are then
            repainted wholesale from the pixels just outside them, row- or column-wise.
            `barrier` colours (the lettering's own outline) stop that flood, so lettering whose
            outline touches the shape border is still enclosed.
  4. parts  one or more Korean runs drawn with kwce.food_texture_v6.restyle (button mode with an
            empty erase box, so restyle only draws): ko, box, fill, fill_bottom, outline + stroke,
            outer + outer_stroke, align, spacing - the same style keys as revision 6-11.

GX format, size and header are kept (palette textures keep their palette, kwce.food_menu_art).

Revision >= 13 (configs/food-textures-v13-ko.json) adds the `plate` option for the category photo tiles
(02_btn_menu_*): their lettering sits on a white plate whose frame is pixel-identical to a photo-free
sibling (02b_btn_menu_piz). Inside `plate.rect` every pixel that differs from that sibling (its own
lettering box `flat` painted with the plate colour) is lettering and takes the plate pixel back, so no
trace of the Japanese is left and nothing is interpolated; the photo, icon and frame outside `rect`
are never touched. Those parts are drawn in the stock tile style by `draw_shadowed` (fill, outline,
and a shadow = the outline shape moved by `shadow_offset`, fixed `size`, optional `scale_x`). Specs
without `plate` take the revision-12 path unchanged.
"""
import math

from .food_menu_art import decode_any, encode_any, font
from .food_texture_v6 import restyle, _rgb


def _close(p, refs, tol):
    return p[3] >= 200 and any(abs(p[0] - r[0]) + abs(p[1] - r[1]) + abs(p[2] - r[2]) <= tol for r in refs)


def _in(rects, x, y):
    return any(x0 <= x < x1 and y0 <= y < y1 for x0, y0, x1, y1 in rects)


def remove_lettering(image, refs, tol=60, rects=None, barrier=None, grow=0, barrier_rects=None, repaint='rows'):
    """Return (image without the lettering, number of repainted pixels).

    rects mode: text = non-background pixels inside `rects`.
    flood mode: walls = background pixels + `barrier`-coloured pixels (inside `barrier_rects` when given);
    text = non-background pixels the outside flood cannot reach (the lettering's outline and what it encloses).
    `grow` dilates the text mask (inside rects / barrier_rects / not-outside). Text pixels are repainted from
    anchor pixels (background when `refs` are given, otherwise any non-text opaque pixel): `repaint` 'rows'
    (left/right), 'cols' (above/below) or 'both' (both interpolations weighted by the shorter span)."""
    img = image.convert('RGBA').copy(); w, h = img.size; px = img.load()
    bg = [[bool(refs) and _close(px[x, y], refs, tol) for x in range(w)] for y in range(h)]
    outside = None
    if rects:
        text = [[not bg[y][x] and _in(rects, x, y) for x in range(w)] for y in range(h)]
    else:
        wall = [[bg[y][x] or (barrier is not None and _close(px[x, y], barrier, tol)
                              and (barrier_rects is None or _in(barrier_rects, x, y))) for x in range(w)] for y in range(h)]
        outside = [[False] * w for _ in range(h)]
        stack = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
        while stack:
            x, y = stack.pop()
            if not (0 <= x < w and 0 <= y < h) or outside[y][x] or wall[y][x]:
                continue
            outside[y][x] = True
            stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
        text = [[not bg[y][x] and not outside[y][x] for x in range(w)] for y in range(h)]
    if grow:                                              # take the lettering's antialias/highlight rim too
        if rects or barrier_rects:
            allowed = [[_in(rects or barrier_rects, x, y) for x in range(w)] for y in range(h)]
        else:
            allowed = [[not outside[y][x] for x in range(w)] for y in range(h)]
        text = _grow(text, grow, allowed)
    if refs:
        anchor = [[bg[y][x] and not text[y][x] for x in range(w)] for y in range(h)]
    else:
        anchor = [[not text[y][x] and px[x, y][3] >= 200 for x in range(w)] for y in range(h)]
    source = img.copy(); sp = source.load(); fixed = 0

    def lerp(a, b, k):
        return tuple(a[i] + (b[i] - a[i]) * k for i in range(4))

    for y in range(h):
        for x in range(w):
            if not text[y][x]:
                continue
            got = []
            if repaint in ('rows', 'both'):
                l = next((i for i in range(x - 1, -1, -1) if anchor[y][i]), None)
                r = next((i for i in range(x + 1, w) if anchor[y][i]), None)
                if l is not None and r is not None:
                    got.append((r - l, lerp(sp[l, y], sp[r, y], (x - l) / (r - l))))
                elif repaint == 'rows' and (l is not None or r is not None):
                    got.append((w, sp[l if l is not None else r, y]))
            if repaint in ('cols', 'both') or not got:
                u = next((j for j in range(y - 1, -1, -1) if anchor[j][x]), None)
                d = next((j for j in range(y + 1, h) if anchor[j][x]), None)
                if u is not None and d is not None:
                    got.append((d - u, lerp(sp[x, u], sp[x, d], (y - u) / (d - u))))
                elif not got and (u is not None or d is not None):
                    got.append((h, sp[x, u if u is not None else d]))
            if not got:
                got.append((1, tuple(refs[0]) + (255,) if refs else sp[x, y]))
            weight = sum(1.0 / span for span, _ in got)
            px[x, y] = tuple(int(round(sum(c[i] / span for span, c in got) / weight)) for i in range(4))
            fixed += 1
    return img, fixed


def _blend_rects(image, rects, rows):
    """Repaint every pixel inside each rect by linear interpolation between the pixels just outside
    it: left/right of the same row (rows=True) or above/below in the same column (rows=False).
    For pill/tile interiors whose colour only varies across the other axis (gloss, gradient)."""
    px = image.load(); w, h = image.size; n = 0
    for x0, y0, x1, y1 in rects:
        if not (0 < x0 < x1 < w and 0 < y0 < y1 < h):
            raise ValueError('Blend rect must lie strictly inside the texture')
        for y in range(y0, y1):
            for x in range(x0, x1):
                if rows:
                    a, b, k = px[x0 - 1, y], px[x1, y], (x - x0 + 1) / (x1 - x0 + 1)
                else:
                    a, b, k = px[x, y0 - 1], px[x, y1], (y - y0 + 1) / (y1 - y0 + 1)
                px[x, y] = tuple(int(round(a[i] + (b[i] - a[i]) * k)) for i in range(4)); n += 1
    return n


def _grow(mask, n, allowed):
    """Dilate a text mask n pixels (8-neighbourhood) into allowed pixels only."""
    h, w = len(mask), len(mask[0])
    for _ in range(n):
        mask = [[mask[y][x] or (allowed[y][x] and any(mask[j][i] for j in range(max(0, y - 1), min(h, y + 2))
                                                     for i in range(max(0, x - 1), min(w, x + 2))))
                 for x in range(w)] for y in range(h)]
    return mask


def plate_image(sibling, spec, index=0):
    """The lettering-free plate: the photo-free sibling texture (same frame) with its own lettering
    box(es) `flat` painted with `colour` (they lie on the plate's flat interior)."""
    from PIL import ImageDraw
    image = decode_any(sibling, index).convert('RGBA'); colour = _rgb(spec.get('colour', '#ffffff')) + (255,)
    for x0, y0, x1, y1 in spec.get('flat', []):
        ImageDraw.Draw(image).rectangle((x0, y0, x1 - 1, y1 - 1), fill=colour)
    return image


def replate(image, plate, rect):
    """Inside `rect` every pixel that differs from `plate` is lettering (fill, outline, shadow,
    antialias) and takes the plate pixel. Returns (image, restored pixel count)."""
    if image.size != plate.size:
        raise ValueError('Plate size differs from the texture')
    out = image.copy(); px = out.load(); pp = plate.load(); x0, y0, x1, y1 = rect; n = 0
    if not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height):
        raise ValueError('Plate rect outside the texture')
    for y in range(y0, y1):
        for x in range(x0, x1):
            if px[x, y] != pp[x, y]:
                px[x, y] = pp[x, y]; n += 1
    return out, n


def lettering_masks(text, size, stroke, gap=0, scale_x=1.0, weight=0):
    """(outline mask, fill mask) of `text`: each line drawn alone in Round Gothic B at `size` (outline =
    PIL stroke `stroke` around the glyph; the fill itself is grown by `weight`, so the visible outline
    is stroke - weight wide), cropped to its outline ink, condensed horizontally by `scale_x`, centred
    and stacked `gap` px apart (negative: the outlines of neighbouring lines overlap)."""
    from PIL import Image, ImageChops, ImageDraw
    face = font(size); lines = []
    if not 0 <= weight < stroke:
        raise ValueError('Lettering weight must stay inside the outline')
    for line in text.split('\n'):
        l, t, r, b = ImageDraw.Draw(Image.new('L', (1, 1))).textbbox((0, 0), line, font=face, stroke_width=stroke)
        ox, oy = 2 - math.floor(l), 2 - math.floor(t)      # integer origin (float strokes give float boxes)
        outer = Image.new('L', (math.ceil(r) + ox + 2, math.ceil(b) + oy + 2), 0); inner = Image.new('L', outer.size, 0)
        ImageDraw.Draw(outer).text((ox, oy), line, font=face, fill=255, stroke_width=stroke, stroke_fill=255)
        ImageDraw.Draw(inner).text((ox, oy), line, font=face, fill=255, stroke_width=weight, stroke_fill=255)
        ink = outer.getbbox(); outer = outer.crop(ink); inner = inner.crop(ink)
        if scale_x != 1.0:
            narrow = (max(1, int(round(outer.width * scale_x))), outer.height)
            outer = outer.resize(narrow, Image.LANCZOS); inner = inner.resize(narrow, Image.LANCZOS)
        lines.append((outer, inner))
    w = max(o.width for o, _ in lines); h = sum(o.height for o, _ in lines) + gap * (len(lines) - 1)
    if h <= 0:
        raise ValueError('Lettering gap swallows the lines')
    outer = Image.new('L', (w, h), 0); inner = Image.new('L', (w, h), 0); y = 0
    for o, i in lines:
        x = (w - o.width) // 2
        for mask, src in ((outer, o), (inner, i)):
            layer = Image.new('L', (w, h), 0); layer.paste(src, (x, y)); mask.paste(ImageChops.lighter(mask, layer))
        y += o.height + gap
    return outer, inner


def draw_shadowed(image, part):
    """Category-tile lettering in the stock style: shadow (the outline shape moved by `shadow_offset`)
    under the outline under the fill; the whole block (shadow included) centred in `box`."""
    from PIL import Image
    outer, inner = lettering_masks(part['ko'], part['size'], part.get('stroke', 3), part.get('gap', 0),
                                   part.get('scale_x', 1.0), part.get('weight', 0))
    dx, dy = part.get('shadow_offset', (2, 2))
    if dx < 0 or dy < 0:
        raise ValueError('Shadow offset must point right/down')
    x0, y0, x1, y1 = part['box']; bw, bh = outer.width + dx, outer.height + dy
    if bw > x1 - x0 or bh > y1 - y0:
        raise ValueError('Korean tile text does not fit its box: %r' % part['ko'])
    x = x0 + (x1 - x0 - bw) // 2; y = y0 + (y1 - y0 - bh) // 2; out = image
    for colour, mask, (ox, oy) in ((part['shadow'], outer, (dx, dy)), (part['outline'], outer, (0, 0)), (part['fill'], inner, (0, 0))):
        layer = Image.new('RGBA', image.size, _rgb(colour) + (0,)); alpha = Image.new('L', image.size, 0)
        alpha.paste(mask, (x + ox, y + oy)); layer.putalpha(alpha); out = Image.alpha_composite(out, layer)
    return out, dict(size=part['size'], block=[x, y, x + bw, y + bh])


def _retext_plate(payload, spec, index, plate):
    """rev >= 13 path of retext: exact plate restore, then draw_shadowed parts; one encode."""
    if plate is None:
        raise ValueError('retext plate mode needs the stock sibling texture')
    original = decode_any(payload, index).convert('RGBA')
    cleaned, fixed = replate(original, plate_image(plate, spec['plate'], index), spec['plate']['rect'])
    if not fixed:
        raise ValueError('retext found no lettering on the plate')
    parts = spec.get('parts') or [spec]; sizes = []; blocks = []
    for part in parts:
        cleaned, meta = draw_shadowed(cleaned, part); sizes.append(meta['size']); blocks.append(meta['block'])
    data = encode_any(payload, index, cleaned)
    decode_any(data, index)
    return data, dict(removed_pixels=fixed, sizes=sizes, parts=len(parts), blocks=blocks, plate=spec['plate']['from'])


def retext(payload, spec, index=0, plate=None):
    if spec.get('plate'):                                 # rev >= 13 category tiles (configs/food-textures-v13-ko.json)
        return _retext_plate(payload, spec, index, plate)
    original = decode_any(payload, index).convert('RGBA')
    refs = [_rgb(c) for c in spec.get('bg', [])] + [original.getpixel(tuple(p))[:3] for p in spec.get('bg_at', [])]
    cleaned, fixed = original, 0
    if refs:
        barrier = [_rgb(c) for c in spec['barrier']] if spec.get('barrier') else None
        cleaned, fixed = remove_lettering(original, refs, spec.get('tol', 60), spec.get('rects'), barrier,
                                          spec.get('grow', 0), spec.get('barrier_rects'), spec.get('repaint', 'rows'))
    elif spec.get('barrier'):                             # outlined lettering on a gradient/gloss: barrier-only flood
        cleaned, fixed = remove_lettering(original, [], spec.get('tol', 60), None, [_rgb(c) for c in spec['barrier']],
                                          spec.get('grow', 0), spec.get('barrier_rects'), spec.get('repaint', 'cols'))
    elif not (spec.get('erase_rows') or spec.get('erase_cols')):
        raise ValueError('retext needs bg colours, bg_at samples, a barrier or blend rects')
    fixed += _blend_rects(cleaned, spec.get('erase_rows', []), True) + _blend_rects(cleaned, spec.get('erase_cols', []), False)
    if not fixed:
        raise ValueError('retext found no enclosed lettering to remove')
    data = encode_any(payload, index, cleaned)
    parts = spec.get('parts') or [spec]
    sizes = []
    for part in parts:
        draw = {k: v for k, v in part.items()
                if k not in ('mode', 'parts', 'ja', 'rects', 'bg', 'bg_at', 'tol', 'barrier', 'grow', 'erase_rows',
                             'erase_cols', 'barrier_rects', 'repaint')}
        draw.update(mode='button', erase=[0, 0, 0, 0])
        data, meta = restyle(data, draw, index)
        sizes.append(meta['size'])
    decode_any(data, index)
    return data, dict(removed_pixels=fixed, sizes=sizes, parts=len(parts))

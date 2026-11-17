"""Korean versions of the Internet Channel manual pictures (revision 6+).

Each picture keeps its size, colour palette and PNG format. The English labels
are erased (each erase box is refilled from its border pixels), the Korean text
is drawn with the channel's Korean UI font (the Round Gothic B face that Opera
uses for the Korean pages) and the picture is mapped back onto its own original
palette without dithering, so every untouched pixel keeps its original colour.
A redraw is refused when a pixel outside the declared label areas changed.

Brand and site names, typed example text, key caps (Caps/Shift/Space, as on the
Korean build's keyboard) and the content of external web pages stay unchanged.
"""
import hashlib
import io

from .channels import ChannelArchive, load_library


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _font(size):
    from .internet_resources import _font as korean_ui_font
    return korean_ui_font(size)


def fill_box(image, box, mode='interp'):
    """Refill box [x0, y0, x1) x [y0, y1) in place.

    interp: average of the row blend (pixels left/right of the box) and the
    column blend (pixels above/below), which keeps soft gradients; row: every
    row takes the pixel left of the box; [r, g, b]: a solid colour."""
    x0, y0, x1, y1 = box
    w, h = image.size
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
        raise ValueError(f'Erase box outside the image: {box}')
    px = image.load()
    if mode == 'interp':
        if x0 < 1 or y0 < 1 or x1 >= w or y1 >= h:
            raise ValueError(f'Interpolated box needs a border ring: {box}')
        for y in range(y0, y1):
            left, right = px[x0 - 1, y], px[x1, y]
            ty = (y - y0 + 1) / (y1 - y0 + 1)
            for x in range(x0, x1):
                tx = (x - x0 + 1) / (x1 - x0 + 1)
                top, bottom = px[x, y0 - 1], px[x, y1]
                px[x, y] = tuple(round(((l + (r - l) * tx) + (t + (b - t) * ty)) / 2)
                                 for l, r, t, b in zip(left, right, top, bottom))
    elif mode == 'row':
        if x0 < 1:
            raise ValueError(f'Row fill needs a pixel left of the box: {box}')
        for y in range(y0, y1):
            colour = px[x0 - 1, y]
            for x in range(x0, x1):
                px[x, y] = colour
    elif isinstance(mode, list) and len(mode) == 3:
        for y in range(y0, y1):
            for x in range(x0, x1):
                px[x, y] = tuple(mode)
    else:
        raise ValueError(f'Unknown fill mode {mode!r}')


def _fit(draw, lines, size, max_width):
    for s in range(size, 7, -1):
        font = _font(s)
        if not max_width or max(draw.textlength(line, font=font) for line in lines) <= max_width:
            return font, s
    raise ValueError(f'Korean label does not fit: {lines!r}')


def draw_label(image, label):
    """Erase the label's boxes and draw its Korean text; returns the changed boxes."""
    load_library()
    from PIL import ImageDraw
    changed = []
    for box in label['erase']:
        fill_box(image, box, label.get('fill', 'interp'))
        changed.append(tuple(box))
    draw = ImageDraw.Draw(image)
    lines = label['text'].split('\n')
    font, size = _fit(draw, lines, label['size'], label.get('max_width'))
    x, y = label['at']
    anchor = label.get('anchor', 'ms')
    passes = 2 if label.get('bold') else 1  # bold: the same text again 1 px to the right
    for i, line in enumerate(lines):
        at = (x, y + i * label.get('pitch', 0))
        for k in range(passes):
            draw.text((at[0] + k, at[1]), line, font=font, fill=tuple(label['color']), anchor=anchor)
        l, t, r, b = draw.textbbox(at, line, font=font, anchor=anchor)
        changed.append((int(l) - 1, int(t) - 1, int(r) + passes, int(b) + 1))
    return changed, size


def _inside(boxes):
    return lambda x, y: any(a <= x < c and b <= y < d for a, b, c, d in boxes)


def _same_palette(source, image, changed):
    """Palette image with the source palette: untouched pixels keep their index;
    redrawn pixels take the index of their exact colour, else the nearest colour
    among the entries the source actually uses."""
    load_library()
    from PIL import Image
    palette = source.getpalette()
    indices = list(source.getdata())
    used = sorted(set(indices))
    colours = {i: tuple(palette[3 * i:3 * i + 3]) for i in used}
    exact = {}
    for i in used:
        exact.setdefault(colours[i], i)
    cache = {}

    def index(colour):
        if colour in exact:
            return exact[colour]
        if colour not in cache:
            cache[colour] = min(used, key=lambda i: (sum((p - q) ** 2 for p, q in zip(colours[i], colour)), i))
        return cache[colour]

    inside = _inside(changed)
    px = image.load()
    w = source.width
    out = [index(px[n % w, n // w]) if inside(n % w, n // w) else v for n, v in enumerate(indices)]
    result = Image.new('P', source.size)
    result.putpalette(palette)
    result.putdata(out)
    return result


def redraw(data, spec):
    """Return the Korean picture bytes and a record for one manual picture."""
    load_library()
    from PIL import Image
    if sha256(data) != spec['sha256']:
        raise ValueError('Manual picture differs from the pinned original')
    source = Image.open(io.BytesIO(data))
    source.load()
    if source.format != 'PNG' or source.mode != 'P' or 'transparency' in source.info:
        raise ValueError('Only opaque palette PNG manual pictures are supported')
    before = source.convert('RGB')
    image = before.copy()
    changed, sizes = [], []
    for label in spec['labels']:
        boxes, size = draw_label(image, label)
        changed += boxes
        sizes.append(size)
    out = _same_palette(source, image, changed)
    buf = io.BytesIO()
    out.save(buf, 'PNG', optimize=True)
    result = buf.getvalue()
    check = Image.open(io.BytesIO(result))
    if check.size != source.size or check.mode != 'P' or check.getpalette() != source.getpalette():
        raise ValueError('Redrawn manual picture changed its size, mode or palette')
    inside = _inside(changed)
    a, b = list(source.getdata()), list(check.getdata())
    w = source.width
    outside = sum(1 for i, (p, q) in enumerate(zip(a, b)) if p != q and not inside(i % w, i // w))
    if outside:
        raise ValueError(f'{outside} pixels outside the label areas changed')
    return result, dict(size=list(source.size), mode='P', labels=len(spec['labels']), font_px=sizes,
                        original_sha256=spec['sha256'], sha256=sha256(result), bytes=[len(data), len(result)])


def manual_images(archive, cfg):
    """archive: content-2 ChannelArchive; cfg: configs/internet-manual-images-v6-ko.json."""
    records = {}
    for name, spec in cfg['images'].items():
        new, records[name] = redraw(archive.get(name), spec)
        archive = ChannelArchive(archive.replace(name, new))
    for name in cfg['kept']:
        if name not in archive.files:
            raise ValueError(f'Kept manual picture missing: {name}')
    return archive, dict(redrawn=len(records), kept=sorted(cfg['kept']), images=records)

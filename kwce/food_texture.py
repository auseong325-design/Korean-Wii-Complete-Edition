"""Food channel texture audit: decode every TPL in content 2, build tiled
contact sheets (<=1600 px/side) to classify text-bearing textures, and redraw
Korean text into selected ones with the Wii system font. Only TEXT is replaced;
illustrative artwork is left untouched. Encoding keeps the original GX format,
size and offset (kwce.tpl.encode)."""
import json, sys, struct
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library, ChannelArchive
from kwce.tpl import decode, encode, texture_records
from kwce.channel_texture import texture_records as _rec

load_library()
from libWiiPy.archive import decompress_lz77


def unwrap(raw):
    if raw[:4] == b'LZ77':
        return decompress_lz77(raw)
    if raw[:1] == b'\x10' and len(raw) > 8:
        try:
            return decompress_lz77(b'LZ77' + raw)
        except Exception:
            return raw
    return raw


def iter_tpls(content2):
    a2 = ChannelArchive(content2)
    for arc in sorted(a2.files):
        if not arc.endswith('.arc'):
            continue
        inner = ChannelArchive(a2.get(arc))
        for f in sorted(inner.files):
            payload = unwrap(inner.get(f))
            if payload[:4] == bytes.fromhex('0020af30'):
                yield arc, f, payload


def contact_sheet(content2, arc_filter, out_png, thumb=96, cols=12, max_side=1600):
    from PIL import Image, ImageDraw, ImageFont
    tiles = []
    for arc, f, payload in iter_tpls(content2):
        if arc_filter not in arc:
            continue
        try:
            recs = texture_records(payload)
            img = decode(payload, 0).convert('RGBA')
        except Exception:
            continue
        tiles.append((f, recs[0], img))
    if not tiles:
        return None
    # checkerboard background to reveal alpha
    def cell(img):
        c = Image.new('RGBA', (thumb, thumb), (255, 255, 255, 255))
        d = ImageDraw.Draw(c)
        for y in range(0, thumb, 8):
            for x in range(0, thumb, 8):
                if (x // 8 + y // 8) % 2:
                    d.rectangle([x, y, x + 7, y + 7], fill=(205, 205, 205, 255))
        im = img.copy(); im.thumbnail((thumb - 2, thumb - 14))
        c.alpha_composite(im, ((thumb - im.width) // 2, 12 + (thumb - 14 - im.height) // 2))
        return c
    rows = (len(tiles) + cols - 1) // cols
    # cap rows per sheet so the side stays <= max_side
    per = max(1, (max_side // thumb))
    cols = min(cols, per); rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new('RGBA', (cols * thumb, rows * thumb), (40, 40, 40, 255))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype('arial.ttf', 9)
    except Exception:
        font = ImageFont.load_default()
    index = []
    for i, (f, rec, img) in enumerate(tiles):
        cx, cy = (i % cols) * thumb, (i // cols) * thumb
        sheet.alpha_composite(cell(img), (cx, cy))
        d.text((cx + 2, cy + 1), str(i), fill=(255, 220, 0), font=font)
        index.append(dict(cell=i, name=f, w=rec['width'], h=rec['height'], fmt=rec['format']))
    if sheet.width > max_side or sheet.height > max_side:
        sheet.thumbnail((max_side, max_side))
    sheet.convert('RGB').save(out_png)
    return index


def _text_color(img):
    op = [img.getpixel((x, y)) for x in range(img.width) for y in range(img.height)]
    op = [p for p in op if p[3] >= 128]
    if not op:
        return (255, 255, 255)
    lum = sum((p[0] * 299 + p[1] * 587 + p[2] * 114) // 1000 for p in op) / len(op)
    return (0, 0, 0) if lum < 128 else (255, 255, 255)


def redraw_label(payload, korean, renderer, index=0):
    """Replace a text-only label texture with Korean, same size/format/offset.

    When the original is light text, a black outline is added back so the
    label stays legible over the channel background (the stock labels carry one).
    """
    from PIL import Image, ImageFilter
    recs = texture_records(payload); r = recs[index]; w, h = r['width'], r['height']
    color = _text_color(decode(payload, index).convert('RGBA'))
    size = h - 4
    while size > 8:
        probe = Image.new('L', (w, h), 0)
        box = renderer.render(korean, size, probe)
        if box[2] - box[0] <= w - 6 and box[3] - box[1] <= h - 2:
            break
        size -= 1
    canvas = Image.new('L', (w, h), 0)
    renderer.render(korean, size, canvas)
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0)); px = out.load()
    outline = color == (255, 255, 255)
    halo = canvas.filter(ImageFilter.MaxFilter(3)) if outline else None
    for y in range(h):
        for x in range(w):
            fg = canvas.getpixel((x, y))
            if outline:
                ha = halo.getpixel((x, y))
                if fg >= 32:
                    px[x, y] = (255, 255, 255, fg)
                elif ha >= 32:
                    px[x, y] = (0, 0, 0, ha)
            else:
                px[x, y] = (color[0], color[1], color[2], fg)
    return encode(payload, index, out), dict(size=size, color=color, outline=outline)


def _korean_mask(renderer, korean, w, h, box, centre, start=None):
    """Fit Korean into `box` (x0,y0,x1,y1) and return an (L coverage, size).

    `start` caps the starting font size so a set of related tiles can share one
    maximum size (uniform look); it still shrinks further when a label overflows.
    """
    from PIL import Image
    x0, y0, x1, y1 = box
    size = (y1 - y0) - 2 if start is None else min(start, (y1 - y0) - 2)
    while size > 8:
        probe = Image.new('L', (w, h), 0)
        bb = renderer.render(korean, size, probe, centre=centre)
        if bb[2] - bb[0] <= (x1 - x0) - 4 and bb[3] - bb[1] <= (y1 - y0) - 2:
            break
        size -= 1
    canvas = Image.new('L', (w, h), 0)
    renderer.render(korean, size, canvas, centre=centre)
    return canvas, size


def redraw_header(payload, korean, renderer, index=0, margin=10):
    """Left-aligned text-only header (obi): full transparent replace, outlined."""
    from PIL import Image, ImageFilter
    r = texture_records(payload)[index]; w, h = r['width'], r['height']
    color = _text_color(decode(payload, index).convert('RGBA'))
    scale = (h - 4) / renderer.height
    lw = renderer.line_width(korean, scale)
    centre = (margin + min(lw, w - margin * 2) / 2, h / 2)
    canvas, size = _korean_mask(renderer, korean, w, h, (margin, 0, w, h), centre)
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0)); px = out.load()
    outline = color == (255, 255, 255)
    halo = canvas.filter(ImageFilter.MaxFilter(3)) if outline else None
    for y in range(h):
        for x in range(w):
            fg = canvas.getpixel((x, y))
            if outline:
                ha = halo.getpixel((x, y))
                if fg >= 32: px[x, y] = (255, 255, 255, fg)
                elif ha >= 32: px[x, y] = (0, 0, 0, ha)
            elif fg: px[x, y] = (color[0], color[1], color[2], fg)
    return encode(payload, index, out), dict(size=size, color=color, align='left')


def _label_bbox(img, x0):
    """Bounding box of outlined bright text (a bright pixel next to a dark one) at x>=x0."""
    w, h = img.size; px = img.load()
    def lum(p): return (p[0] * 299 + p[1] * 587 + p[2] * 114) // 1000 if p[3] >= 128 else -1
    xs, ys = [], []
    for y in range(1, h - 1):
        for x in range(x0, w - 1):
            if lum(px[x, y]) > 205 and any(0 <= lum(px[x + dx, y + dy]) < 95 for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                xs.append(x); ys.append(y)
    if len(xs) < 12:
        return None
    return (max(x0, min(xs) - 3), max(0, min(ys) - 3), min(w, max(xs) + 4), min(h, max(ys) + 4))


def redraw_tile(payload, korean, renderer, index=0, x0=0.40, size=None):
    """Localize a food-photo tile: cover the Japanese label (a fixed box on the
    right, where the stock text sits) with a dark rounded scrim, then fit white
    outlined Korean onto it. The photo outside the box is left byte-untouched;
    no character or photo is redrawn. `size` caps the font size so sibling tiles
    share one maximum (the category grid reads evenly instead of ragged)."""
    from PIL import Image, ImageDraw, ImageFilter
    r = texture_records(payload)[index]; w, h = r['width'], r['height']
    base = decode(payload, index).convert('RGBA')
    bx0 = int(w * x0); box = (bx0, 3, w - 2, h - 3)
    scrim = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(scrim).rounded_rectangle([box[0], box[1], box[2] - 1, box[3] - 1], radius=6, fill=(26, 20, 12, 232))
    base = Image.alpha_composite(base, scrim)
    centre = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    canvas, size = _korean_mask(renderer, korean, w, h, box, centre, start=size)
    halo = canvas.filter(ImageFilter.MaxFilter(5)); px = base.load()
    for y in range(h):
        for x in range(w):
            fg = canvas.getpixel((x, y))
            if fg >= 24:
                px[x, y] = (255, 255, 255, 255)
            elif halo.getpixel((x, y)) >= 24:
                px[x, y] = (0, 0, 0, 255)
    return encode(payload, index, base), dict(size=size, label_box=list(box))


def korean_font_renderer():
    from kwce.channel_korean_font import korean_shared_fonts
    fonts, _ = korean_shared_fonts()
    from kwce.wbf_text import WiiFontRenderer
    return WiiFontRenderer(ChannelArchive(fonts).get('wbf1.brfna'))


def audit(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    lib = load_library(); t = lib.title.Title()
    t.load_wad((ROOT / 'workspace/channels/food/originals/food-japan-v512.wad').read_bytes())
    c2 = t.get_content_by_index(2)
    manifest = {}
    for arc in ['DtestTitle', 'DtestWelcome', 'DtestCommon', 'DtestDialog', 'DtestOrder', 'sofkeybd']:
        idx = contact_sheet(c2, arc, out / f'{arc}.png')
        if idx is not None:
            manifest[arc] = idx
    (out / 'index.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    m = audit(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'workspace/private/food-sheets')
    for arc, idx in m.items():
        print(arc, len(idx), 'tpls')

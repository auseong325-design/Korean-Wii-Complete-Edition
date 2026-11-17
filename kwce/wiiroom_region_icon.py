"""Wii Room settings 'region' icon: the Japan silhouette (Option_Pic_Area.tpl, 25x26 IA4) redrawn as
the Korean peninsula in the same style (solid black, anti-aliased alpha edge).

The outline is a coarse hand-made coastline (lon/lat, ~40 points) plus Jeju; at 25x26 pixels finer
detail would vanish. Drawn 16x supersampled with an equirectangular projection (cos 38 deg).
"""
import math

PENINSULA = [  # clockwise from the Yalu mouth (lon, lat)
    (124.35, 40.05), (124.9, 40.45), (125.6, 40.8), (126.4, 41.35), (126.95, 41.75), (127.6, 41.45),
    (128.15, 41.6), (128.3, 42.0), (128.95, 42.05), (129.4, 42.45), (129.75, 42.95), (130.0, 42.85),
    (130.35, 42.6), (130.7, 42.3), (130.35, 42.15), (129.75, 41.75), (129.65, 41.35), (129.2, 40.75),
    (128.65, 40.3), (128.0, 40.0), (127.55, 39.75), (127.45, 39.25), (127.55, 39.05), (127.95, 38.9),
    (128.4, 38.45), (128.85, 37.85), (129.15, 37.5), (129.4, 37.0), (129.45, 36.4), (129.58, 36.05),
    (129.42, 35.6), (129.2, 35.25), (128.95, 35.05), (128.6, 34.85), (128.0, 34.8), (127.6, 34.65),
    (127.25, 34.45), (126.85, 34.4), (126.5, 34.3), (126.3, 34.6), (126.35, 35.05), (126.5, 35.55),
    (126.75, 35.95), (126.5, 36.35), (126.15, 36.65), (126.3, 36.95), (126.65, 37.3), (126.55, 37.65),
    (126.15, 37.75), (125.75, 37.95), (125.2, 37.85), (124.75, 38.1), (125.15, 38.55), (125.15, 38.9),
    (124.9, 39.2), (124.65, 39.55),
]
JEJU = ((126.55, 33.38), 0.42, 0.17)   # centre, half-width (lon), half-height (lat)


def draw(size=(25, 26), margin=0.5, supersample=16, bold=0.0, jeju_scale=1.0):
    from PIL import Image, ImageDraw
    k = math.cos(math.radians(38))
    pts = [(lon * k, -lat) for lon, lat in PENINSULA]
    (jx, jy), jw, jh = JEJU; jw *= jeju_scale; jh *= jeju_scale
    jeju = [((jx + jw * math.cos(a)) * k, -(jy + jh * math.sin(a))) for a in [i * math.pi / 16 for i in range(32)]]
    allp = pts + jeju
    x0, x1 = min(p[0] for p in allp), max(p[0] for p in allp)
    y0, y1 = min(p[1] for p in allp), max(p[1] for p in allp)
    w, h = size
    s = min((w - 2 * margin) / (x1 - x0), (h - 2 * margin) / (y1 - y0))
    ox = (w - (x1 - x0) * s) / 2; oy = (h - (y1 - y0) * s) / 2
    S = supersample
    big = Image.new('L', (w * S, h * S), 0); d = ImageDraw.Draw(big)
    tf = lambda p: (((p[0] - x0) * s + ox) * S, ((p[1] - y0) * s + oy) * S)
    d.polygon([tf(p) for p in pts], fill=255)
    d.polygon([tf(p) for p in jeju], fill=255)
    if bold:
        from PIL import ImageFilter
        r = max(1, int(round(bold * S))) | 1
        big = big.filter(ImageFilter.MaxFilter(r))
    alpha = big.resize((w, h), Image.LANCZOS)
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0)); img.putalpha(alpha)
    return img


TEXTURE = 'timg/Option_Pic_Area.tpl'
LEXES = ('layout/Option/Area_Btn.lex', 'layout/Option/Area_Btn_B.lex')
STYLE = dict(bold=1.0, jeju_scale=2.0)   # candidate B (2026-11-16)


def patch_content2(content2, style=STYLE):
    """Replace Option_Pic_Area.tpl in both settings button archives (LZ11 U8). Returns (bytes, record)."""
    import hashlib
    from .channels import ChannelArchive
    from .channel_texture import replace_ia4, texture_records
    from .wiiroom_formats import decompress_lz11, compress_lz11_optimal
    outer = ChannelArchive(content2); record = []
    image = draw(**style)
    for lex in LEXES:
        inner = ChannelArchive(decompress_lz11(outer.get(lex)))
        name = next(n for n in inner.files if n.endswith(TEXTURE))
        old = inner.get(name); r = texture_records(old)[0]
        if (r['width'], r['height'], r['format']) != (25, 26, 2): raise ValueError('Unexpected region icon texture')
        new = replace_ia4(old, 0, image)
        rebuilt = inner.replace(name, new)
        packed = compress_lz11_optimal(rebuilt)
        if decompress_lz11(packed) != rebuilt: raise ValueError('LZ11 roundtrip')
        outer = ChannelArchive(outer.replace(lex, packed))
        record.append(dict(archive=lex, texture=name, old_sha256=hashlib.sha256(old).hexdigest(), new_sha256=hashlib.sha256(new).hexdigest()))
    return outer.data, dict(style=style, textures=record)

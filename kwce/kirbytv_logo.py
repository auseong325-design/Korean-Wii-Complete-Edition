"""Korean '채널' lettering for the Kirby TV Channel logos (revision 8).

A Korean console shows the ENG logo assets: LocaleManager treats language 9
as English inside the SWF, and the Wii Menu banner/icon KOR groups are the
renamed ENG groups (kirbytv_banner). Those assets spell 'Channel'. Only that
word changes here; the Kirby wordmark, 'TV' and the TV screen stay Nintendo's
artwork, re-used from the same title.

Original pieces (WiiLink-patched Gumball2.12.RC-1.swf of the PAL v257 title):
  Channel_Logo_In (sprite 1817, first-entry logo): word 1785, shadow 1782 (188x66)
  small_LOGO_ENG  (sprite 1448, special-intro top-left logo): word 1406, shadow 1403 (80x30),
                  still image 1409 (144x88) shown from frame 55 on
  mc_logo         (sprite 1848, usual top-left logo of the episode-selection and settings
                  screens, revision 9): English frame image 1840 (162x104)
  Wii Menu banner arc/timg/Logo_English.tpl (208x127) = intro arrangement x0.6
  Wii Menu icon   arc/timg/ENG_channel.tpl  (49x18)
  Save-data banner banner/KR/KO/banner.tpl (192x64, opaque)

Style measured on 1785/1406: white body, navy rim (35,57,118) about 5% of the
word box height, a light-blue inner edge (118,184,228) on the lower left,
italic, baseline rising to the right; the shadow piece is the same silhouette
in (0,0,149) at alpha 65 (its sprite offsets it). The Korean word uses the
console's own 'Wii-kr_Round Gothic B' (rounded terminals like the original
lettering), emboldened with round joins.

Composite images (1409, banner, save banner) keep their original pixels
outside a feathered mask around the old and new word; inside it they take a
re-render of the logo arrangement from the SWF pieces with the Korean word.
"""
import hashlib
import math
import struct
import zlib

from .channels import ChannelArchive, load_library

NAVY = (35, 57, 118)
EDGE = (118, 184, 228)
WHITE = (255, 255, 255)
SHADOW = (0, 0, 149)
SHADOW_ALPHA = 65
WORD = '채널'
FONT_NAME = 'Wii-kr_Round Gothic B.ttf'
SS = 8

# Placement of the pieces in their sprites at the final frames (from the SWF timelines).
# (depth, 'bmp', bitmap id, matrix) | (depth, 'clip', shape id, inner matrix, outer matrix, clip depth)
I = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
INTRO = [
    (1, 'bmp', 1764, (1.0, 0.0, 0.0, 1.0, 298.0, -81.0)),
    (3, 'clip', 1774, I, (1.0, 0.0, 0.0, 1.0, 0.0, 490.0), 8),
    (4, 'bmp', 1768, (1.0, 0.0, 0.0, 1.0, 152.0, -105.0)),
    (9, 'bmp', 1778, (1.0, 0.0, 0.0, 1.0, 168.0, 13.6)),
    (11, 'bmp', 1771, (1.0, 0.0, 0.0, 1.0, 152.0, -110.0)),
    (13, 'clip', 1401, (2.379150390625, 0.0, 0.0, 2.3786163330078125, 0.0, 0.0), (1.0, 0.0, 0.0, 1.0, 295.45, -65.65), 17),
    (15, 'bmp', 1782, (1.0, 0.0, 0.0, 1.0, 276.0, 3.0)),
    (19, 'bmp', 1785, (1.0, 0.0, 0.0, 1.0, 272.0, -2.0)),
]
SMALL = [
    (1, 'bmp', 1384, (1.0, 0.0, 0.0, 1.0, 67.0, 24.0)),
    (3, 'clip', 1401, I, (1.0, 0.0, 0.0, 1.0, 66.65, 30.3), 7),
    (5, 'bmp', 1403, (1.0, 0.0, 0.0, 1.0, 57.0, 59.0)),
    (9, 'clip', 1387, I, (1.0, 0.0, 0.0, 1.0, 70.1, 26.1), 15),
    (13, 'bmp', 1389, (1.0, 0.0, 0.0, 1.0, 9.0, 14.0)),
    (17, 'bmp', 1398, (1.0, 0.0, 0.0, 1.0, 13.0, 64.0)),
    (19, 'bmp', 1392, (1.0, 0.0, 0.0, 1.0, 8.0, 10.0)),
    (21, 'bmp', 1406, (1.0, 0.0, 0.0, 1.0, 57.0, 57.0)),
]
INTRO_WORD, INTRO_SHADOW = 1785, 1782
SMALL_WORD, SMALL_SHADOW, SMALL_STILL = 1406, 1403, 1409
SMALL_STILL_BOX = (8.0, 12.0, 152.0, 100.0)          # placed at (8,12), 144x88
# Revision 9: the top-left logo of the episode-selection and settings screens is not small_LOGO_ENG
# but the instance mc_logo (sprite 1848): gotoAndStop(wiiLanguageCode), and language 9 is English
# inside the SWF, so frame 1 = shape 1841 = bitmap 1840 (162x104 JPEG3). small_LOGO_ENG is only
# attached by EpisodeSelectionScreen.addLogo on the special-intro path.
MC_LOGO_ENG = 1840
# 1840 = SMALL arrangement at target X = s * u + o (least-squares fit; residual outside the word
# mask is checked at build time)
MC_LOGO_FIT = (0.987, 0.4, 0.5)
# Wii Menu banner logo = intro arrangement scaled about 0.6 (least-squares fit: scale, x, y offset;
# residual outside the word mask is checked at build time)
BANNER_FIT = (0.599, -90.0, 67.0)
# Word styles: box size, rim/weight in final px, italic shear, baseline angle, tracking (em), margins
#   chosen from candidate sheets (workspace/private/rc6-work/W-Kirby-*.png): heavier strokes close
#   the counters of '널' (ㄹ) at banner size; a wider letterform fills the TV screen like 'Channel'.
STYLES = {
    'intro': dict(box=(188, 66), rim=3.4, weight=1.7, edge=1.4, shear=0.2, angle=-3.0, tracking=-0.03, stretch=1.32,
                  margin=(2, 2)),
    'small': dict(box=(80, 30), rim=1.6, weight=0.8, edge=0.7, shear=0.2, angle=-3.0, tracking=-0.03, stretch=1.32,
                  margin=(1, 1)),
    'icon': dict(box=(49, 18), rim=1.05, weight=0.15, edge=0.0, shear=0.16, angle=0.0, tracking=-0.02, stretch=1.25,
                 margin=(1, 0)),
}


def _pil():
    load_library()
    import PIL.Image
    return PIL


def round_gothic():
    """The console's Korean round gothic (bytes) and its sha256."""
    from .opera_font import KOREAN_SHARED
    raw = ChannelArchive(KOREAN_SHARED.read_bytes()).get(FONT_NAME)
    return raw, hashlib.sha256(raw).hexdigest()


# ------------------------------------------------------------------ SWF bitmaps

def _char_tags(fws):
    from . import kirbytv_swf as K
    out = {}
    for index, (code, pos, head, length) in enumerate(K.tags(fws)):
        if code in (2, 20, 21, 22, 32, 35, 36, 39, 83):
            out[struct.unpack_from('<H', fws, pos + head)[0]] = (index, code, pos + head, length)
    return out


def bitmap(fws, cid, chars=None):
    """RGBA image of a DefineBitsLossless2 / DefineBitsJPEG3 (colour premultiplied, clamped to alpha)."""
    import io
    _pil()
    from PIL import Image
    chars = chars or _char_tags(fws)
    index, code, at, length = chars[cid]
    payload = fws[at:at + length]
    if code == 36:
        fmt, w, h = struct.unpack_from('<BHH', payload, 2)
        if fmt != 5:
            raise ValueError('Unexpected lossless bitmap format')
        img = Image.frombytes('RGBA', (w, h), zlib.decompress(payload[7:]), 'raw', 'ARGB')
    elif code == 35:
        size = struct.unpack_from('<I', payload, 2)[0]
        jpeg = payload[6:6 + size]
        if jpeg[:4] == b'\xff\xd9\xff\xd8':
            jpeg = jpeg[4:]
        rgb = Image.open(io.BytesIO(jpeg)).convert('RGB')
        img = rgb.convert('RGBA')
        img.putalpha(Image.frombytes('L', rgb.size, zlib.decompress(payload[6 + size:])))
    else:
        raise ValueError(f'Character {cid} is not an alpha bitmap')
    return _clamp_premultiplied(img)


def _clamp_premultiplied(img):
    from PIL import Image, ImageChops
    r, g, b, a = img.split()
    return Image.merge('RGBA', [ImageChops.darker(c, a) for c in (r, g, b)] + [a])


def lossless2(cid, image):
    """DefineBitsLossless2 payload (format 5, premultiplied ARGB, deterministic zlib)."""
    if image.mode != 'RGBA':
        raise ValueError('Expected RGBA')
    image = _clamp_premultiplied(image)
    rgba = image.tobytes()
    argb = bytearray(len(rgba))
    argb[0::4], argb[1::4], argb[2::4], argb[3::4] = rgba[3::4], rgba[0::4], rgba[1::4], rgba[2::4]
    co = zlib.compressobj(9, zlib.DEFLATED, 15, 9)
    data = co.compress(bytes(argb)) + co.flush()
    return struct.pack('<HBHH', cid, 5, image.width, image.height) + data


def replace_bitmaps(fws, payloads):
    """Return FWS with the given character bitmaps replaced by DefineBitsLossless2 tags."""
    from . import kirbytv_swf as K
    chars = _char_tags(fws)
    listing = K.tags(fws)
    by_index = {}
    for cid, payload in payloads.items():
        index, code, at, length = chars[cid]
        if code not in (35, 36):
            raise ValueError(f'Character {cid} is not an alpha bitmap')
        by_index[index] = payload
    out = bytearray(fws[:K.header_end(fws)])
    for index, (code, pos, head, length) in enumerate(listing):
        if index in by_index:
            out += K.tag_bytes(36, by_index[index])
        else:
            out += fws[pos:pos + head + length]
    end = listing[-1][1] + listing[-1][2] + listing[-1][3]
    out += fws[end:]
    struct.pack_into('<I', out, 4, len(out))
    return bytes(out)


# ------------------------------------------------------------------ vector clip shapes

class _Bits:
    def __init__(self, data, at):
        self.data, self.pos = data, at * 8

    def u(self, n):
        v = 0
        for _ in range(n):
            v = v << 1 | (self.data[self.pos >> 3] >> (7 - (self.pos & 7))) & 1
            self.pos += 1
        return v

    def s(self, n):
        v = self.u(n)
        return v - (1 << n) if n and v >> (n - 1) else v

    def byte(self):
        return (self.pos + 7) // 8


def shape_contours(fws, cid, chars=None):
    """Closed contours (px) of a single solid-fill DefineShape used as a clip mask."""
    chars = chars or _char_tags(fws)
    index, code, at, length = chars[cid]
    if code != 2:
        raise ValueError('Clip shape is not a DefineShape')
    bits = _Bits(fws, at + 2)
    n = bits.u(5)
    [bits.s(n) for _ in range(4)]
    pos = bits.byte()
    fills = fws[pos]
    pos += 1
    for _ in range(fills):
        if fws[pos] != 0:
            raise ValueError('Clip shape fill is not solid')
        pos += 4
    if fws[pos] != 0:
        raise ValueError('Clip shape has line styles')
    pos += 1
    bits = _Bits(fws, pos)
    nf, nl = bits.u(4), bits.u(4)
    x = y = 0
    contours, current = [], None
    while True:
        if bits.u(1) == 0:
            flags = bits.u(5)
            if flags == 0:
                break
            if flags & 16:
                raise ValueError('Clip shape with new styles')
            if flags & 1:
                k = bits.u(5)
                x, y = bits.s(k), bits.s(k)
                current = [(x / 20, y / 20)]
                contours.append(current)
            if flags & 2:
                bits.u(nf)
            if flags & 4:
                bits.u(nf)
            if flags & 8:
                bits.u(nl)
        else:
            straight = bits.u(1)
            k = bits.u(4) + 2
            if straight:
                if bits.u(1):
                    dx, dy = bits.s(k), bits.s(k)
                elif bits.u(1):
                    dx, dy = 0, bits.s(k)
                else:
                    dx, dy = bits.s(k), 0
                x, y = x + dx, y + dy
                current.append((x / 20, y / 20))
            else:
                cx, cy = x + bits.s(k), y + bits.s(k)
                ax, ay = cx + bits.s(k), cy + bits.s(k)
                for i in range(1, 13):
                    t = i / 12
                    current.append((((1 - t) ** 2 * x + 2 * t * (1 - t) * cx + t * t * ax) / 20,
                                    ((1 - t) ** 2 * y + 2 * t * (1 - t) * cy + t * t * ay) / 20))
                x, y = ax, ay
    return contours


def _compose(a, b):
    """Matrix applying b first, then a; (a, b, c, d, tx, ty) as in SWF."""
    a1, b1, c1, d1, x1, y1 = a
    a2, b2, c2, d2, x2, y2 = b
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2, a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * x2 + c1 * y2 + x1, b1 * x2 + d1 * y2 + y1)


# ------------------------------------------------------------------ float premultiplied layers

def _math(fn, **images):
    from PIL import ImageMath
    return ImageMath.lambda_eval(lambda e: fn(e), **images)


def to_float(img):
    """Premultiplied RGBA image -> [r, g, b, a] float images in 0..1."""
    return [c.convert('F').point(lambda v: v / 255.0) for c in img.split()]


def premultiply(img):
    """Straight RGBA image -> premultiplied float channels."""
    r, g, b, a = [c.convert('F') for c in img.convert('RGBA').split()]
    af = a.point(lambda v: v / 255.0)
    return [_math(lambda e: e['c'] / 255.0 * e['a'], c=c, a=af) for c in (r, g, b)] + [af]


def to_premultiplied_image(chans):
    from PIL import Image
    return Image.merge('RGBA', [c.point(lambda v: v * 255.0 + 0.5).convert('L') for c in chans])


def to_straight_image(chans):
    from PIL import Image
    r, g, b, a = chans
    cols = [_math(lambda e: e['min'](e['c'] * 255.0 / e['max'](e['a'], 1e-6) + 0.5, 255.0), c=c, a=a) for c in (r, g, b)]
    alpha = a.point(lambda v: v * 255.0 + 0.5)
    return Image.merge('RGBA', [c.convert('L') for c in cols] + [alpha.convert('L')])


def _binary(mask_f):
    """L mask: 255 where the float mask is above zero."""
    return mask_f.point(lambda v: v * 255.0 + 0.5).convert('L').point(lambda v: 255 if v else 0)


def _place(chans, matrix, size, scale, origin):
    """Affine-place float channels (bitmap px) into a canvas: X = scale*(M(x) - origin)."""
    from PIL import Image
    a, b, c, d, tx, ty = matrix
    ox, oy = origin
    A, B, C, D = a * scale, c * scale, b * scale, d * scale
    E, F = (tx - ox) * scale, (ty - oy) * scale
    det = A * D - B * C
    ia, ib, ic, id_ = D / det, -B / det, -C / det, A / det
    inv = (ia, ib, -(ia * E + ib * F) + 1, ic, id_, -(ic * E + id_ * F) + 1)
    out = []
    for ch in chans:
        w, h = ch.size
        padded = Image.new('F', (w + 2, h + 2), 0.0)
        padded.paste(ch, (1, 1))
        out.append(padded.transform(size, Image.Transform.AFFINE, inv, resample=Image.Resampling.BILINEAR, fillcolor=0.0))
    return out


def _clip_mask(contours, matrix, size, scale, origin):
    """Even-odd coverage (float 0..1) of contours under matrix, 4x supersampled."""
    from PIL import Image, ImageChops, ImageDraw
    a, b, c, d, tx, ty = matrix
    ox, oy = origin
    k = 4
    big = (size[0] * k, size[1] * k)
    mask = Image.new('1', big, 0)
    for poly in contours:
        pts = [((a * x + c * y + tx - ox) * scale * k, (b * x + d * y + ty - oy) * scale * k) for x, y in poly]
        layer = Image.new('1', big, 0)
        ImageDraw.Draw(layer).polygon(pts, fill=1)
        mask = ImageChops.logical_xor(mask, layer)
    return mask.convert('L').resize(size, Image.Resampling.BOX).convert('F').point(lambda v: v / 255.0)


def _over(dst, src, mask=None):
    if mask is not None:
        src = [_math(lambda e: e['s'] * e['m'], s=s, m=mask) for s in src]
    sa = src[3]
    return [_math(lambda e: e['s'] + e['d'] * (1.0 - e['a']), s=s, d=d, a=sa) for s, d in zip(src, dst)]


def render(fws, arrangement, box, scale=1.0, override=None, only=None, chars=None):
    """Premultiplied float render of an arrangement over box (sprite px) at scale.

    override: {bitmap id: premultiplied RGBA image}; only: set of bitmap ids to draw.
    """
    from PIL import Image
    chars = chars or _char_tags(fws)
    override = override or {}
    x0, y0, x1, y1 = box
    size = (int(round((x1 - x0) * scale)), int(round((y1 - y0) * scale)))
    dst = [Image.new('F', size, 0.0) for _ in range(4)]
    clips = []
    for item in arrangement:
        depth = item[0]
        clips = [c for c in clips if c[0] >= depth]
        if item[1] == 'clip':
            _, _, sid, inner, outer, until = item
            clips.append((until, _clip_mask(shape_contours(fws, sid, chars), _compose(outer, inner), size, scale, (x0, y0))))
            continue
        _, _, bid, matrix = item
        if only is not None and bid not in only:
            continue
        image = override.get(bid) or bitmap(fws, bid, chars)
        src = _place(to_float(image), matrix, size, scale, (x0, y0))
        mask = None
        for until, cm in clips:
            if depth <= until:
                mask = cm if mask is None else _math(lambda e: e['p'] * e['q'], p=mask, q=cm)
        dst = _over(dst, src, mask)
    return dst


def resample(chans, scale, ox, oy, size, factor=4):
    """Area-correct resample: target X = scale * (render px) + o, via factor-x bilinear then box."""
    from PIL import Image
    big = (size[0] * factor, size[1] * factor)
    a = 1.0 / (scale * factor)
    inv = (a, 0.0, -ox / scale, 0.0, a, -oy / scale)
    return [c.transform(big, Image.Transform.AFFINE, inv, resample=Image.Resampling.BILINEAR, fillcolor=0.0)
            .resize(size, Image.Resampling.BOX) for c in chans]


# ------------------------------------------------------------------ Korean word

def _font(raw, size):
    import io
    from PIL import ImageFont
    return ImageFont.truetype(io.BytesIO(raw), size)


def _word_masks_big(raw, em, weight, rim, edge, tracking, text=WORD):
    """Supersampled masks (outline, body, core) on a canvas, unscaled geometry."""
    from PIL import Image, ImageChops, ImageDraw
    font = _font(raw, em)
    pad = int(em * 0.6)
    advances = [font.getlength(ch) for ch in text]
    width = int(sum(advances) + tracking * em * (len(text) - 1)) + 2 * pad
    height = int(em * 1.5) + 2 * pad
    masks = []
    for stroke in (weight + rim, weight):
        m = Image.new('L', (width, height), 0)
        d = ImageDraw.Draw(m)
        x = pad
        for ch, adv in zip(text, advances):
            d.text((x, pad), ch, font=font, fill=255, stroke_width=int(round(stroke)), stroke_fill=255)
            x += adv + tracking * em
        masks.append(m)
    outline, body = masks
    e = int(round(edge))
    core = ImageChops.multiply(body, ImageChops.offset(body, e, -e)) if e else body.copy()
    return outline, body, core


def word_image(raw, style):
    """(word straight RGBA, shadow straight RGBA, record) for a style in STYLES."""
    _pil()
    from PIL import Image
    st = STYLES[style]
    W, H = st['box']
    mx, my = st['margin']
    # pass 1: geometry at a reference em to find the fit scale; pass 2: strokes in final px
    ref = 400
    fit = None
    for _ in range(3):
        k = 1.0 if fit is None else 1.0 / fit
        outline, body, core = _word_masks_big(raw, ref, st['weight'] * k, st['rim'] * k, st['edge'] * k, st['tracking'])
        matrix, size = _italic_rotation(outline.size, st['shear'], st['angle'], st.get('stretch', 1.0))
        o = outline.transform(size, Image.Transform.AFFINE, matrix, resample=Image.Resampling.BICUBIC)
        bbox = o.getbbox()
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        new_fit = min((W - 2 * mx) / bw, (H - 2 * my) / bh)
        if fit is not None and abs(new_fit - fit) < 1e-4:
            break
        fit = new_fit
    layers = []
    for m in (outline, body, core):
        t = m.transform(size, Image.Transform.AFFINE, matrix, resample=Image.Resampling.BICUBIC).crop(bbox)
        out_w, out_h = max(1, round(bw * fit)), max(1, round(bh * fit))
        layers.append(t.resize((out_w, out_h), Image.Resampling.BOX))
    ow, oh = layers[0].size
    left, top = mx, (H - oh) // 2
    o_full, b_full, c_full = [Image.new('L', (W, H), 0) for _ in range(3)]
    for full, lay in zip((o_full, b_full, c_full), layers):
        full.paste(lay, (left, top))
    word = Image.new('RGBA', (W, H), NAVY + (0,))
    word.putalpha(o_full)
    word.paste(EDGE + (255,), (0, 0), b_full)
    word.paste(WHITE + (255,), (0, 0), c_full)
    word.putalpha(o_full)
    shadow = Image.new('RGBA', (W, H), SHADOW + (0,))
    shadow.putalpha(o_full.point(lambda v: (v * SHADOW_ALPHA + 127) // 255))
    record = dict(style=style, box=[W, H], word_bbox=[left, top, left + ow, top + oh], em_px=round(ref * fit, 2),
                  rim_px=st['rim'], weight_px=st['weight'], edge_px=st['edge'], shear=st['shear'], angle_deg=st['angle'],
                  tracking_em=st['tracking'], stretch=st.get('stretch', 1.0))
    return word, shadow, record


def _italic_rotation(size, shear, angle, stretch=1.0):
    """PIL inverse affine (output -> input) for horizontal stretch, shear x' = x - shear*y,
    then rotation (y down, negative angle = baseline rising to the right), and the output size."""
    w, h = size
    r = math.radians(angle)
    cos, sin = math.cos(r), math.sin(r)
    # forward: p' = R * S * D * (p - c) - min, D = diag(stretch, 1)
    cx, cy = w / 2, h / 2

    def forward(x, y):
        x, y = (x - cx) * stretch, y - cy
        x = x - shear * y
        return cos * x - sin * y, sin * x + cos * y
    corners = [forward(x, y) for x, y in ((0, 0), (w, 0), (0, h), (w, h))]
    minx, maxx = min(p[0] for p in corners), max(p[0] for p in corners)
    miny, maxy = min(p[1] for p in corners), max(p[1] for p in corners)
    out = (int(math.ceil(maxx - minx)), int(math.ceil(maxy - miny)))
    # inverse: p = S^-1 R^-1 (p' + (minx, miny)) + c
    # R^-1 = [[cos, sin], [-sin, cos]]; S^-1: x = x' + shear*y'
    a11, a12 = cos, sin
    a21, a22 = -sin, cos
    # after R^-1: (u, v) = (a11 X + a12 Y + t1, a21 X + a22 Y + t2) with X,Y output coords
    t1 = a11 * minx + a12 * miny
    t2 = a21 * minx + a22 * miny
    # S^-1: x = u + shear * v, y = v; D^-1: x / stretch; then + c
    return ((a11 + shear * a21) / stretch, (a12 + shear * a22) / stretch, (t1 + shear * t2) / stretch + cx,
            a21, a22, t2 + cy), out


# ------------------------------------------------------------------ composites

def _feather(mask_f, grow, blur):
    """Float 0..1 mask: threshold, dilate by grow px, blur."""
    from PIL import ImageFilter
    m = mask_f.point(lambda v: v * 255.0).convert('L').point(lambda v: 255 if v > 5 else 0)
    if grow:
        m = m.filter(ImageFilter.MaxFilter(2 * grow + 1))
    if blur:
        m = m.filter(ImageFilter.GaussianBlur(blur))
    return m.convert('F').point(lambda v: v / 255.0)


def _mix(base, new, mask):
    return [_math(lambda e: e['b'] * (1.0 - e['m']) + e['n'] * e['m'], b=b, n=n, m=mask) for b, n in zip(base, new)]


def _union(a, b):
    return _math(lambda e: e['max'](e['p'], e['q']), p=a, q=b)


def mean_abs(a, b, mask=None):
    """Mean |a-b| over the 4 channels (0..255), only where mask == 0 when a mask is given."""
    keep = None if mask is None else [v <= 0.0 for v in mask.getdata()]
    total = count = 0.0
    for x, y in zip(a, b):
        for i, (p, q) in enumerate(zip(x.getdata(), y.getdata())):
            if keep is None or keep[i]:
                total += abs(p - q)
                count += 1
    return total / max(count, 1) * 255.0


def small_still(fws, korean, chars=None):
    """Korean version of still image 1409 (premultiplied RGBA) + record."""
    chars = chars or _char_tags(fws)
    original = to_float(bitmap(fws, SMALL_STILL, chars))
    override = {SMALL_WORD: korean['small'][0], SMALL_SHADOW: korean['small'][1]}
    box = SMALL_STILL_BOX
    rendered = render(fws, SMALL, box, 1.0, override, chars=chars)
    old = render(fws, SMALL, box, 1.0, only={SMALL_WORD, SMALL_SHADOW}, chars=chars)[3]
    new = render(fws, SMALL, box, 1.0, override, only={SMALL_WORD, SMALL_SHADOW}, chars=chars)[3]
    mask = _feather(_union(old, new), 1, 0.7)
    check = render(fws, SMALL, box, 1.0, chars=chars)
    residual = mean_abs(check, original, mask)
    if residual > 6.0:
        raise ValueError(f'Small logo arrangement does not match its still image ({residual:.2f})')
    from PIL import Image
    source = bitmap(fws, SMALL_STILL, chars)
    out = Image.composite(to_premultiplied_image(_mix(original, rendered, mask)), source, _binary(mask))
    return out, dict(still=SMALL_STILL, residual_outside_mask=round(residual, 2),
                     replaced_pixels=sum(1 for v in _binary(mask).getdata() if v))


def mc_logo_still(fws, korean, chars=None):
    """Korean version of the mc_logo English frame image 1840 (premultiplied RGBA) + record.

    Same method as small_still: original pixels outside a feathered mask around the old and new
    word, the SMALL arrangement with the Korean word pieces (at MC_LOGO_FIT) inside it.
    """
    chars = chars or _char_tags(fws)
    source = bitmap(fws, MC_LOGO_ENG, chars)
    original = to_float(source)
    s, ox, oy = MC_LOGO_FIT
    w, h = source.size
    x0, y0 = -ox / s, -oy / s
    box = (x0, y0, x0 + w / s, y0 + h / s)
    override = {SMALL_WORD: korean['small'][0], SMALL_SHADOW: korean['small'][1]}
    rendered = render(fws, SMALL, box, s, override, chars=chars)
    if rendered[0].size != source.size:
        raise ValueError('mc_logo render size differs')
    old = render(fws, SMALL, box, s, only={SMALL_WORD, SMALL_SHADOW}, chars=chars)[3]
    new = render(fws, SMALL, box, s, override, only={SMALL_WORD, SMALL_SHADOW}, chars=chars)[3]
    mask = _feather(_union(old, new), 1, 0.7)
    check = render(fws, SMALL, box, s, chars=chars)
    residual = mean_abs(check, original, mask)
    if residual > 6.0:
        raise ValueError(f'Small logo arrangement does not match the mc_logo image ({residual:.2f})')
    from PIL import Image
    out = Image.composite(to_premultiplied_image(_mix(original, rendered, mask)), source, _binary(mask))
    return out, dict(image=MC_LOGO_ENG, sprite=1848, frames='1 (English; Korean via LocaleManager), 4, 6',
                     fit=list(MC_LOGO_FIT), residual_outside_mask=round(residual, 2),
                     replaced_pixels=sum(1 for v in _binary(mask).getdata() if v))


def menu_banner_logo(fws, logo_straight, korean, chars=None):
    """Korean Logo_English.tpl image (straight RGBA) from the intro arrangement at BANNER_FIT."""
    chars = chars or _char_tags(fws)
    target = premultiply(logo_straight)
    size = logo_straight.size
    scale, ox, oy = BANNER_FIT
    hi = 3.0
    box = (140.0, -120.0, 510.0, 110.0)
    # hi-res render origin is box corner: render px p_r = (u - x0)*hi ; target X = scale*u + ox
    sc = scale / hi
    o2x, o2y = ox + scale * box[0], oy + scale * box[1]
    override = {INTRO_WORD: korean['intro'][0], INTRO_SHADOW: korean['intro'][1]}
    rendered = resample(render(fws, INTRO, box, hi, override, chars=chars), sc, o2x, o2y, size)
    plain = resample(render(fws, INTRO, box, hi, chars=chars), sc, o2x, o2y, size)
    old = resample(render(fws, INTRO, box, hi, only={INTRO_WORD, INTRO_SHADOW}, chars=chars), sc, o2x, o2y, size)[3]
    new = resample(render(fws, INTRO, box, hi, override, only={INTRO_WORD, INTRO_SHADOW}, chars=chars), sc, o2x, o2y, size)[3]
    mask = _feather(_union(old, new), 1, 0.8)
    residual = mean_abs(plain, target, mask)
    if residual > 9.0:
        raise ValueError(f'Intro arrangement does not match the banner logo ({residual:.2f})')
    from PIL import Image
    out = Image.composite(to_straight_image(_mix(target, rendered, mask)), logo_straight.convert('RGBA'), _binary(mask))
    return out, dict(fit=list(BANNER_FIT), residual_outside_mask=round(residual, 2),
                     replaced_pixels=sum(1 for v in _binary(mask).getdata() if v))


def korean_pieces(raw):
    """{'intro'|'small'|'icon': (word premultiplied RGBA, shadow premultiplied RGBA, straight word, record)}."""
    out = {}
    for style in ('intro', 'small', 'icon'):
        word, shadow, record = word_image(raw, style)
        out[style] = (to_premultiplied_image(premultiply(word)), to_premultiplied_image(premultiply(shadow)), word, record)
    return out


def tpl_replace_changed(data, index, before, after):
    """Encode `after` into TPL image `index`, restoring the original bytes of blocks whose pixels are unchanged."""
    from . import tpl
    from .channel_texture import texture_records
    r = texture_records(data)[index]
    w, h, fmt, at = r['width'], r['height'], r['format'], r['offset']
    bw, bh, bpp = tpl.BLOCK[fmt]
    encoded = bytearray(tpl.encode(data, index, after))
    block_bytes = bw * bh * bpp // 8
    pos = at
    changed = 0
    for by in range(0, h, bh):
        for bx in range(0, w, bw):
            same = True
            for y in range(by, min(by + bh, h)):
                for x in range(bx, min(bx + bw, w)):
                    if before.getpixel((x, y)) != after.getpixel((x, y)):
                        same = False
                        break
                if not same:
                    break
            if same:
                encoded[pos:pos + block_bytes] = data[pos:pos + block_bytes]
            else:
                changed += 1
            pos += block_bytes
    return bytes(encoded), changed


# ------------------------------------------------------------------ build entry point

def korean_logo_set(swf, mc_logo=False):
    """Revision-8 logo assets from the WiiLink-patched SWF (read only); mc_logo=True (revision 9+)
    also replaces the mc_logo English frame image 1840.

    Returns dict(bitmaps={character id: DefineBitsLossless2 payload}, icon_word=straight RGBA 49x18,
    banner_logo=fn(straight RGBA Logo_English) -> (image, record), record=...).
    """
    from . import kirbytv_swf as K
    _, _, fws = K.unpack(swf)
    chars = _char_tags(fws)
    raw, digest = round_gothic()
    pieces = korean_pieces(raw)
    korean = {k: v[:2] for k, v in pieces.items()}
    still, still_record = small_still(fws, korean, chars)
    images = {INTRO_WORD: pieces['intro'][0], INTRO_SHADOW: pieces['intro'][1],
              SMALL_WORD: pieces['small'][0], SMALL_SHADOW: pieces['small'][1], SMALL_STILL: still}
    mc_record = None
    if mc_logo:
        images[MC_LOGO_ENG], mc_record = mc_logo_still(fws, korean, chars)
    bitmaps = {}
    for cid, image in images.items():
        original = bitmap(fws, cid, chars)
        if original.size != image.size:
            raise ValueError(f'Korean logo piece {cid} size differs')
        bitmaps[cid] = lossless2(cid, image)

    def banner_logo(image):
        return menu_banner_logo(fws, image, korean, chars)
    record = dict(word=WORD, font=FONT_NAME, font_sha256=digest, styles={k: v[3] for k, v in pieces.items()},
                  swf_pieces={'intro word': INTRO_WORD, 'intro shadow': INTRO_SHADOW, 'small word': SMALL_WORD,
                              'small shadow': SMALL_SHADOW, 'small still': SMALL_STILL},
                  small_still=still_record, swf_bitmap_sha256={str(k): hashlib.sha256(v).hexdigest() for k, v in sorted(bitmaps.items())})
    if mc_record is not None:
        record['swf_pieces']['mc_logo still'] = MC_LOGO_ENG
        record['mc_logo_still'] = mc_record
    return dict(bitmaps=bitmaps, icon_word=pieces['icon'][2], banner_logo=banner_logo, record=record)

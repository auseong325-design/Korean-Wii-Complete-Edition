"""Add Hangul glyph outlines to the Kirby TV SWF's embedded DefineFont3 fonts.

Every text field of Gumball2.12.RC-1.swf uses embedded outlines (DefineEditText
UseOutlines) of "Alor 0513" or "Alor 0513 Narrow", which carry only Latin-1.
Characters missing from an embedded font are skipped by the player, so Korean
text showed only its ASCII parts (build-v1, lead Dolphin review 2026-10-28).
This module appends outlines for the requested Hangul syllables:

* source: Noto Sans KR variable (SIL OFL 1.1, the font kwce.channel_font
  already uses), instanced at a heavy weight to match Alor's stroke;
* its contours overlap, which the player's edge fill would render as holes,
  so each glyph is converted to the outline of its non-zero area (curves
  flattened, edges split at intersections, boundary pieces chained) and the
  result is checked against the source coverage;
* shapes follow the Flash-authored convention found in these fonts:
  NumFillBits=1, NumLineBits=0, the first style record sets FillStyle0=1,
  later contours only move, outer contours positive area in y-down units,
  20480 units per em;
* the code table stays sorted (Hangul sorts after Latin-1), advances are
  appended, bounds stay zero like the originals, kerning is untouched;
  offsets become 32-bit when the shape table outgrows 16-bit offsets;
  DefineFontAlignZones gets a no-zone record (mask 0) per new glyph.
"""
import hashlib
import struct
from .channels import load_library

EM = 20480
TAG_FONT3 = 75
TAG_ALIGN = 73


# ------------------------------------------------------------------ bits

class BitReader:
    def __init__(self, data, at):
        self.data = data
        self.pos = at * 8

    def u(self, n):
        value = 0
        for _ in range(n):
            value = value << 1 | (self.data[self.pos >> 3] >> (7 - (self.pos & 7))) & 1
            self.pos += 1
        return value

    def s(self, n):
        value = self.u(n)
        return value - (1 << n) if n and value >> (n - 1) else value

    def byte(self):
        return (self.pos + 7) // 8


class BitWriter:
    def __init__(self):
        self.out = bytearray()
        self.acc = 0
        self.count = 0

    def u(self, n, value):
        if value < 0 or value >> n:
            raise ValueError('Unsigned bit field overflow')
        for bit in range(n - 1, -1, -1):
            self.acc = self.acc << 1 | (value >> bit) & 1
            self.count += 1
            if self.count == 8:
                self.out.append(self.acc)
                self.acc = self.count = 0

    def s(self, n, value):
        if not -(1 << (n - 1)) <= value < 1 << (n - 1):
            raise ValueError('Signed bit field overflow')
        self.u(n, value & ((1 << n) - 1))

    def flush(self):
        if self.count:
            self.out.append(self.acc << (8 - self.count))
            self.acc = self.count = 0
        return bytes(self.out)


def sbits(*values):
    """Bits for signed values, at least 1 sign bit."""
    width = 1
    for value in values:
        width = max(width, (value if value >= 0 else ~value).bit_length() + 1)
    return width


# --------------------------------------------------------------- shapes

def read_shape(data, at):
    """Decode a glyph SHAPE into contours of ('line'|'curve', points) in absolute units."""
    bits = BitReader(data, at)
    fill_bits, line_bits = bits.u(4), bits.u(4)
    contours, current = [], None
    x = y = 0
    fills = []
    while True:
        if bits.u(1) == 0:
            flags = bits.u(5)
            if flags == 0:
                break
            if flags & 16:
                raise ValueError('Glyph shape with new styles')
            if flags & 1:
                n = bits.u(5)
                x, y = bits.s(n), bits.s(n)
                current = [(x, y)]
                contours.append(current)
            if flags & 2:
                fills.append(('f0', bits.u(fill_bits)))
            if flags & 4:
                fills.append(('f1', bits.u(fill_bits)))
            if flags & 8:
                bits.u(line_bits)
        else:
            straight = bits.u(1)
            n = bits.u(4) + 2
            if straight:
                if bits.u(1):
                    dx, dy = bits.s(n), bits.s(n)
                elif bits.u(1):
                    dx, dy = 0, bits.s(n)
                else:
                    dx, dy = bits.s(n), 0
                x, y = x + dx, y + dy
                current.append((x, y))
            else:
                cx, cy = x + bits.s(n), y + bits.s(n)
                x, y = cx + bits.s(n), cy + bits.s(n)
                current.append(((cx, cy), (x, y)))
    return dict(fill_bits=fill_bits, line_bits=line_bits, fills=fills, contours=contours, end=bits.byte())


def write_shape(contours):
    """contours: list of [start, item...] with item (x, y) line or ((cx, cy), (x, y)) curve."""
    bits = BitWriter()
    bits.u(4, 1)
    bits.u(4, 0)
    first = True
    px = py = 0
    for contour in contours:
        sx, sy = contour[0]
        n = sbits(sx, sy)
        bits.u(1, 0)
        bits.u(5, (2 if first else 0) | 1)   # StateFillStyle0 on the first record, StateMoveTo
        bits.u(5, n)
        bits.s(n, sx)
        bits.s(n, sy)
        if first:
            bits.u(1, 1)                      # FillStyle0 = 1
            first = False
        px, py = sx, sy
        for item in contour[1:]:
            if isinstance(item[0], tuple):
                (cx, cy), (ax, ay) = item
                values = (cx - px, cy - py, ax - cx, ay - cy)
                n = max(2, sbits(*values))
                bits.u(1, 1)
                bits.u(1, 0)
                bits.u(4, n - 2)
                for value in values:
                    bits.s(n, value)
                px, py = ax, ay
            else:
                ax, ay = item
                dx, dy = ax - px, ay - py
                if not dx and not dy:
                    continue
                n = max(2, sbits(dx, dy))
                bits.u(1, 1)
                bits.u(1, 1)
                bits.u(4, n - 2)
                if dx and dy:
                    bits.u(1, 1)
                    bits.s(n, dx)
                    bits.s(n, dy)
                else:
                    bits.u(1, 0)
                    bits.u(1, 1 if dx == 0 else 0)
                    bits.s(n, dy if dx == 0 else dx)
                px, py = ax, ay
    bits.u(1, 0)
    bits.u(5, 0)
    return bits.flush()


# ----------------------------------------------------------- DefineFont3

def _rect_bytes(xmin, xmax, ymin, ymax):
    bits = BitWriter()
    n = sbits(xmin, xmax, ymin, ymax) if any((xmin, xmax, ymin, ymax)) else 0
    bits.u(5, n)
    for value in (xmin, xmax, ymin, ymax):
        if n:
            bits.s(n, value)
    return bits.flush()


def parse_font3(payload):
    fid = struct.unpack_from('<H', payload, 0)[0]
    flags, lang, name_len = payload[2], payload[3], payload[4]
    if not flags & 0x80 or not flags & 0x04:
        raise ValueError('Expected DefineFont3 with layout and wide codes')
    name = payload[5:5 + name_len]
    count = struct.unpack_from('<H', payload, 5 + name_len)[0]
    at = 7 + name_len
    wide = bool(flags & 0x08)
    size = 4 if wide else 2
    fmt = '<I' if wide else '<H'
    offsets = [struct.unpack_from(fmt, payload, at + size * i)[0] for i in range(count)]
    code_offset = struct.unpack_from(fmt, payload, at + size * count)[0]
    shapes = [payload[at + offsets[i]:at + (offsets[i + 1] if i + 1 < count else code_offset)] for i in range(count)]
    codes = list(struct.unpack_from('<%dH' % count, payload, at + code_offset))
    pos = at + code_offset + 2 * count
    ascent, descent, leading = struct.unpack_from('<hhh', payload, pos)
    pos += 6
    advances = list(struct.unpack_from('<%dh' % count, payload, pos))
    pos += 2 * count
    bounds = []
    for _ in range(count):
        bits = BitReader(payload, pos)
        n = bits.u(5)
        rect = [bits.s(n) for _ in range(4)]
        end = bits.byte()
        bounds.append(payload[pos:end])
        pos = end
        if any(rect):
            pass
    kerning_count = struct.unpack_from('<H', payload, pos)[0]
    kerning = payload[pos + 2:pos + 2 + 6 * kerning_count]
    if pos + 2 + 6 * kerning_count != len(payload):
        raise ValueError('DefineFont3 length differs')
    return dict(id=fid, flags=flags, lang=lang, name=name, shapes=shapes, codes=codes, ascent=ascent,
                descent=descent, leading=leading, advances=advances, bounds=bounds, kerning_count=kerning_count,
                kerning=kerning)


def build_font3(font):
    count = len(font['codes'])
    if count != len(font['shapes']) or count != len(font['advances']) or count != len(font['bounds']):
        raise ValueError('Font tables differ in length')
    if font['codes'] != sorted(set(font['codes'])):
        raise ValueError('Font code table must be sorted and unique')
    shape_bytes = sum(len(s) for s in font['shapes'])
    wide = bool(font['flags'] & 0x08) or 2 * (count + 1) + shape_bytes > 0xffff
    flags = font['flags'] | (0x08 if wide else 0)
    size = 4 if wide else 2
    fmt = '<I' if wide else '<H'
    out = bytearray(struct.pack('<HBBB', font['id'], flags, font['lang'], len(font['name'])) + font['name'])
    out += struct.pack('<H', count)
    table = size * (count + 1)
    offset = table
    offsets = bytearray()
    for shape in font['shapes']:
        offsets += struct.pack(fmt, offset)
        offset += len(shape)
    out += offsets + struct.pack(fmt, offset) + b''.join(font['shapes'])
    out += struct.pack('<%dH' % count, *font['codes'])
    out += struct.pack('<hhh', font['ascent'], font['descent'], font['leading'])
    out += struct.pack('<%dh' % count, *font['advances'])
    out += b''.join(font['bounds'])
    out += struct.pack('<H', font['kerning_count']) + font['kerning']
    return bytes(out)


def extend_align_zones(payload, font_id, added):
    if struct.unpack_from('<H', payload, 0)[0] != font_id:
        raise ValueError('Alignment zones belong to another font')
    # NumZoneData 2, two zero zones, ZoneMaskX/Y 0: no alignment for the glyph.
    return payload + bytes([2] + [0] * 8 + [0]) * added


# --------------------------------------------------------- TrueType side

class _Outline:
    """fontTools pen collecting quadratic contours in font units."""

    def __init__(self, glyph_set):
        from fontTools.pens.basePen import BasePen

        class Pen(BasePen):
            def __init__(pen):
                super().__init__(glyph_set)
                pen.contours = []

            def _moveTo(pen, pt):
                pen.contours.append([('move', pt)])

            def _lineTo(pen, pt):
                pen.contours[-1].append(('line', pt))

            def _qCurveToOne(pen, pt1, pt2):
                pen.contours[-1].append(('curve', pt1, pt2))

            def _curveToOne(pen, pt1, pt2, pt3):
                raise ValueError('Cubic outlines are not expected in this font')

            def _closePath(pen):
                pass
        self.pen = Pen()


def glyph_contours(glyph_set, name):
    outline = _Outline(glyph_set)
    glyph_set[name].draw(outline.pen)
    return outline.pen.contours


def _flatten(contour, steps=6):
    points = [contour[0][1]]
    for item in contour[1:]:
        if item[0] == 'line':
            points.append(item[1])
        else:
            (x0, y0), (cx, cy), (x1, y1) = points[-1], item[1], item[2]
            for k in range(1, steps + 1):
                t = k / steps
                a, b, c = (1 - t) ** 2, 2 * t * (1 - t), t * t
                points.append((a * x0 + b * cx + c * x1, a * y0 + b * cy + c * y1))
    if points[0] != points[-1]:
        points.append(points[0])
    return points


def overlap_area(contours, lines=48):
    """Approximate area (font units^2) where |non-zero winding| > 1."""
    polys = [_flatten(c) for c in contours if len(c) > 1]
    if not polys:
        return 0.0
    ys = [p[1] for poly in polys for p in poly]
    lo, hi = min(ys), max(ys)
    if hi <= lo:
        return 0.0
    step = (hi - lo) / lines
    total = 0.0
    for k in range(lines):
        y = lo + (k + 0.5) * step
        crossings = []
        for poly in polys:
            for (x0, y0), (x1, y1) in zip(poly, poly[1:]):
                if (y0 <= y < y1) or (y1 <= y < y0):
                    x = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
                    crossings.append((x, 1 if y1 > y0 else -1))
        crossings.sort()
        winding = 0
        for (x, d), nxt in zip(crossings, crossings[1:] + [None]):
            winding += d
            if nxt is not None and abs(winding) > 1:
                total += (nxt[0] - x) * step
    return total


def _flatten_adaptive(contour, tolerance):
    """Closed polygon (list of points, first == last) from a quadratic contour."""
    import math
    points = [contour[0][1]]
    for item in contour[1:]:
        if item[0] == 'line':
            if item[1] != points[-1]:
                points.append(item[1])
            continue
        (x0, y0), (cx, cy), (x1, y1) = points[-1], item[1], item[2]
        deviation = math.hypot(x0 - 2 * cx + x1, y0 - 2 * cy + y1) / 4
        steps = max(1, math.ceil(math.sqrt(deviation / tolerance)))
        for k in range(1, steps + 1):
            t = k / steps
            a, b, c = (1 - t) ** 2, 2 * t * (1 - t), t * t
            point = (a * x0 + b * cx + c * x1, a * y0 + b * cy + c * y1) if k < steps else (x1, y1)
            if point != points[-1]:
                points.append(point)
    if points[0] != points[-1]:
        points.append(points[0])
    return points


def _winding(point, segments):
    x, y = point
    winding = 0
    for (x0, y0), (x1, y1) in segments:
        if y0 <= y < y1:
            if (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0) > 0:
                winding += 1
        elif y1 <= y < y0:
            if (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0) < 0:
                winding -= 1
    return winding


def union_outline(contours, tolerance=1.0):
    """Outline of {winding != 0} as non-overlapping straight-edged contours.

    Curves are flattened (max deviation `tolerance` font units). All edges
    are split at their mutual intersections; a piece is kept when exactly
    one of its sides is filled, oriented with the fill on its right (TrueType
    outer clockwise, y up), and the pieces are chained into closed loops.
    """
    import math
    polygons = [_flatten_adaptive(c, tolerance) for c in contours]
    segments = [(p, q) for poly in polygons for p, q in zip(poly, poly[1:]) if p != q]
    splits = [[a, b] for a, b in segments]
    order = sorted(range(len(segments)), key=lambda i: min(segments[i][0][0], segments[i][1][0]))
    active = []
    snap = 1e-7

    def near(p, q):
        return abs(p[0] - q[0]) <= snap and abs(p[1] - q[1]) <= snap
    for i in order:
        (ax, ay), (bx, by) = segments[i]
        lo_x = min(ax, bx)
        active = [j for j in active if max(segments[j][0][0], segments[j][1][0]) >= lo_x - snap]
        lo_y, hi_y = min(ay, by), max(ay, by)
        for j in active:
            (cx, cy), (dx, dy) = segments[j]
            if max(cy, dy) < lo_y - snap or min(cy, dy) > hi_y + snap:
                continue
            rx, ry, sx, sy = bx - ax, by - ay, dx - cx, dy - cy
            denom = rx * sy - ry * sx
            qx, qy = cx - ax, cy - ay
            if abs(denom) > 1e-12 * (abs(rx) + abs(ry)) * (abs(sx) + abs(sy)):
                t = (qx * sy - qy * sx) / denom
                u = (qx * ry - qy * rx) / denom
                if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
                    point = (ax + t * rx, ay + t * ry)
                    for end in (segments[i][0], segments[i][1], segments[j][0], segments[j][1]):
                        if near(point, end):
                            point = end
                            break
                    splits[i].append(point)
                    splits[j].append(point)
            elif abs(qx * ry - qy * rx) <= 1e-9 * (abs(rx) + abs(ry) + 1):
                # Collinear: each segment is split at the other's endpoints.
                for end in (segments[j][0], segments[j][1]):
                    splits[i].append(end)
                for end in (segments[i][0], segments[i][1]):
                    splits[j].append(end)
        active.append(i)
    pieces = {}
    for index, (a, b) in enumerate(segments):
        rx, ry = b[0] - a[0], b[1] - a[1]
        length2 = rx * rx + ry * ry

        def param(p):
            return ((p[0] - a[0]) * rx + (p[1] - a[1]) * ry) / length2
        points = sorted({p for p in splits[index] if -1e-9 <= param(p) <= 1 + 1e-9}, key=param)
        for p, q in zip(points, points[1:]):
            if p != q:
                key = (p, q) if p < q else (q, p)
                pieces[key] = True
    kept = []
    for p, q in pieces:
        mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
        length = math.hypot(q[0] - p[0], q[1] - p[1])
        if length < 1e-9:
            continue
        nx, ny = -(q[1] - p[1]) / length, (q[0] - p[0]) / length
        eps = min(1e-3, length / 4)
        left = _winding((mx + nx * eps, my + ny * eps), segments) != 0
        right = _winding((mx - nx * eps, my - ny * eps), segments) != 0
        if left != right:
            kept.append((p, q) if right else (q, p))
    outgoing = {}
    for edge in kept:
        outgoing.setdefault(edge[0], []).append(edge)
    used = set()
    loops = []
    for edge in kept:
        if edge in used:
            continue
        loop = [edge[0]]
        current = edge
        while current not in used:
            used.add(current)
            loop.append(current[1])
            candidates = [e for e in outgoing.get(current[1], []) if e not in used]
            if not candidates:
                break
            if len(candidates) > 1:
                ix, iy = current[1][0] - current[0][0], current[1][1] - current[0][1]

                def turn(e):
                    ox, oy = e[1][0] - e[0][0], e[1][1] - e[0][1]
                    return math.atan2(ix * oy - iy * ox, ix * ox + iy * oy)
                candidates.sort(key=turn)   # rightmost turn first keeps loops simple
            current = candidates[0]
        if loop[0] != loop[-1]:
            raise ValueError('Union boundary did not close')
        loops.append(_simplify(loop))
    return [[('move', loop[0])] + [('line', p) for p in loop[1:]] for loop in loops if len(loop) >= 4]


def _simplify(loop):
    """Drop points that are collinear with their neighbours (exact geometry kept)."""
    points = loop[:-1]
    changed = True
    while changed and len(points) > 3:
        changed = False
        out = []
        n = len(points)
        for i in range(n):
            a, b, c = points[i - 1], points[i], points[(i + 1) % n]
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            scale = abs(c[0] - a[0]) + abs(c[1] - a[1]) + 1e-12
            if abs(cross) / scale <= 1e-7 and (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1]) >= 0:
                changed = True
                points = points[:i] + points[i + 1:]
                break
            out.append(b)
    return points + [points[0]]


def coverage_mismatch(reference, outline, lines=64):
    """Fraction of the reference (non-zero) area that the even-odd outline gets wrong."""
    ref = [(p, q) for c in reference for poly in [_flatten_adaptive(c, 0.5)] for p, q in zip(poly, poly[1:]) if p != q]
    out = [(p, q) for c in outline for poly in [_flatten_adaptive(c, 0.5)] for p, q in zip(poly, poly[1:]) if p != q]
    ys = [p[1] for seg in ref for p in seg]
    lo, hi = min(ys), max(ys)
    step = (hi - lo) / lines
    wrong = total = 0.0

    def spans(segments, y, rule):
        xs = []
        for (x0, y0), (x1, y1) in segments:
            if (y0 <= y < y1) or (y1 <= y < y0):
                xs.append((x0 + (y - y0) * (x1 - x0) / (y1 - y0), 1 if y1 > y0 else -1))
        xs.sort()
        result, winding, start = [], 0, None
        for x, d in xs:
            before = winding != 0 if rule == 'nonzero' else winding % 2 == 1
            winding += d if rule == 'nonzero' else 1
            after = winding != 0 if rule == 'nonzero' else winding % 2 == 1
            if not before and after:
                start = x
            elif before and not after:
                result.append((start, x))
        return result

    def length(a):
        return sum(b - c for c, b in a)

    def intersect(a, b):
        out, i, j = 0.0, 0, 0
        while i < len(a) and j < len(b):
            lo_, hi_ = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
            if hi_ > lo_:
                out += hi_ - lo_
            if a[i][1] < b[j][1]:
                i += 1
            else:
                j += 1
        return out
    for k in range(lines):
        y = lo + (k + 0.5) * step
        a, b = spans(ref, y, 'nonzero'), spans(out, y, 'evenodd')
        la, lb, both = length(a), length(b), intersect(a, b)
        wrong += (la - both) + (lb - both)
        total += la
    return wrong / total if total else 0.0


def embolden(contours, distance, miter=2.0):
    """Move every point (on and off curve) outward along its control-polygon
    bisector, like FreeType's FT_Outline_Embolden. TrueType orientation (outer
    clockwise, holes counter-clockwise, y up) makes (-dy, dx) point away from
    the filled area, so outer contours grow and holes shrink.
    """
    import math
    if not distance:
        return contours
    out = []
    for contour in contours:
        points = [contour[0][1]]
        kinds = []
        for item in contour[1:]:
            if item[0] == 'line':
                points.append(item[1])
                kinds.append(('line',))
            else:
                points.append(item[1])
                points.append(item[2])
                kinds.append(('curve',))
        closed = points[0] == points[-1]
        ring = points[:-1] if closed else points[:]
        n = len(ring)
        if n < 3:
            out.append(contour)
            continue

        def unit(a, b):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            return (dx / length, dy / length) if length else None
        moved = []
        for i in range(n):
            prev = next_ = None
            for k in range(1, n):
                prev = unit(ring[(i - k) % n], ring[i])
                if prev:
                    break
            for k in range(1, n):
                next_ = unit(ring[i], ring[(i + k) % n])
                if next_:
                    break
            if not prev or not next_:
                moved.append(ring[i])
                continue
            nx, ny = -prev[1] - next_[1], prev[0] + next_[0]
            length = math.hypot(nx, ny)
            if length < 1e-6:
                moved.append(ring[i])
                continue
            nx, ny = nx / length, ny / length
            cos_half = max(1.0 / miter, (nx * -prev[1] + ny * prev[0]))
            shift = distance / cos_half
            moved.append((ring[i][0] + nx * shift, ring[i][1] + ny * shift))
        if closed:
            moved.append(moved[0])
        rebuilt = [('move', moved[0])]
        at = 1
        for kind in kinds:
            if kind[0] == 'line':
                rebuilt.append(('line', moved[at]))
                at += 1
            else:
                rebuilt.append(('curve', moved[at], moved[at + 1]))
                at += 2
        out.append(rebuilt)
    return out


# ----------------------------------------------------------- integration

class HangulSource:
    def __init__(self, ttf, weight=None, label=''):
        load_library()
        import io
        from fontTools.ttLib import TTFont
        from pathlib import Path
        raw = bytes(ttf) if isinstance(ttf, (bytes, bytearray)) else Path(ttf).read_bytes()
        self.font = TTFont(io.BytesIO(raw), lazy=False, recalcTimestamp=False)
        self.cmap = self.font.getBestCmap()
        location = {'wght': weight} if weight is not None and 'fvar' in self.font else None
        self.glyphs = self.font.getGlyphSet(location=location) if location else self.font.getGlyphSet()
        self.upm = self.font['head'].unitsPerEm
        self.weight = weight
        self.label = label
        self.digest = hashlib.sha256(raw).hexdigest()

    def contours(self, char):
        name = self.cmap.get(ord(char))
        if name is None:
            raise ValueError(f'Source font lacks U+{ord(char):04X}')
        return glyph_contours(self.glyphs, name), self.glyphs[name].width


def required_characters(texts, existing):
    chars = set()
    for text in texts:
        chars.update(text)
    missing = sorted(c for c in chars if ord(c) >= 32 and ord(c) not in existing)
    others = [c for c in missing if not 0xac00 <= ord(c) <= 0xd7a3]
    if others:
        raise ValueError('Characters outside Hangul syllables need a font decision: ' + ''.join(others))
    return missing


def extend_fonts(fws, characters, source, size=0.9, condense=1.0, narrow_condense=1.0, bold=0.0):
    """Return (new FWS bytes, record).

    size: em fraction the source em maps to (uniform scale, baseline kept);
    condense: horizontal factor for "Alor 0513", narrow_condense for the
    Narrow face; bold: outward offset in source em (FreeType-style), reduced
    per glyph when it would make contours overlap. Advances are the source
    advances scaled the same way (plus 2*bold so emboldened glyphs keep their
    side bearings).
    """
    from . import kirbytv_swf as K
    listing = K.tags(fws)
    fonts = {}
    zones = {}
    for index, (code, pos, head, length) in enumerate(listing):
        payload = fws[pos + head:pos + head + length]
        if code == TAG_FONT3:
            fonts[struct.unpack_from('<H', payload, 0)[0]] = index
        elif code == TAG_ALIGN:
            zones[struct.unpack_from('<H', payload, 0)[0]] = index
    if sorted(fonts) != [1, 2] or sorted(zones) != [1, 2]:
        raise ValueError('Expected the two Alor fonts with alignment zones')
    limit = 4.0 * (source.upm / 1000) ** 2
    tolerance = 0.8 * source.upm / 1000
    outlines = {}
    worst = 0.0
    for char in characters:
        contours, width = source.contours(char)
        merged = union_outline(contours, tolerance)
        worst = max(worst, coverage_mismatch(contours, merged))
        if bold:
            grown = embolden(merged, bold * source.upm)
            merged = union_outline(grown, tolerance)
            worst = max(worst, coverage_mismatch(grown, merged))
        if overlap_area(merged) > limit:
            raise ValueError(f'Union left overlapping contours in U+{ord(char):04X}')
        # Keep the side bearings: shift right by the bold offset, widen the advance.
        shift = bold * source.upm
        merged = [[(kind[0],) + tuple((p[0] + shift, p[1]) for p in kind[1:]) for kind in c] for c in merged]
        outlines[char] = (merged, width + 2 * shift)
    if worst > 0.01:
        raise ValueError(f'Union outline differs from the source coverage ({worst:.4f})')
    scale = size * EM / source.upm
    replacements = {}
    record = dict(source=source.label, source_sha256=source.digest, weight=source.weight, characters=len(characters),
                  size_em=size, condense=condense, narrow_condense=narrow_condense, bold_em=bold,
                  flatten_tolerance_units=tolerance, worst_coverage_mismatch=round(worst, 5), fonts={})
    for fid in (1, 2):
        index = fonts[fid]
        code, pos, head, length = listing[index]
        font = parse_font3(fws[pos + head:pos + head + length])
        existing = set(font['codes'])
        add = [c for c in characters if ord(c) not in existing]
        sx = scale * (narrow_condense if fid == 2 else condense)
        added_bytes = 0
        for char in add:
            contours, width = outlines[char]
            swf = to_swf_xy(contours, sx, scale, 0.0)
            areas = [_swf_area(c) for c in swf]
            if not areas or max(areas, key=abs) <= 0:
                raise ValueError(f'Glyph orientation differs from the Alor convention: U+{ord(char):04X}')
            shape = write_shape(swf)
            check = read_shape(shape, 0)
            if len(check['contours']) != len(swf) or check['fills'] != [('f0', 1)]:
                raise ValueError('Glyph shape roundtrip failed')
            font['shapes'].append(shape)
            font['codes'].append(ord(char))
            font['advances'].append(round(width * sx))
            font['bounds'].append(b'\x00')
            added_bytes += len(shape)
        order = sorted(range(len(font['codes'])), key=lambda i: font['codes'][i])
        if order != list(range(len(order))):
            raise ValueError('New glyphs must sort after the original glyphs')
        replacements[index] = build_font3(font)
        zcode, zpos, zhead, zlength = listing[zones[fid]]
        old_zones = fws[zpos + zhead:zpos + zhead + zlength]
        if (len(old_zones) - 3) // 10 != len(existing) or (len(old_zones) - 3) % 10:
            raise ValueError('Alignment zone count differs from glyph count')
        replacements[zones[fid]] = extend_align_zones(old_zones, fid, len(add))
        record['fonts'][font['name'].rstrip(b'\0').decode('latin-1')] = dict(
            id=fid, glyphs_before=len(existing), glyphs_after=len(font['codes']), added=len(add),
            added_shape_bytes=added_bytes, wide_offsets=bool(replacements[index][2] & 0x08))
    return K.replace_tags(fws, replacements), record


def _swf_area(items):
    """Signed area of an SWF contour (y down); curves via their control polygon."""
    points = [items[0]]
    for item in items[1:]:
        if isinstance(item[0], tuple):
            points.extend(item)
        else:
            points.append(item)
    if points[0] != points[-1]:
        points.append(points[0])
    return sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(points, points[1:])) / 2


def to_swf_xy(contours, sx, sy, dx):
    """Like to_swf but with independent x/y scale (narrow variant)."""
    def tr(pt):
        return (round(pt[0] * sx + dx), round(-pt[1] * sy))
    out = []
    for contour in contours:
        start = tr(contour[0][1])
        items = [start]
        last = start
        for item in contour[1:]:
            if item[0] == 'line':
                point = tr(item[1])
                if point != last:
                    items.append(point)
                    last = point
            else:
                control, anchor = tr(item[1]), tr(item[2])
                if anchor == last and control == last:
                    continue
                if control == last or control == anchor:
                    items.append(anchor)
                else:
                    items.append((control, anchor))
                last = anchor
        if last != start:
            items.append(start)
        if len(items) > 2:
            out.append(items)
    return out

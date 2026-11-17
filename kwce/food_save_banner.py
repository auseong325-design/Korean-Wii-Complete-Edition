"""Korean save-data banner for the Food channel (content-2 Dtest/Nand/banner.tpl).

The save-data banner shown in the Wii Data Management screen is one RGB5A3
192x64 texture: the wordmark 出前チャンネル in orange on an opaque white field
(rounded transparent corners) with the chef-and-bowl mascot raised above the
centre. The mascot carries no text. This redraws the wordmark as 음식 배달 채널
in the same orange Round Gothic B used for the Wii-menu wordmark (kwce.food_menu_art),
preserving the mascot pixel-for-pixel and the white field / rounded corners.

Only Dtest/Nand/banner.tpl changes; icon.tpl (mascot only, no text) is left as is.
Deterministic: the mascot is isolated by a bounded flood fill from the rows
above the wordmark cap line, so the same source WAD reproduces byte-identically.
revision >= 8.
"""
from collections import deque, Counter

from .channels import ChannelArchive
from .tpl import decode, encode, texture_records

BANNER = 'Dtest/Nand/banner.tpl'
WORD_KO = '음식 배달 채널'
SIZE = (192, 64)
FLOOR_Y = 44          # the mascot never extends below this row; the wordmark body is lower
WHITE = (255, 255, 255)


def _is_orange(c):
    r, g, b, a = c
    return a >= 90 and r > 165 and 30 < g < 205 and b < 125 and (r - b) > 70


def _chef_mask(img):
    """Mascot = orange pixels reachable from the rows ABOVE the wordmark cap line,
    bounded below by FLOOR_Y so the fill can never leak into the wordmark body."""
    W, H = img.size
    px = img.load()
    orange = [[_is_orange(px[x, y]) for y in range(H)] for x in range(W)]
    # cap line of the wordmark: the highest orange row among the left glyph columns
    # (x in [14,42]) that have no mascot above them.
    cap = min((y for x in range(14, 42) for y in range(H) if orange[x][y]), default=H)
    seedrow = max(1, cap - 2)
    seen = [[False] * H for _ in range(W)]
    q = deque()
    for x in range(W):
        for y in range(seedrow):
            if orange[x][y]:
                seen[x][y] = True
                q.append((x, y))
    while q:
        x, y = q.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny <= FLOOR_Y and orange[nx][ny] and not seen[nx][ny]:
                    seen[nx][ny] = True
                    q.append((nx, ny))
    return seen, cap


def _orange_colour(img):
    px = img.load(); W, H = img.size
    c = Counter(px[x, y][:3] for x in range(W) for y in range(H) if _is_orange(px[x, y]))
    return c.most_common(1)[0][0] + (255,)


def _render(img):
    from PIL import Image, ImageDraw
    from .food_menu_art import font as rgb_font
    W, H = img.size
    spx = img.load()
    seen, cap = _chef_mask(img)
    chef_px = sum(r.count(True) for r in seen)
    if not 300 <= chef_px <= 1400:
        raise ValueError('Food save-banner mascot isolation looks wrong: %d px' % chef_px)
    orange = _orange_colour(img)
    # White field with the stock alpha (keeps the rounded transparent corners); wordmark erased.
    canvas = img.copy(); cpx = canvas.load()
    for x in range(W):
        for y in range(H):
            if not seen[x][y]:
                cpx[x, y] = WHITE + (spx[x, y][3],)
    # Korean wordmark, one line, centred, fitted under a 30px cap.
    for size in range(30, 10, -1):
        face = rgb_font(size)
        l, t, r, b = face.getbbox(WORD_KO)
        if (r - l) <= W - 16 and (b - t) <= 30:
            break
    else:
        raise ValueError('Korean save-banner wordmark does not fit')
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    l, t, r, b = face.getbbox(WORD_KO)
    ImageDraw.Draw(layer).text(((W - (r - l)) / 2 - l, H - (b - t) - 2 - t), WORD_KO, font=face, fill=orange)
    out = Image.alpha_composite(canvas, layer); opx = out.load()
    for x in range(W):                       # mascot stays in front, exactly as stock
        for y in range(H):
            if seen[x][y]:
                opx[x, y] = spx[x, y]
    return out, dict(wordmark=WORD_KO, font='Round Gothic B %dpx' % size, orange='#%02x%02x%02x' % orange[:3],
                     mascot_px=chef_px, cap_row=cap, mascot_preserved=True)


def korean_save_banner(content2):
    """Return (content-2 with a Korean save-data banner, record). Only banner.tpl changes."""
    outer = ChannelArchive(content2)
    raw = outer.get(BANNER)
    recs = texture_records(raw)
    if len(recs) != 1 or (recs[0]['width'], recs[0]['height']) != SIZE or recs[0]['format'] != 5:
        raise ValueError('Food save banner is not a single 192x64 RGB5A3 texture')
    img = decode(raw, 0)
    new_img, record = _render(img)
    new_raw = encode(raw, 0, new_img)
    if len(new_raw) != len(raw):
        raise ValueError('Food save banner re-encode changed the TPL size')
    result = ChannelArchive(outer.replace(BANNER, new_raw))
    before = ChannelArchive(content2)
    if set(result.files) != set(before.files) or any(result.get(n) != before.get(n) for n in before.files if n != BANNER):
        raise ValueError('Food save-banner change escaped banner.tpl')
    record['file'] = BANNER
    return result.compact(), record

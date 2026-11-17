"""Photo Prints content 2: Korean operation guide picture, save-data banner and HOME network prompt (revision 12).

manual.jpg (556x257, baseline JPEG, 4:4:4) is the channel's only manual: a header
line and a five-row table (left cell = control, right cell = action) with Japanese
text baked in. The Korean picture keeps every pixel outside the text cells and the
control icons (A, B, +, +/-); each text cell is refilled with its own flat colour
and the Korean text is drawn in white with the console's 'Wii-kr_Round Gothic B'.
It is re-encoded with the original quantisation tables and 4:4:4 sampling, no
metadata, and must not grow past the original byte size.

banner.lz (TPL RGB5A3 192x64, LZ10) is taken to be the save-data banner shown in Wii
Options > Data Management (inferred: it and icon.lz 48x48 have the Wii save banner/icon
sizes); its 'デジカメプリントチャンネル' wordmark is replaced by
'디지털 카메라 프린트 채널' in the original wordmark colour (same supersampled
renderer as the Wii Menu banner, kwce.photoprints_menu_art). 'prints by FUJIFILM'
and the white background stay as they are.

HomeButton3/network.csv holds the HOME Menu quit prompt the channel loads for
network use. It has the seven columns JP..NL only (home.csv has ten: .. SC TC KO),
so a Korean console has no Korean prompt. Like Kirby TV, the row is extended to ten
columns; the Korean cell is the sentence of home.csv's 'Wii Menu' row so every glyph
is in the Korean HOME archive's partial font.
"""
import hashlib
import io
import re

from .channels import ChannelArchive, compress_lz10, load_library

MANUAL = 'manual.jpg'
BANNER = 'banner.lz'
NETWORK = 'HomeButton3/network.csv'
HOME = 'HomeButton3/home.csv'
MANUAL_SHA256 = '87b7d06b0251aa3ad7782232861c6d95d1b4922f43c87c2a6fa92a239693bf71'
MANUAL_SIZE = (556, 257)

# Measured on the original picture (1x pixels). Lines: x 5-6, 99-100, 550-551;
# y 22-23, 59, 95-96, 132, 168-169, 204-205.
HEADER_BOX = (0, 0, 556, 22)                      # black band above the table
ROWS = [(24, 59), (60, 95), (97, 132), (133, 168), (170, 204)]
LEFT_CELL = (7, 99)                               # x range inside the left column
RIGHT_CELL = (101, 550)                           # x range inside the right column
LEFT_FILL = (50, 50, 50)
RIGHT_FILL = (0, 0, 0)
TEXT_X = 110                                      # left edge of the original right-cell text
TEXT_RIGHT = 544                                  # keep >= 5 px before the right border
HEADER_X = 6
HEADER_RIGHT = 550
INK = (255, 255, 255)

HEADER_TEXT = '「디지털 카메라 프린트 채널」은 Wii 리모컨을 세로로 들고 조작합니다.'
LEFT_TEXT = {0: '포인터'}                           # rows 1-4 keep their icons (A, B, +, +/-)
ROW_TEXTS = ['가리킨 곳으로 커서 이동(포인터 맞추기)',
             '포인터를 맞춘 버튼이나 항목 선택',
             '이미지 확대 / 원래 크기로',
             '화면 중앙의 「선택한 이미지」나 상품을 좌우로 이동',
             '화면 아래의 「이미지 목록」을 좌우로 이동']
JAPANESE = {  # what each Korean text replaces (for the record and the review sheet)
    'header': '「デジカメプリントチャンネル」は Wiiリモコンを縦に持って操作します。',
    'left0': 'ポインター',
    'rows': ['向けた先にカーソルを動かす（ポイントする）', 'ポイントしたボタンや項目を選ぶ', '画像を拡大する / 元に戻す',
             '画面中央の「選んだ画像」や商品を左右に動かす', '画面下部の「画像の一覧」を左右に動かす']}
ROW_PX = 19        # largest size tried for the table text (the Japanese is ~20 px)
HEADER_PX = 16     # header line (the Japanese is ~15 px)
LEFT_PX = 18

BANNER_TITLE = '디지털 카메라 프린트 채널'
BANNER_BOX = (9, 20, 183, 33)        # ink box of the Japanese wordmark
BANNER_ERASE = (4, 17, 188, 37)      # white-filled before drawing (above 'prints by FUJIFILM', y >= 40)
BANNER_STROKE = 2                    # supersampled units (SS=4): +0.5 px weight, like the heavy original
NETWORK_SOURCE = 'This will quit the game. Proceed?\r\n(Anything not saved will be lost.)'
HOME_KOREAN_ROW = 2                  # home.csv row 'Return to the Wii Menu?' (0-based)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _font(px):
    from .photoprints_menu_art import _font as menu_font
    return menu_font(px)


def _ink_width(text, px):
    from PIL import Image, ImageDraw
    l, t, r, b = ImageDraw.Draw(Image.new('L', (1, 1))).textbbox((0, 0), text, font=_font(px))
    return r - l


def _fit_px(texts, start, width):
    for px in range(start, 11, -1):
        if all(_ink_width(t, px) <= width for t in texts):
            return px
    raise ValueError(f'Korean manual text does not fit: {texts!r}')


def _draw(draw, text, px, x, y_mid, *, centre=False):
    """Draw text with its ink box vertically centred on y_mid (and horizontally centred on x if centre)."""
    font = _font(px)
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    left = x - (r - l) / 2 - l if centre else x - l
    top = y_mid - (b - t) / 2 - t
    draw.text((round(left), round(top)), text, font=font, fill=INK)
    return dict(text=text, px=px, ink=[round(left + l), round(top + t), round(left + r), round(top + b)])


def _check_geometry(image):
    """The layout must be the one measured above (grid lines grey, cells flat)."""
    px = image.convert('L').load()
    lines = [(x, y) for y in (22, 59, 96, 132, 169, 205) for x in (60, 300, 500)]
    lines += [(x, y) for x in (6, 100, 550) for y in (40, 112, 186)]
    if any(px[x, y] < 100 for x, y in lines):
        raise ValueError('manual.jpg grid differs from the measured layout')
    rgb = image.convert('RGB').load()

    def near(p, ref, tol=6):
        return all(abs(a - b) <= tol for a, b in zip(p, ref))
    samples = [((20, 75), LEFT_FILL), ((12, 186), LEFT_FILL), ((480, 75), RIGHT_FILL), ((480, 115), RIGHT_FILL),
               ((2, 10), (0, 0, 0)), ((545, 10), (0, 0, 0)), ((300, 230), (0, 0, 0))]
    if not all(near(rgb[xy], ref) for xy, ref in samples):
        raise ValueError('manual.jpg cell colours differ from the measured layout')


def korean_manual(data):
    """Korean manual.jpg (bytes, record) from the original Japanese picture."""
    load_library()
    from PIL import Image, ImageDraw, JpegImagePlugin
    if sha(data) != MANUAL_SHA256:
        raise ValueError('manual.jpg differs from the pinned original')
    src = Image.open(io.BytesIO(data))
    if src.size != MANUAL_SIZE or src.info.get('progressive') or JpegImagePlugin.get_sampling(src) != 0:
        raise ValueError('manual.jpg format differs (expected 556x257 baseline 4:4:4)')
    _check_geometry(src)
    qtables = src.quantization
    image = src.convert('RGB')
    draw = ImageDraw.Draw(image)
    draw.rectangle((HEADER_BOX[0], HEADER_BOX[1], HEADER_BOX[2] - 1, HEADER_BOX[3] - 1), fill=(0, 0, 0))
    for y0, y1 in ROWS:
        draw.rectangle((RIGHT_CELL[0], y0, RIGHT_CELL[1] - 1, y1 - 1), fill=RIGHT_FILL)
    for row in LEFT_TEXT:
        y0, y1 = ROWS[row]
        draw.rectangle((LEFT_CELL[0], y0, LEFT_CELL[1] - 1, y1 - 1), fill=LEFT_FILL)
    header_px = _fit_px([HEADER_TEXT], HEADER_PX, HEADER_RIGHT - HEADER_X)
    row_px = _fit_px(ROW_TEXTS, ROW_PX, TEXT_RIGHT - TEXT_X)
    left_px = _fit_px(list(LEFT_TEXT.values()), LEFT_PX, LEFT_CELL[1] - LEFT_CELL[0] - 8)
    drawn = dict(header=_draw(draw, HEADER_TEXT, header_px, HEADER_X, (HEADER_BOX[1] + HEADER_BOX[3] - 1) / 2))
    drawn['rows'] = [_draw(draw, text, row_px, TEXT_X, (y0 + y1 - 1) / 2) for text, (y0, y1) in zip(ROW_TEXTS, ROWS)]
    drawn['left'] = {str(r): _draw(draw, t, left_px, (LEFT_CELL[0] + LEFT_CELL[1] - 1) / 2, (ROWS[r][0] + ROWS[r][1] - 1) / 2,
                                   centre=True) for r, t in LEFT_TEXT.items()}
    for item in [drawn['header']] + drawn['rows']:
        if item['ink'][2] > (HEADER_RIGHT if item is drawn['header'] else TEXT_RIGHT):
            raise ValueError(f'text overflows its cell: {item["text"]!r}')
    out = io.BytesIO()
    image.save(out, 'JPEG', qtables=qtables, subsampling=0, optimize=True, progressive=False, dpi=(72, 72))
    result = out.getvalue()
    check = Image.open(io.BytesIO(result))
    if check.size != MANUAL_SIZE or check.info.get('progressive') or JpegImagePlugin.get_sampling(check) != 0:
        raise ValueError('Korean manual.jpg format check failed')
    if len(result) > len(data):
        raise ValueError('Korean manual.jpg is larger than the original')
    return result, dict(file=MANUAL, original_sha256=MANUAL_SHA256, sha256=sha(result), bytes=len(result),
                        original_bytes=len(data), size=list(MANUAL_SIZE), jpeg='baseline, 4:4:4, original quantisation tables, '
                        'optimised Huffman, no EXIF/XMP', font='Wii-kr_Round Gothic B (console shared font)',
                        px=dict(header=header_px, rows=row_px, left=left_px), drawn=drawn, japanese=JAPANESE)


def korean_save_banner(lz):
    """Korean save-data banner (LZ10 TPL bytes, record)."""
    load_library()
    from libWiiPy.archive import decompress_lz77
    from PIL import Image
    from .channel_texture import texture_records
    from .photoprints_menu_art import SS, title_mask, _down
    from . import tpl
    raw = decompress_lz77(lz)
    rec = texture_records(raw)
    if len(rec) != 1 or (rec[0]['format'], rec[0]['width'], rec[0]['height']) != (5, 192, 64):
        raise ValueError('save banner is not one RGB5A3 192x64 texture')
    image = tpl.decode(raw, 0).convert('RGBA')
    px = image.load()
    blue = [px[x, y][:3] for y in range(BANNER_BOX[1], BANNER_BOX[3]) for x in range(BANNER_BOX[0], BANNER_BOX[2])
            if px[x, y][2] > 150 and px[x, y][0] < 150 and px[x, y][2] - px[x, y][0] > 60]
    if len(blue) < 400:
        raise ValueError('save banner wordmark not found where measured')
    colour = max(set(blue), key=blue.count)
    for y in range(BANNER_ERASE[1], BANNER_ERASE[3]):
        for x in range(BANNER_ERASE[0], BANNER_ERASE[2]):
            r, g, b, a = px[x, y]
            neutral = max(r, g, b) - min(r, g, b) < 20   # 'prints by FUJIFILM' is neutral dark grey
            if a != 255 or (neutral and min(r, g, b) < 230):
                raise ValueError('unexpected non-wordmark ink inside the erase box')
            px[x, y] = (255, 255, 255, 255)
    mask, fit = title_mask((192, 64), [(BANNER_TITLE, BANNER_BOX)], stroke=BANNER_STROKE)
    cov = _down(mask, (192, 64))
    ink = Image.new('RGBA', (192, 64), colour + (255,))
    ink.putalpha(cov)
    out = Image.alpha_composite(image, ink)
    texture = tpl.encode(raw, 0, out)
    if len(texture) != len(raw) or texture_records(texture)[0]['format'] != 5:
        raise ValueError('save banner TPL layout changed')
    packed = compress_lz10(texture)
    if decompress_lz77(packed) != texture:
        raise ValueError('save banner LZ10 roundtrip')
    return packed, dict(file=BANNER, texture='RGB5A3 192x64', title=BANNER_TITLE, colour=list(colour), stroke=BANNER_STROKE,
                        supersample=SS, fit=fit, erase_box=list(BANNER_ERASE), texture_sha256=sha(texture), sha256=sha(packed),
                        kept='prints by FUJIFILM, white background')


def _cells(data):
    if data[:2] != b'\xfe\xff':
        raise ValueError('Expected UTF-16BE CSV')
    return re.findall(r'"([^"]*)"', data[2:].decode('utf-16-be'))


def korean_network_csv(network, home):
    """Ten-column network.csv whose Korean cell is home.csv's Korean 'Wii Menu' prompt."""
    from .kirbytv_text import network_csv_korean
    home_cells = _cells(home)
    if len(home_cells) != 40:
        raise ValueError('Expected the four by ten HOME messages in home.csv')
    target = home_cells[HOME_KOREAN_ROW * 10 + 9]
    if not target.startswith('Wii 메뉴로 돌아가시겠습니까?'):
        raise ValueError('home.csv Korean Wii Menu prompt differs')
    out, rec = network_csv_korean(network, NETWORK_SOURCE, target)
    korean_home = set(''.join(home_cells[r * 10 + 9] for r in range(4)))
    if not set(target) <= korean_home:
        raise ValueError('network prompt uses a character outside the Korean HOME messages')
    return out, dict(rec, file=NETWORK, korean=target, korean_source='home.csv row 3 (Wii Menu prompt), Korean column',
                     sha256=sha(out))


def korean_content2(content2):
    """Content 2 with the three revision-12 files replaced; every other file byte-identical."""
    arc = ChannelArchive(content2)
    manual, manual_rec = korean_manual(arc.get(MANUAL))
    banner, banner_rec = korean_save_banner(arc.get(BANNER))
    network, network_rec = korean_network_csv(arc.get(NETWORK), arc.get(HOME))
    new = ChannelArchive(arc.replace(MANUAL, manual))
    new = ChannelArchive(new.replace(BANNER, banner))
    new = ChannelArchive(new.replace(NETWORK, network))
    data = new.compact()
    check = ChannelArchive(data)
    changed = sorted(n for n in arc.files if check.get(n) != arc.get(n))
    if changed != sorted([MANUAL, BANNER, NETWORK]) or set(check.files) != set(arc.files):
        raise ValueError(f'content 2 change escaped the three files: {changed}')
    return data, dict(changed_files=changed, manual=manual_rec, save_banner=banner_rec, network_prompt=network_rec)


def review_sheet(content2_before, content2_after, path):
    """Before/after sheet (manual 2x, save banner 3x) for the review record; <= 1600 px."""
    load_library()
    from libWiiPy.archive import decompress_lz77
    from PIL import Image, ImageDraw
    from . import tpl
    a, b = ChannelArchive(content2_before), ChannelArchive(content2_after)
    manuals = [Image.open(io.BytesIO(x.get(MANUAL))).convert('RGB').resize((1112, 514)) for x in (a, b)]
    banners = [tpl.decode(decompress_lz77(x.get(BANNER)), 0).convert('RGB').resize((576, 192), Image.NEAREST) for x in (a, b)]
    sheet = Image.new('RGB', (1192, 20 + 514 + 26 + 514 + 26 + 192 + 10), (40, 40, 60))
    d = ImageDraw.Draw(sheet)
    d.text((10, 4), 'manual.jpg original (2x)', fill=(255, 255, 0))
    sheet.paste(manuals[0], (10, 20))
    d.text((10, 540), 'manual.jpg Korean, revision 12 (2x)', fill=(255, 255, 0))
    sheet.paste(manuals[1], (10, 556))
    y = 556 + 514 + 10
    d.text((10, y), 'save banner original (3x)', fill=(255, 255, 0))
    d.text((606, y), 'save banner Korean, revision 12 (3x)', fill=(255, 255, 0))
    sheet.paste(banners[0], (10, y + 16))
    sheet.paste(banners[1], (606, y + 16))
    sheet.thumbnail((1600, 1600))
    sheet.save(path)
    return dict(size=list(sheet.size))

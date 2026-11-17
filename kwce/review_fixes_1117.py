"""Fixes from the 2026-11-16/17 full localization review (docs/reference/FULL_REVIEW_2026_11.md).

Nintendo Channel and Food Channel share the HOME "manual" (nwm) screen and its quit prompt:
  N2/F1  HOME -> 설명서 showed the Japanese "コントローラの使いかた" guide. A Korean console reads the
         default (Japanese) slot, so the *_jpn resources become Korean: title / note / button textures in
         HomeButton3/LZ77_homeBtn_nwm_jpn.arc and the body picture (Nintendo HomeButton3/Wiiware_guid_jpn.jpg,
         Food Dtest/Home/Demae_guide-00.jpg).
  N3/F2  "くわしい説明をみる" opened an empty yes/no prompt: the quit CSV (Nintendo HomeButton3/network.csv,
         Food Dtest/Home/network_nosave.csv) has no Korean text, so the default column was drawn with the
         Korean HOME subset font. All seven columns become QUIT_MESSAGE and the six syllables the subset
         lacks are added from the console's own Korean font (extend_native_font, glyphs not redrawn).
  N1     Nintendo movie panel "A 버튼을 눌러 시작해 주세요." used Promotion_RodinNTLGPro_DB_32_IA4.brfnt (no Hangul).
"""
import hashlib
import io
import re

from .channels import ROOT, ChannelArchive, load_library, compress_lz10

# v1 (nintendo build-v22 / food hardware-v19): three lines -- the HOME prompt shows only two, the
# save warning was cut off. v2 (build-v23 / hardware-v20): two lines like the English original.
QUIT_MESSAGES = {1: '채널을 종료합니다.\r\n계속하시겠습니까?\r\n(저장하지 않은 내용은 사라집니다.)',
                 2: '채널을 종료하시겠습니까?\r\n(저장하지 않은 내용은 사라집니다.)',
                 # v3 (build-v24 / hardware-v21): lines split short on the (wrong) guess that wide lines drop.
                 3: '채널을 종료하시겠습니까?\r\n저장하지 않은 내용은\r\n사라집니다.',
                 # v4 (build-v25 / hardware-v22): [Dolphin] this HOME prompt shows the text only up to the first
                 # line that ends in '?': v22 showed "…종료합니다. / 계속하시겠습니까?", v23/v24/diagnostic and the
                 # reset prompt showed only their "…까?" line. So the prompt ends at its question.
                 4: '채널을 종료합니다.\r\n계속하시겠습니까?'}
QUIT_MESSAGE = QUIT_MESSAGES[4]
SAVE_WARNING_LINE = re.compile(r'\(저장(?:하지|되지) 않은 내용은 사라집니다\.?\)')
SAVE_WARNING_SPLIT = '저장하지 않은 내용은\r\n사라집니다.'


def split_save_warning(data):
    """HOME message CSV (UTF-16 with BOM): the one-line save warning becomes two lines that fit."""
    if data[:2] not in (b'\xfe\xff', b'\xff\xfe'):
        raise ValueError('Unexpected HOME CSV encoding')
    big = data[:2] == b'\xfe\xff'
    text = data[2:].decode('utf-16-be' if big else 'utf-16-le')
    changed, count = SAVE_WARNING_LINE.subn(SAVE_WARNING_SPLIT, text)
    return data[:2] + changed.encode('utf-16-be' if big else 'utf-16-le'), count
GUIDE_TITLE = '조작 방법'
GUIDE_NOTE = '※ Wii 쇼핑 채널에서 더 자세한 설명을 볼 수 있습니다.'
GUIDE_BUTTON = '자세한 설명 보기'
NOTO = ROOT / 'workspace/channels/forecast/references/NotoSansKR.ttf'
MOVIE_PROMPT = 'A 버튼을 눌러 시작해 주세요.'

# body pictures: header line + table rows (text cell x range, label cell, row bounds) measured on the originals
GUIDES = {
    'nintendo': dict(
        header=((0, 0, 554, 31), 8, '닌텐도 채널은 Wii 리모컨을 세로로 잡고 조작합니다.'),
        label=((7, 33, 86, 69), '포인터'),
        rows=[((87, 33, 549, 69), '가리킨 곳으로 커서를 움직입니다 (포인트)'),
              ((87, 70, 549, 106), '가리킨 버튼이나 항목을 선택합니다'),
              ((87, 107, 549, 142), '첫 화면에서 영상 목록을 좌우로 넘깁니다'),
              ((87, 143, 549, 179), '화면이 위아래로 길게 이어질 때 화면을 스크롤합니다')]),
    'food': dict(
        header=((0, 0, 554, 27), 46, '음식 배달 채널은 Wii 리모컨을 세로로 잡고 조작합니다.'),
        label=((44, 29, 135, 58), '포인터'),
        rows=[((136, 29, 507, 58), '가리킨 곳으로 커서를 움직입니다 (포인트)'),
              ((75, 60, 507, 88), '가리킨 아이콘이나 버튼 등을 선택합니다'),
              ((75, 90, 507, 119), '누른 채 Wii 리모컨을 위아래로 움직여 스크롤합니다'),
              ((75, 120, 507, 149), '화면을 위아래로 스크롤합니다'),
              ((75, 150, 507, 179), 'HOME 버튼 메뉴를 표시합니다')]),
}


def _system_font(px):
    from .wiiroom_visual import _font
    return _font(px)


def _fit(draw, text, box_w, start, minimum=12):
    px = start
    while px > minimum:
        font = _system_font(px)
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        if r - l <= box_w:
            return font
        px -= 1
    return _system_font(minimum)


def guide_picture(jpeg, kind):
    """Original body JPEG -> same picture with the Japanese text cells redrawn in Korean (white)."""
    load_library()
    from PIL import Image, ImageDraw
    spec = GUIDES[kind]
    image = Image.open(io.BytesIO(jpeg)).convert('RGB')
    if image.size != (554, 256):
        raise ValueError('Unexpected guide picture size')
    draw = ImageDraw.Draw(image)

    def background(box):
        x0, y0, x1, y1 = box
        samples = sorted(image.getpixel((x, y)) for x in range(x0 + 2, x1 - 2, 3) for y in (y0 + 2, y1 - 3))
        return samples[len(samples) // 4]          # darker quartile: the cell colour, not the old letters

    (hbox, hx, htext) = spec['header']
    draw.rectangle(hbox, fill=background(hbox))
    font = _fit(draw, htext, hbox[2] - hx - 8, 19)
    l, t, r, b = draw.textbbox((0, 0), htext, font=font)
    draw.text((hx - l, (hbox[1] + hbox[3]) / 2 - (t + b) / 2), htext, font=font, fill=(255, 255, 255))
    lbox, ltext = spec['label']
    inner = (lbox[0] + 1, lbox[1] + 1, lbox[2] - 1, lbox[3] - 1)
    draw.rectangle(inner, fill=background(inner))
    font = _fit(draw, ltext, inner[2] - inner[0] - 6, 18)
    l, t, r, b = draw.textbbox((0, 0), ltext, font=font)
    draw.text(((inner[0] + inner[2]) / 2 - (l + r) / 2, (inner[1] + inner[3]) / 2 - (t + b) / 2), ltext, font=font, fill=(255, 255, 255))
    for box, text in spec['rows']:
        inner = (box[0] + 1, box[1] + 1, box[2] - 1, box[3] - 1)
        draw.rectangle(inner, fill=background(inner))
        font = _fit(draw, text, inner[2] - inner[0] - 14, 18)
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        draw.text((inner[0] + 7 - l, (inner[1] + inner[3]) / 2 - (t + b) / 2), text, font=font, fill=(255, 255, 255))
    out = io.BytesIO()
    image.save(out, 'JPEG', quality=92, subsampling=0)
    return out.getvalue()


def _mask(size, text, px, x0, center=False):
    load_library()
    from PIL import Image, ImageDraw
    w, h = size
    big = Image.new('L', (w * 4, h * 4))
    draw = ImageDraw.Draw(big)
    font = _fit(draw, text, (w - 2 * x0) * 4, px * 4, 12 * 4)
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    x = (w * 4 - (r - l)) / 2 - l if center else x0 * 4 - l
    draw.text((x, h * 2 - (t + b) / 2), text, font=font, fill=255)
    small = big.resize((w, h), Image.Resampling.LANCZOS)
    return Image.merge('RGBA', (small, small, small, small))


def nwm_archive(packed):
    """LZ77_homeBtn_nwm_jpn.arc (bare LZ10 stream) -> Korean title / note / button textures."""
    load_library()
    from libWiiPy.archive import decompress_lz77
    from . import tpl
    before = ChannelArchive(decompress_lz77(packed))
    archive = before
    for name, text, px, x0, center in (('arc/timg/it_ttl_wrd_a.tpl', GUIDE_TITLE, 30, 10, False),
                                       ('arc/timg/it_net_wrd.tpl', GUIDE_NOTE, 16, 17, True),
                                       ('arc/timg/it_btn_01.tpl', GUIDE_BUTTON, 26, 9, False)):
        raw = archive.get(name)
        w, h = tpl.texture_records(raw)[0]['width'], tpl.texture_records(raw)[0]['height']
        archive = ChannelArchive(archive.replace(name, tpl.encode(raw, 0, _mask((w, h), text, px, x0, center))))
    raw = ChannelArchive(archive.compact()).compact()
    after = ChannelArchive(raw)
    changed = sorted(p for p in before.files if before.get(p) != after.get(p))
    if set(after.files) != set(before.files) or changed != ['arc/timg/it_btn_01.tpl', 'arc/timg/it_net_wrd.tpl', 'arc/timg/it_ttl_wrd_a.tpl']:
        raise ValueError('nwm change escaped its three textures')
    stream = compress_lz10(raw)
    if decompress_lz77(stream) != raw:
        raise ValueError('nwm compression roundtrip')
    return stream


def quit_csv(data, message=QUIT_MESSAGE):
    """Seven-language quit prompt CSV (UTF-16 BE with BOM) -> QUIT_MESSAGE in every column."""
    if data[:2] != b'\xfe\xff':
        raise ValueError('Unexpected quit CSV encoding')
    text = data[2:].decode('utf-16-be')
    cells = list(re.finditer(r'"([^"]*)"', text))
    if len(cells) != 7 or not cells[0].group(1).startswith('ゲームを終了します'):
        raise ValueError('Unknown quit CSV')
    for m in reversed(cells):
        text = text[:m.start(1)] + message + text[m.end(1):]
    return b'\xfe\xff' + text.encode('utf-16-be')


def home_fonts(archive, folders=('HomeButton2', 'HomeButton3'), message=QUIT_MESSAGE):
    """Every LZ77_homeBtn*.arc (not nwm) of the given HOME folders: subset font + QUIT_MESSAGE glyphs."""
    load_library()
    from libWiiPy.archive import decompress_lz77
    from .channel_korean_font import korean_shared_fonts
    from .wbf_text import WiiFontRenderer
    from .wiiroom_manual_font_v42 import extend_native_font
    native, _ = korean_shared_fonts()
    renderer = WiiFontRenderer(ChannelArchive(native).get('wbf2.brfna'))
    cache, done = {}, []
    for name in sorted(archive.files):
        folder, _, leaf = name.partition('/')
        if folder not in folders or not leaf.startswith('LZ77_homeBtn') or 'nwm' in leaf:
            continue
        packed = archive.get(name)
        key = hashlib.sha256(packed).hexdigest()
        if key not in cache:
            inner = ChannelArchive(decompress_lz77(packed))
            fonts = [p for p in inner.files if p.endswith('.brfnt')]
            if len(fonts) != 1:
                raise ValueError('HOME font identity')
            font, record = extend_native_font(inner.get(fonts[0]), renderer, message)
            rebuilt = ChannelArchive(ChannelArchive(inner.replace(fonts[0], font)).compact()).compact()
            stream = (b'LZ77' if packed[:4] == b'LZ77' else b'') + compress_lz10(rebuilt)
            if decompress_lz77(stream) != rebuilt:
                raise ValueError('HOME archive compression roundtrip')
            cache[key] = (stream, record)
        archive = ChannelArchive(archive.replace(name, cache[key][0]))
        done.append(dict(file=name, **cache[key][1]))
    if not done:
        raise ValueError('No HOME archives found')
    return archive, done


def promotion_fonts(archive, prompt=MOVIE_PROMPT):
    """Nintendo content 5 font/{E,F,S}/Promotion_RodinNTLGPro_DB_32_IA4.brfnt + the movie prompt's Hangul."""
    from .channel_font import extend_font
    records = []
    for name in sorted(p for p in archive.files if p.startswith('font/') and p.endswith('Promotion_RodinNTLGPro_DB_32_IA4.brfnt')):
        font, record = extend_font(archive.get(name), prompt, NOTO)
        archive = ChannelArchive(archive.replace(name, font))
        records.append(dict(file=name, **record))
    if not records:
        raise ValueError('Promotion fonts not found')
    return archive, records


# I1: the 240004 error PAGE heading ignores the english.lng "\\n" breaks (Opera breaks between any two
# syllables there) and showed "240004: 이 주소는 인터넷 채널에 / 서 사용할 수 없습니다." [Dolphin]. One line
# holds about ten syllables at h1 110 %, so the heading becomes a nine-syllable sentence; the page body
# still explains the address problem.
INTERNET_LNG = {'-1504149836': ('240004: 이 주소는\\n인터넷 채널에서\\n사용할 수 없습니다.', '240004: 쓸 수 없는 주소입니다.')}


def internet_lng(data):
    text = data.decode('utf-8')
    for key, (old, new) in INTERNET_LNG.items():
        line = f'{key}="{old}"'
        if text.count(line) != 1:
            raise ValueError(f'english.lng entry {key} not found once')
        text = text.replace(line, f'{key}="{new}"')
    return text.encode('utf-8')


# K1: Kirby TV key help (help/keys/key_1..3) wrapped inside words: the service text's '</br>' is
# dropped by the Flash text field, so the Korean overlay strings now carry '<br/>' like the other Korean
# entries (configs/kirbytv-ui-v5-ko.json). Derived from the parent SWF: only those constant-pool strings
# change (a from-scratch Linux rebuild re-encodes manual.jpg and nwKO.arc -> hardware-v12 not used).
def _push_replace(payload, mapping, hits):
    """Re-encode an AVM1 Push payload with inline (type 0) strings swapped by mapping."""
    import struct
    at, out = 0, bytearray()
    while at < len(payload):
        kind = payload[at]
        if kind == 0:
            end = payload.index(0, at + 1)
            text = payload[at + 1:end].decode('utf-8')
            if text in mapping:
                hits[text] += 1; text = mapping[text]
            out += b'\x00' + text.encode('utf-8') + b'\x00'; at = end + 1; continue
        size = {1: 4, 2: 0, 3: 0, 4: 1, 5: 1, 6: 8, 7: 4, 8: 1, 9: 2}[kind]
        out += payload[at:at + 1 + size]; at += 1 + size
    return bytes(out)


def kirbytv_swf(swf, mapping):
    from . import kirbytv_swf as S
    signature, version, data = S.unpack(swf)
    replacements, hits = {}, {old: 0 for old in mapping}
    for index, (code, pos, head, length) in enumerate(S.tags(data)):
        if code not in (S.TAG_DO_INIT, 12):
            continue
        raw = data[pos + head:pos + head + length]
        prefix, body = (raw[:2], raw[2:]) if code == S.TAG_DO_INIT else (b'', raw)
        if not any(old.encode() in body for old in mapping):
            continue
        acts = S.parse(body)
        before = dict(hits)
        strings = S.pool(acts)
        if any(old in strings for old in mapping):
            raise ValueError('Help string in a constant pool (not expected)')
        for act in acts:
            if act.op == 0x96 and any(old.encode() in act.payload for old in mapping):
                act.payload = _push_replace(act.payload, mapping, hits)
        if hits == before:
            raise ValueError('Help string bytes found outside Push actions')
        replacements[index] = prefix + S.serialize(acts)
    if any(n != 1 for n in hits.values()):
        raise ValueError(f'Help strings not found exactly once: {hits}')
    return S.pack(S.replace_tags(data, replacements), signature), sorted(replacements)

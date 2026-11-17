"""Korean-console Wii Menu banner/icon fix for Kirby TV (content 0, revision 5).

The Korean System Menu shows only the 'KOR' language group of a channel banner or icon
(external/wii-ipl iplChannelObj::setLangPane: every language group is hidden, then the
console-language group is shown; the Korean-area fallback list is just KOR). The European
banner carries ENG/GER/ITA/FRA logo groups and no KOR group, so on a Korean console the
whole logo (banner) and the tube/Kirby/TV/word pieces (icon) stay hidden.

This module renames the ENG group to KOR in banner.brlyt and icon.brlyt (16-byte group
name field, grp1 sections only) so the English artwork is what a Korean console shows, and
redraws the icon's small 'Channel' word texture as '채널' in the same white-on-navy style.
The banner's big logo keeps its English 'Channel' (it is baked into the logo artwork).
Animations, other textures and the layouts' pane data are byte-identical.

Revision 8 (logos=kirbytv_logo.korean_logo_set(...)): the banner's Logo_English.tpl gets the
Korean '채널' word as well (only the 4x4 blocks around the word change) and the icon word uses
the same lettering at icon size.
"""
import hashlib
import struct

from .channels import ChannelArchive, compress_lz10, load_library
from . import tpl

IMET_AT = 0x80
ARCHIVE_AT = 0x640
SIZE_FIELD = {'meta/icon.bin': 0x8C, 'meta/banner.bin': 0x90}
ICON_WORD = 'ENG_channel.tpl'
WORD = '채널'


def rename_group(brlyt, old=b'ENG', new=b'KOR'):
    """Rename one grp1 group; refuse if the new name already exists or the old is absent."""
    data = bytearray(brlyt)
    pos, hits, existing = 0x10, [], False
    while pos + 8 <= len(data):
        size = struct.unpack_from('>I', data, pos + 4)[0]
        if size < 8:
            break
        if data[pos:pos + 4] == b'grp1':
            name = bytes(data[pos + 8:pos + 0x18]).split(b'\0')[0]
            if name == old:
                hits.append(pos)
            elif name == new:
                existing = True
        pos += size
    if existing or len(hits) != 1:
        raise ValueError(f'group rename {old!r}->{new!r}: found {len(hits)}, target exists={existing}')
    data[hits[0] + 8:hits[0] + 0x18] = new.ljust(16, b'\0')
    return bytes(data)


def _navy(image):
    """Darkest opaque colour of the original word (its outline)."""
    best = None
    for r, g, b, a in image.getdata():
        if a > 200:
            lum = r * 299 + g * 587 + b * 114
            if best is None or lum < best[0]:
                best = (lum, (r, g, b))
    return best[1] if best else (16, 32, 96)


STYLES = {1: dict(size=0.86, stroke=0.11),   # build-v5 (outline too heavy; kept reproducible)
          2: dict(size=0.92, stroke=0.055),  # build-v6 (outline ok, fill too light; kept reproducible)
          3: dict(size=0.95, stroke=0.06, bold=0.045)}  # build-v7+: emboldened fill + thin navy outline


def korean_word(original, text=WORD, style=1):
    """Redraw the word in white with the original's navy outline, slightly italic, fitted to the tile."""
    load_library()
    from PIL import Image, ImageDraw
    from .wiiroom_visual import _font
    w, h = original.size
    navy = _navy(original)
    s = 8
    W, H = w * s, h * s
    size = int(H * STYLES[style]['size'])
    font = _font(size)
    stroke = max(2, int(H * STYLES[style]['stroke']))
    bold = int(H * STYLES[style].get('bold', 0))
    probe = Image.new('L', (W * 2, H * 2))
    box = ImageDraw.Draw(probe).textbbox((0, 0), text, font=font, stroke_width=stroke + bold)
    tw, th = box[2] - box[0], box[3] - box[1]
    shear = 0.18
    scale = min((W * 0.94) / (tw + shear * th), (H * 0.94) / th, 1.0)
    canvas = Image.new('RGBA', (int(tw + shear * th) + 4 * s, th + 4 * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    origin = (2 * s - box[0] + shear * th, 2 * s - box[1])
    if bold:
        # navy outline around an emboldened white body: outline pass, then the white body widened by 'bold'
        d.text(origin, text, font=font, fill=navy + (255,), stroke_width=stroke + bold, stroke_fill=navy + (255,))
        d.text(origin, text, font=font, fill=(255, 255, 255, 255), stroke_width=bold, stroke_fill=(255, 255, 255, 255))
    else:
        d.text(origin, text, font=font, fill=(255, 255, 255, 255),
               stroke_width=stroke, stroke_fill=navy + (255,))
    canvas = canvas.transform(canvas.size, Image.Transform.AFFINE, (1, shear, 0, 0, 1, 0),
                              resample=Image.Resampling.BICUBIC)
    canvas = canvas.resize((max(1, int(canvas.width * scale)), max(1, int(canvas.height * scale))),
                           Image.Resampling.LANCZOS)
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    bb = canvas.getbbox() or (0, 0, canvas.width, canvas.height)
    crop = canvas.crop(bb)
    out.alpha_composite(crop, ((W - crop.width) // 2, (H - crop.height) // 2))
    out = out.resize((w, h), Image.Resampling.LANCZOS)
    return out


def _repack(wrapped_payload_archive):
    raw = wrapped_payload_archive.compact()
    payload = b'LZ77' + compress_lz10(raw)
    return raw, b'IMD5' + len(payload).to_bytes(4, 'big') + bytes(8) + hashlib.md5(payload).digest() + payload


BANNER_LOGO = 'Logo_English.tpl'


def korean_banner_art(content, style=1, logos=None):
    """logos (revision 8+): kirbytv_logo.korean_logo_set() result; the banner logo then reads
    '채널' as well and the icon word comes from the same lettering (style argument unused)."""
    load_library()
    from libWiiPy.archive import decompress_lz77
    if content[IMET_AT:IMET_AT + 4] != b'IMET':
        raise ValueError('Kirby TV banner: IMET not at 0x80')
    prefix = bytearray(content[:ARCHIVE_AT])
    outer = ChannelArchive(content[ARCHIVE_AT:])
    record = {}
    for member in ('meta/banner.bin', 'meta/icon.bin'):
        wrapped = outer.get(member)
        if wrapped[:4] != b'IMD5' or hashlib.md5(wrapped[32:]).digest() != wrapped[16:32]:
            raise ValueError('Kirby TV banner integrity')
        arc = ChannelArchive(decompress_lz77(wrapped[32:]))
        before = arc
        layout = next(p for p in arc.files if p.endswith('.brlyt'))
        arc = ChannelArchive(arc.replace(layout, rename_group(arc.get(layout))))
        changed = [layout]
        extra = {}
        if member.endswith('icon.bin'):
            path = next(p for p in arc.files if p.endswith('/' + ICON_WORD))
            raw = arc.get(path)
            image = tpl.decode(raw, 0)
            word = logos['icon_word'] if logos else korean_word(image, style=style)
            arc = ChannelArchive(arc.replace(path, tpl.encode(raw, 0, word)))
            changed.append(path)
        elif logos:
            from .kirbytv_logo import tpl_replace_changed
            path = next(p for p in arc.files if p.endswith('/' + BANNER_LOGO))
            raw = arc.get(path)
            image = tpl.decode(raw, 0)
            korean, extra = logos['banner_logo'](image)
            data, blocks = tpl_replace_changed(raw, 0, image, korean)
            extra['changed_blocks'] = blocks
            arc = ChannelArchive(arc.replace(path, data))
            changed.append(path)
        for p in before.files:
            if p not in changed and arc.get(p) != before.get(p):
                raise ValueError('Kirby TV banner: unrelated resource changed')
        raw, rewrapped = _repack(arc)
        outer = ChannelArchive(outer.replace(member, rewrapped))
        struct.pack_into('>I', prefix, SIZE_FIELD[member], len(raw))
        record[member] = dict(changed=changed, group='ENG->KOR')
        if extra:
            record[member]['banner_logo'] = extra
    record['icon_word'] = WORD
    if logos:
        record['icon_word_style'] = 'kirbytv_logo icon'
        record['banner_logo'] = 'Korean 채널 lettering (kirbytv_logo, Kirby/TV/screen artwork kept)'
        return bytes(prefix) + outer.compact(), record
    if style != 1:
        record['icon_word_style'] = STYLES[style]
    record['banner_logo'] = 'English artwork kept (Channel baked into the logo)'
    return bytes(prefix) + outer.compact(), record

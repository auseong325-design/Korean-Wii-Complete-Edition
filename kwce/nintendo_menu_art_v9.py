"""Korean Nintendo Channel wordmark, revision 9: one lettering for the Wii Menu banner, the
Wii Menu icon and the in-channel opening logo.

Why v9 (user hardware report 2026-10-29): the v8 glyphs were fitted one by one into their
tiles (different sizes and baselines, light weight) and the letters sat on fixed slots, so
'닌텐도 채널' looked uneven and loosely spaced; the icon kept its US language groups with no
KOR group, which the Korean System Menu hides (iplChannelObj::setLangPane shows only KOR);
and the channel's own opening still spelled 'Nintendo Channel' in English.

Lettering rules (shared by every surface):
  * the console's Korean system font (Round Gothic B, as on the Korean Wii Menu's own
    channel titles), ONE font size and ONE baseline for all five syllables;
  * glyph height matched to the US letters' cap height on screen;
  * positions computed from each syllable's ink width: a tight, even gap inside a word and
    one word space between 닌텐도 and 채널, the whole title centred where the US title was.
The US layouts, pane scales, colours and animation curves stay as they are (the letter
animations carry no X-translation tracks, so static X positions are what the screen shows).

Revision 13 (user hardware report: the title read '닌텐도채널' with no word space): revisions 9-12
spaced the tiles by the font's getbbox(), which for a single syllable is the ADVANCE box (54.4 px,
identical for all five), not the ink. The visible ink gaps were then the font's side bearings plus
the gap, so the 14 px word space only showed as 19 px against 12-17 px inside the words. Revision 13
keeps the v12 glyph textures byte for byte (same size, baseline, weight) and moves only the panes:
ink-to-ink gaps of 14.5 px inside a word (the v12 average) and 32 px at the word break (the font's
own '닌텐도 채널' word gap plus the v12 tracking), the ink row centred on the US title's ink centre.

Revision 14 (user hardware report RC5: the Wii Menu icon showed the Japanese 'みんなの ニンテンドーチャンネル'):
the icon is a channel-script icon. Content 2 arc/icon.cs.lz7 (unchanged since the originals) runs
setRegionPanes on every draw: it hides every logo pane and shows ONE by System.SCGetLanguage(), and for
SC_LANG_KOREAN (like both Chinese languages) it shows P_logoJ_00, whose texture is the Japanese logo.
The KOR group rename of revisions 9-13 only reaches the static N_chIcon_00 logos, which that script
hides. v8 had swapped the P_logoJ/P_logoE pane names (Dolphin showed the Korean icon); v9 dropped it.
Revision 14 swaps P_logoJ_00 <-> P_logoE_00 again in icon.brlyt and the icon animations, so the pane
the script shows for Korean is the US E pane with the Korean wordmark (US geometry and slide curve).
Lettering, banner and opening are byte for byte revision 13.
"""
import hashlib
import struct

from .channels import ChannelArchive, compress_lz10, layout_sections, load_library, rebuild_layout
from .votes_visual import _materials, _textures
from .nintendo_menu_art_v8 import swap_names
from . import tpl

# (syllable, front pane, reflection pane, texture slot) - the v8 slot choice keeps the
# letters' staggered animation timing spread over both words.
TITLE = [('닌', 'P_E_N_00', 'P_E_N_01', 'tr_na_00.tpl'),
         ('텐', 'P_E_n_00', 'P_E_n_04', 'tr_nn_01.tpl'),
         ('도', 'P_E_e_00', 'P_E_e_02', 'tr_no_00.tpl'),
         ('채', 'P_E_C_00', 'P_E_C_01', 'tr_ni_00.tpl'),
         ('널', 'P_E_h_00', 'P_E_h_01', 'tr_nn_00.tpl')]
WORD_BREAK = 3          # space after the third syllable
TILE = 56               # tr_* glyph textures are 56x56
SS = 8                  # supersampling
# revision 9: spacing computed at the layout's STATIC scale 1.5 (the letters' animation start), which
#   made the gaps 1.5x too wide once the letters settle at scale 1.0 -- kept only for reproduction.
# revision 10: spacing at the animated REST scale (the last sX key, checked == 1.0), larger glyphs.
STYLES = {9: dict(glyph_h=44, gap=3.0, space=13.0, rest_from_anim=False),
          10: dict(glyph_h=48, gap=3.5, space=14.0, rest_from_anim=True),
          # revision 11: v10 + 10% larger letter panes (still no size tracks in the animations) and a
          # slightly heavier stroke, so the five syllables carry the visual weight of the US title.
          11: dict(glyph_h=48, gap=3.5, space=14.0, rest_from_anim=True, pane_scale=1.1, bold_px=0.45),
          # revision 12: v11 lettering + a 12-row, slightly bold icon wordmark (legible at icon size).
          12: dict(glyph_h=48, gap=3.5, space=14.0, rest_from_anim=True, pane_scale=1.1, bold_px=0.45,
                   icon_rows=12, icon_bold_px=0.375),
          # revision 13: v12 glyphs/icon unchanged; gap/space are INK-to-ink px (see ink_positions).
          13: dict(glyph_h=48, gap=14.5, space=32.0, rest_from_anim=True, pane_scale=1.1, bold_px=0.45,
                   icon_rows=12, icon_bold_px=0.375, ink_spacing=True)}
# revision 14: revision 13 lettering + the icon pane the channel script shows for Korean (see docstring).
STYLES[14] = dict(STYLES[13], icon_script_pane=True)
# revision 15 (candidate 'H' of workspace/private/rc6-work/W-Nintendo-titles.png): the round stroke
# +1.0 px per side (stroke/height 0.10 -> 0.12, the US title's capitals; +1.1 starts to fill the ㄹ of
# 널 and join ㅊ to ㅏ in 채), US-like tracking (ink gaps 9 px in a word = 7.8 units vs the US 6.5,
# 27 px word space = 23.4 units vs 24.4), letter panes 5% larger, and an icon wordmark in the same
# lettering: 13 rows, slightly bold, 15% wider, tracked like the title. Plus the revision 14 icon pane.
STYLES[15] = dict(glyph_h=48, gap=9.0, space=27.0, rest_from_anim=True, pane_scale=1.155, bold_px=1.0,
                  ink_spacing=True, tile_check_v=True, icon_rows=13, icon_bold_px=0.5, icon_x_scale=1.15,
                  icon_gap=1.5, icon_space=5.0, icon_script_pane=True)
# revision 16 (user choice 2026-11-16, sheet items 3-B and 4 "A + reflection"): the banner letters
# 1.3 px heavier per side and 1.5x larger panes with 8/26 px ink gaps (the v15 title read sparse on the
# console); the icon wordmark one line in all 14 rows above the US mirror axis, 0.6 px bold, 1.45x wide
# (~108 of 120 px like the US "Nintendo Channel"), with the unfaded mirror the US bitmap also carries.
STYLES[16] = dict(STYLES[15], bold_px=1.3, pane_scale=1.5, gap=8.0, space=26.0,
                  icon_rows=14, icon_bold_px=0.6, icon_x_scale=1.45, icon_gap=2.0, icon_space=6.0)
# the icon logo panes swapped for the channel script (P_logoJ_00 is what SC_LANG_KOREAN turns on)
ICON_SCRIPT_PANES = [('P_logoJ_00', 'P_logoE_00')]
GLYPH_H, GAP, SPACE = 44, 3.0, 13.0


def _font(px):
    from .wiiroom_visual import _font as shared_font
    return shared_font(px)


def glyphs(revision=9):
    """{syllable: (RGBA white-on-alpha 56x56 image, box width px, (ink left, ink right) px)} with one
    size and baseline. The box width is font.getbbox() (the advance box for one syllable; what
    revisions 9-12 spaced by); the ink edges come from the drawn supersampled glyph (revision 13+)."""
    GLYPH_H = STYLES[revision]['glyph_h']
    load_library()
    from PIL import Image, ImageDraw
    text = [t[0] for t in TITLE]
    # find the font size whose tallest syllable ink equals GLYPH_H
    size = GLYPH_H * SS
    for _ in range(6):
        font = _font(size)
        boxes = [font.getbbox(c) for c in text]
        top, bottom = min(b[1] for b in boxes), max(b[3] for b in boxes)
        size = int(round(size * (GLYPH_H * SS) / (bottom - top)))
    font = _font(size)
    bold = int(round(STYLES[revision].get('bold_px', 0) * SS))
    boxes = {c: font.getbbox(c, stroke_width=bold) for c in text}
    top, bottom = min(b[1] for b in boxes.values()), max(b[3] for b in boxes.values())
    n = TILE * SS
    out = {}
    for c in text:
        b = boxes[c]
        im = Image.new('L', (n, n))
        x = (n - (b[2] - b[0])) / 2 - b[0]
        y = (n - (bottom - top)) / 2 - top
        ImageDraw.Draw(im).text((x, y), c, font=font, fill=255, stroke_width=bold, stroke_fill=255)
        small = im.resize((TILE, TILE), Image.Resampling.LANCZOS)
        ink = im.getbbox()
        if STYLES[revision].get('ink_spacing') and (ink is None or ink[0] <= 0 or ink[2] >= n):
            raise ValueError('glyph ink touches the tile edge: ' + c)
        if STYLES[revision].get('tile_check_v') and (ink[1] <= 0 or ink[3] >= n):
            raise ValueError('glyph ink touches the tile top/bottom: ' + c)
        out[c] = (Image.merge('RGBA', (small, small, small, small)), (b[2] - b[0]) / SS,
                  (ink[0] / SS, ink[2] / SS))
    return out


def positions(widths, unit, centre, gap=GAP, space=SPACE):
    """Front-pane X centres (layout units) for the ink widths (px) at 'unit' units per px."""
    gaps = [space if i == WORD_BREAK - 1 else gap for i in range(len(widths) - 1)]
    total = sum(widths) + sum(gaps)
    x = -total / 2
    centres = []
    for i, w in enumerate(widths):
        centres.append(centre + (x + w / 2) * unit)
        x += w + (gaps[i] if i < len(gaps) else 0)
    return centres


def ink_positions(inks, unit, centre, gap, space):
    """Tile-centre X (layout units) so that the INK gaps between neighbouring syllables are exactly
    'gap' px inside a word and 'space' px at the word break, the ink row centred on 'centre'.
    inks: [(left, right)] ink edges in tile px (0..TILE); unit: layout units per tile px at rest."""
    gaps = [space if i == WORD_BREAK - 1 else gap for i in range(len(inks) - 1)]
    total = sum(r - l for l, r in inks) + sum(gaps)
    x = -total / 2
    centres = []
    for i, (left, right) in enumerate(inks):
        centres.append(centre + (x - (left - TILE / 2)) * unit)
        x += (right - left) + (gaps[i] if i < len(gaps) else 0)
    return centres


def _us_ink_centre(archive, sections, fronts, mat, materials, textures):
    """Centre (layout units) of the visible US title letters' ink at rest (texture alpha > 24,
    stretched over the pane, centre origin, default texcoords)."""
    lo, hi = [], []
    for name, i in fronts.items():
        s = sections[i]
        if not (s[8] & 1) or struct.unpack_from('>f', s, 0x40)[0] < 0 or s[9] != 4:
            continue
        x, w = struct.unpack_from('>f', s, 0x24)[0], struct.unpack_from('>f', s, 0x44)[0]
        texture = textures[struct.unpack_from('>H', mat, materials[name] + 0x40)[0]]
        path = next(p for p in archive.files if p.endswith('/timg/' + texture))
        image = tpl.decode(archive.get(path), 0).convert('RGBA')
        box = image.split()[3].point(lambda v: 255 if v > 24 else 0).getbbox()
        if box:
            lo.append(x - w / 2 + box[0] * w / image.size[0])
            hi.append(x - w / 2 + box[2] * w / image.size[0])
    if not lo:
        raise ValueError('US title ink not found')
    return (min(lo) + max(hi)) / 2


def _rest_scale(archive, panes):
    """Last animated sX key of the title letters (they settle there); must be one common value."""
    import struct as _s
    from .disk_dvd_anim import _contents
    finals = set()
    for path in [p for p in archive.files if p.endswith('.brlan')]:
        raw = archive.get(path)
        for name, material, tags in _contents(raw):
            if material or name not in panes:
                continue
            for at, kind, tracks in tags:
                for te, target, curve, keys in tracks:
                    if kind == b'RLPA' and target == 6 and len(keys) >= 2:  # single keys are start-state holds
                        last = max(keys, key=lambda k: _s.unpack_from('>f', raw, k)[0])
                        finals.add(round(_s.unpack_from('>f', raw, last + 4)[0], 4))
    if len(finals) != 1:
        raise ValueError(f'title letters do not share one rest scale: {sorted(finals)}')
    return finals.pop()


def _apply_title(archive, layout_path, glyph_set, revision=9):
    """Point the five US letter panes (and reflections) at the Korean glyph textures, place them,
    hide the other US letters. Returns (archive, record)."""
    sections = layout_sections(archive.get(layout_path))
    matidx = next(i for i, s in enumerate(sections) if s[:4] == b'mat1')
    materials = _materials(sections[matidx])
    textures = _textures(next(s for s in sections if s[:4] == b'txl1'))
    mat = bytearray(sections[matidx])
    fronts = {}
    for i, s in enumerate(sections):
        if s[:4] == b'pic1':
            name = s[12:28].split(b'\0')[0].decode('ascii')
            if name.startswith('P_E_'):
                fronts[name] = i
    used = {n for t in TITLE for n in (t[1], t[2])}
    if not used <= set(fronts):
        raise ValueError('US title panes missing in ' + layout_path)
    # geometry of the US title: centre between its first and last letter, display units per glyph px
    xs = [struct.unpack_from('>f', sections[fronts[n]], 0x24)[0] for n in fronts if n.endswith('_00')]
    first = sections[fronts['P_E_N_00']]
    w, sx = struct.unpack_from('>f', first, 0x44)[0], struct.unpack_from('>f', first, 0x3c)[0]
    style = STYLES[revision]
    if style['rest_from_anim']:
        sx = _rest_scale(archive, {t[1] for t in TITLE})
    grow = style.get('pane_scale', 1.0)
    w *= grow
    unit = w * sx / TILE
    centre = (min(xs) + max(xs)) / 2
    if style.get('ink_spacing'):
        centre = _us_ink_centre(archive, sections, fronts, mat, materials, textures)
        inks = [glyph_set[t[0]][2] for t in TITLE]
        centres = ink_positions(inks, unit, centre, style['gap'], style['space'])
    else:
        widths = [glyph_set[t[0]][1] for t in TITLE]
        centres = positions(widths, unit, centre, style['gap'], style['space'])
    placed = {}
    for (syllable, front, back, texture), x in zip(TITLE, centres):
        for name in (front, back):
            pane = bytearray(sections[fronts[name]])
            struct.pack_into('>f', pane, 0x24, float(round(x, 2)))
            if grow != 1.0:
                pw, ph = struct.unpack_from('>ff', pane, 0x44)
                struct.pack_into('>ff', pane, 0x44, float(round(pw * grow, 3)), float(round(ph * grow, 3)))
            pane[8] |= 1
            sections[fronts[name]] = bytes(pane)
            struct.pack_into('>H', mat, materials[name] + 0x40, textures.index(texture))
        placed[syllable] = round(x, 2)
    hidden = 0
    for name, i in fronts.items():
        if name not in used:
            pane = bytearray(sections[i])
            pane[8] &= 0xfe
            sections[i] = bytes(pane)
            hidden += 1
    sections[matidx] = bytes(mat)
    archive = ChannelArchive(archive.replace(layout_path, rebuild_layout(archive.get(layout_path), sections)))
    for _, _, _, texture in TITLE:
        name = next(p for p in archive.files if p.endswith('/timg/' + texture))
        original = archive.get(name)
        if tpl.decode(original, 0).size != (TILE, TILE):
            raise ValueError('Unexpected glyph texture ' + texture)
    for syllable, _, _, texture in TITLE:
        name = next(p for p in archive.files if p.endswith('/timg/' + texture))
        original = archive.get(name)
        archive = ChannelArchive(archive.replace(name, tpl.encode(original, 0, glyph_set[syllable][0])))
    record = dict(layout=layout_path, centre=round(centre, 2), unit=round(unit, 4), x=placed,
                  hidden_us_letters=hidden, glyph_height_px=style['glyph_h'], gap_px=style['gap'],
                  space_px=style['space'])
    if style.get('ink_spacing'):
        record.update(spacing='ink', ink_row=[round(centres[0] + (inks[0][0] - TILE / 2) * unit, 2),
                                              round(centres[-1] + (inks[-1][1] - TILE / 2) * unit, 2)])
    return archive, record


def banner_archive(before, glyph_set, revision=9):
    archive, record = _apply_title(before, 'arc/blyt/banner.brlyt', glyph_set, revision)
    # As in v8: a Korean console takes the J parent of the banner title; give that name to the US
    # parent (and its reflection parent), so the Korean letters above are the ones shown.
    layout = swap_names(archive.get('arc/blyt/banner.brlyt'),
                        [('N_logoJ_00', 'N_logoE_00'), ('N_logoJS_00', 'N_logoES_00')], 16)
    archive = ChannelArchive(archive.replace('arc/blyt/banner.brlyt', layout))
    for name in [p for p in archive.files if p.endswith('.brlan')]:
        archive = ChannelArchive(archive.replace(name, swap_names(archive.get(name), [('N_logoJS_00', 'N_logoES_00')], 20)))
    return archive, record


def icon_logo_tracked(original, style):
    """Revision 15+: the 120x32 icon wordmark from the same five syllables as the title, one size and
    baseline, placed by INK gaps (icon_gap inside a word, icon_space at the word break, texture px),
    optionally widened (icon_x_scale; the menu shows this texture ~1.1-1.3x taller than drawn). The
    title's bottom ink row is 14 and its unfaded mirror starts at row 17 (US axis between 15 and 16)."""
    load_library()
    from PIL import Image, ImageDraw
    w, h = original.size
    rows = style['icon_rows']
    top_row = 15 - rows
    if top_row < 1:
        raise ValueError('icon wordmark too tall')
    bold = int(round(style.get('icon_bold_px', 0) * SS))
    x_scale = style.get('icon_x_scale', 1.0)
    text = [t[0] for t in TITLE]
    target = rows * SS
    size = target
    for _ in range(8):
        font = _font(size)
        boxes = [font.getbbox(c, stroke_width=bold) for c in text]
        ink_h = max(b[3] for b in boxes) - min(b[1] for b in boxes)
        size = max(8, int(round(size * target / ink_h)))
    font = _font(size)
    boxes = {c: font.getbbox(c, stroke_width=bold) for c in text}
    top = min(b[1] for b in boxes.values())
    cells = []
    for c in text:
        cw = 3 * target
        im = Image.new('L', (cw, h * SS))
        b = boxes[c]
        ImageDraw.Draw(im).text(((cw - (b[2] - b[0])) / 2 - b[0], top_row * SS - top), c, font=font, fill=255,
                                stroke_width=bold, stroke_fill=255)
        if x_scale != 1.0:
            im = im.resize((int(round(cw * x_scale)), h * SS), Image.Resampling.LANCZOS)
        ink = im.getbbox()
        cells.append(im.crop((ink[0], 0, ink[2], h * SS)))
    gaps = [style['icon_space'] if i == WORD_BREAK - 1 else style['icon_gap'] for i in range(len(cells) - 1)]
    total = sum(c.size[0] for c in cells) + sum(g * SS for g in gaps)
    if total > (w - 6) * SS:
        raise ValueError('icon wordmark too wide')
    canvas = Image.new('L', (w * SS, h * SS))
    x = (w * SS - total) / 2
    for i, cell in enumerate(cells):
        canvas.paste(cell, (int(round(x)), 0))
        x += cell.size[0] + (gaps[i] * SS if i < len(gaps) else 0)
    small = canvas.resize((w, h), Image.Resampling.LANCZOS)
    out = Image.new('L', (w, h))
    title = small.crop((0, top_row, w, 15))
    out.paste(title, (0, top_row))
    out.paste(title.transpose(Image.Transpose.FLIP_TOP_BOTTOM), (0, 31 - 14))
    return Image.merge('RGBA', (out, out, out, out))


def icon_logo(original, revision=9):
    """120x32 icon wordmark: title ink in rows 3..13 and its unfaded mirror in rows 18..28,
    exactly like the US bitmap (the layout fades the reflection)."""
    if 'icon_gap' in STYLES[revision]:
        return icon_logo_tracked(original, STYLES[revision])
    load_library()
    from PIL import Image, ImageDraw
    w, h = original.size
    text = '닌텐도 채널'
    rows = STYLES[revision].get('icon_rows', 11)   # US bitmap: title ink rows 3..13 (11)
    bold = int(round(STYLES[revision].get('icon_bold_px', 0) * SS))
    target_h = rows * SS
    size = target_h
    for _ in range(6):
        font = _font(size)
        b = font.getbbox(text)
        size = int(round(size * target_h / (b[3] - b[1])))
    font = _font(size)
    b = font.getbbox(text, stroke_width=bold)
    if b[2] - b[0] > (w - 6) * SS:
        raise ValueError('icon wordmark too wide')
    im = Image.new('L', (w * SS, h * SS))
    x = (w * SS - (b[2] - b[0])) / 2 - b[0]
    y = 3 * SS - b[1]
    ImageDraw.Draw(im).text((x, y), text, font=font, fill=255, stroke_width=bold, stroke_fill=255)
    small = im.resize((w, h), Image.Resampling.LANCZOS)
    canvas = Image.new('L', (w, h))
    title = small.crop((0, 3, w, 3 + rows))
    canvas.paste(title, (0, 3))
    # mirror about the US axis between rows 15 and 16 (rows 3..13 <-> 18..28 for 11 rows)
    canvas.paste(title.transpose(Image.Transpose.FLIP_TOP_BOTTOM), (0, 31 - (3 + rows - 1)))
    return Image.merge('RGBA', (canvas, canvas, canvas, canvas))


def icon_archive(before, revision=9):
    path = 'arc/blyt/icon.brlyt'
    sections = layout_sections(before.get(path))
    hits = 0
    for i, s in enumerate(sections):
        if s[:4] == b'grp1':
            name = s[8:24].split(b'\0')[0]
            if name == b'KOR':
                raise ValueError('icon already has a KOR group')
            if name == b'ENG':
                b = bytearray(s)
                b[8:24] = b'KOR'.ljust(16, b'\0')
                sections[i] = bytes(b)
                hits += 1
    if hits != 1:
        raise ValueError('US icon ENG group not found')
    archive = ChannelArchive(before.replace(path, rebuild_layout(before.get(path), sections)))
    record = dict(group='ENG->KOR')
    if STYLES[revision].get('icon_script_pane'):
        # Names are swapped in the layout (panes, their materials, group lists) and in every animation,
        # so each physical pane keeps its own texture, geometry and curves; only the name the channel
        # script looks up for SC_LANG_KOREAN now belongs to the US (Korean wordmark) pane.
        archive = ChannelArchive(archive.replace(path, swap_names(archive.get(path), ICON_SCRIPT_PANES, 16)))
        for anim in [p for p in archive.files if p.endswith('.brlan')]:
            archive = ChannelArchive(archive.replace(anim, swap_names(archive.get(anim), ICON_SCRIPT_PANES, 20)))
        record['script_panes'] = ['<->'.join(pair) for pair in ICON_SCRIPT_PANES]
    name = 'arc/timg/oh_proLogo_E_00.tpl'
    original = archive.get(name)
    image = tpl.decode(original, 0)
    if image.size != (120, 32):
        raise ValueError('US icon title dimensions differ')
    archive = ChannelArchive(archive.replace(name, tpl.encode(original, 0, icon_logo(image, revision))))
    record['logo'] = name
    return archive, record


def korean_menu_art(content, revision=9):
    """Content 0 (Wii Menu banner + icon) of the US channel -> Korean wordmark (revision 9/10)."""
    load_library()
    from libWiiPy.archive import decompress_lz77
    glyph_set = glyphs(revision)
    outer = ChannelArchive(content[0x640:])
    prefix = bytearray(content[:0x640])
    records = []
    for kind in ('banner', 'icon'):
        member = f'meta/{kind}.bin'
        wrapped = outer.get(member)
        if wrapped[:4] != b'IMD5' or hashlib.md5(wrapped[32:]).digest() != wrapped[16:32]:
            raise ValueError('Menu artwork integrity')
        before = ChannelArchive(decompress_lz77(wrapped[32:]))
        archive, record = banner_archive(before, glyph_set, revision) if kind == 'banner' else icon_archive(before, revision)
        icon_anims = ({p for p in before.files if p.endswith('.brlan')}
                      if STYLES[revision].get('icon_script_pane') else set())
        allowed = ({'arc/blyt/icon.brlyt', 'arc/timg/oh_proLogo_E_00.tpl'} | icon_anims if kind == 'icon' else
                   {'arc/blyt/banner.brlyt'} | {'arc/timg/' + t[3] for t in TITLE} |
                   {p for p in before.files if p.endswith('.brlan')})
        if set(archive.files) != set(before.files) or any(
                archive.get(p) != before.get(p) for p in before.files if p not in allowed):
            raise ValueError('Changes escaped the wordmark')
        raw = archive.compact()
        payload = b'LZ77' + compress_lz10(raw)
        if decompress_lz77(payload) != raw:
            raise ValueError('Menu artwork compression')
        outer = ChannelArchive(outer.replace(member, b'IMD5' + len(payload).to_bytes(4, 'big') + bytes(8)
                                             + hashlib.md5(payload).digest() + payload))
        struct.pack_into('>I', prefix, 0x40 + (0x50 if kind == 'banner' else 0x4c), len(raw))
        record.update(kind=kind, size=len(raw))
        records.append(record)
    prefix[0x630:0x640] = bytes(16)
    prefix[0x630:0x640] = hashlib.md5(prefix[0x40:0x640]).digest()
    return bytes(prefix) + outer.compact(), records


def korean_opening(content5, revision=9):
    """Content 5: the in-channel opening logo (layout/option.arc opening_00) in the same lettering."""
    glyph_set = glyphs(revision)
    archive = ChannelArchive(content5)
    member = 'layout/option.arc'
    inner = ChannelArchive(archive.get(member))
    before = inner
    inner, record = _apply_title(inner, 'arc/blyt/opening_00.brlyt', glyph_set, revision)
    allowed = {'arc/blyt/opening_00.brlyt'} | {'arc/timg/' + t[3] for t in TITLE}
    if any(inner.get(p) != before.get(p) for p in before.files if p not in allowed):
        raise ValueError('Opening changes escaped the wordmark')
    out = ChannelArchive(archive.replace(member, inner.compact())).compact()
    if len(out) > len(content5):
        raise ValueError('Nintendo content 5 capacity exceeded')
    return out + bytes(len(content5) - len(out)), record

"""Korean content-2 (Dtest/) resources for Food build revision >= 2.

1. HOME dialog messages. The channel hands Dtest/Home/home_nosave.csv to the
   HOME Button library. At 0x8001d7cc the library clamps SCGetLanguage()>=7 to
   0, so a Korean console (9) loads HomeButton3/LZ77_homeBtn.arc (the Korean
   archive in our builds) and CSV column 0 (Japanese). The Korean archive font
   holds only the Korean HOME glyphs, so Japanese text would draw blank. Every
   column is set to the CSV's own official Korean column 9 (glyph coverage
   checked against the Korean archive font). network_nosave.csv is used with
   the content-6 nwm_* archives (Japanese fonts, no Korean variant exists) and
   is left Japanese so text and font stay consistent.
2. Functional label textures from configs/food-textures-v1-ko.json, redrawn
   with the Korean 43K system font in the original GX format/size/offset.
"""
import json, re
from .channels import ChannelArchive, ROOT, sha256
from .tpl import decode

HOME_CSV = 'Dtest/Home/home_nosave.csv'
KOREAN_COLUMN = 9
COLUMNS = 10
TEXTURES = ROOT / 'configs/food-textures-v1-ko.json'


def _korean_home_font():
    from .channels import load_library
    from .channel_font import font_data
    from .home_menu import KOREAN_SHARED, SOURCES
    load_library(); from libWiiPy.archive import decompress_lz77
    arc = ChannelArchive(decompress_lz77(ChannelArchive(KOREAN_SHARED.read_bytes()).get(SOURCES['HomeButton3'])))
    fonts = [p for p in arc.files if p.endswith('.brfnt')]
    if len(fonts) != 1:
        raise ValueError('Unknown Korean HOME font')
    return set(font_data(arc.get(fonts[0]))[1])


def korean_home_csv(data):
    if data[:2] != b'\xfe\xff':
        raise ValueError('HOME CSV is not UTF-16BE with BOM')
    text = data[2:].decode('utf-16-be')
    cells = list(re.finditer(r'"([^"]*)"', text))
    if len(cells) % COLUMNS or len(cells) // COLUMNS != 4:
        raise ValueError('Expected 4 rows x 10 languages in the Food HOME CSV')
    korean = [cells[r * COLUMNS + KOREAN_COLUMN].group(1) for r in range(len(cells) // COLUMNS)]
    if not korean[2].startswith('Wii 메뉴로'):
        raise ValueError('Unexpected Korean HOME column')
    font = _korean_home_font()
    missing = sorted({ch for s in korean for ch in s if ord(ch) >= 32 and ord(ch) not in font})
    if missing:
        raise ValueError('Korean HOME text has glyphs missing from the Korean HOME font')
    for i in reversed(range(len(cells))):
        start, end = cells[i].span(1)
        text = text[:start] + korean[i // COLUMNS] + text[end:]
    after = re.findall(r'"([^"]*)"', text)
    if len(after) != len(cells) or any(after[i] != korean[i // COLUMNS] for i in range(len(after))):
        raise ValueError('HOME CSV rewrite failed')
    return b'\xfe\xff' + text.encode('utf-16-be'), dict(file=HOME_CSV, rows=len(korean), columns=COLUMNS,
        source_column=KOREAN_COLUMN, all_columns_korean=True, glyphs_missing=0,
        reason='HBM clamps language>=7 to column/archive 0 (0x8001d7cc)')


LAYOUTS = ROOT / 'configs/food-layout-v4-ko.json'
TEXTURES_V4 = ROOT / 'configs/food-textures-v4-ko.json'
LAYOUTS_V6 = ROOT / 'configs/food-layout-v6-ko.json'      # revision >= 6: v4 + text-fit fixes + loading labels
TEXTURES_V6 = ROOT / 'configs/food-textures-v6-ko.json'   # revision >= 6: style-preserving redraws (food_texture_v6)
LAYOUTS_V7 = ROOT / 'configs/food-layout-v7-ko.json'      # revision >= 7: v6 + lead review wording (100만 엔, operator name)
TEXTURES_V7 = ROOT / 'configs/food-textures-v7-ko.json'   # revision >= 7: v6 + roulette stop button fix
LAYOUTS_V10 = ROOT / 'configs/food-layout-v10-ko.json'    # revision >= 10 (rc6): v7 + 02a shop-request labels (delta)
TEXTURES_V10 = ROOT / 'configs/food-textures-v10-ko.json' # revision >= 10 (rc6): v7 + order-flow obis/buttons (delta)
LAYOUTS_V11 = ROOT / 'configs/food-layout-v11-ko.json'    # revision >= 11 (rc7): v7+v10 + order-flow BRLYT static labels
TEXTURES_V11 = ROOT / 'configs/food-textures-v11-ko.json' # revision >= 11 (rc7): v7+v10 + missed buttons + category refit
LAYOUTS_V12 = ROOT / 'configs/food-layout-v12-ko.json'    # revision >= 12 (rc7b): + order-record/order-list labels, hidden readings
TEXTURES_V12 = ROOT / 'configs/food-textures-v12-ko.json' # revision >= 12 (rc7b): + every remaining stock baked-Japanese texture
TEXTURES_V13 = ROOT / 'configs/food-textures-v13-ko.json' # revision >= 13 (rc7c): category photo tiles + 단골 redrawn from stock (override)


def _merge_cfg(base, delta, override=False):
    """Deep-merge {arc: {name: spec}} configs. By default delta only adds names
    base lacks (overlap is a mistake); with override=True delta replaces base
    entries (the rc7 texture layer intentionally refines earlier category tiles)."""
    out = {arc: dict(specs) for arc, specs in base.items()}
    for arc, specs in delta.items():
        merged = dict(out.get(arc, {}))
        for name, spec in specs.items():
            if name in merged and not override:
                raise ValueError('Food config overlaps earlier wave: %s / %s' % (arc, name))
            merged[name] = spec
        out[arc] = merged
    return out


def _merge_layouts(base, delta):
    """Merge {arc: {brlyt: [pane,...]}} at pane granularity: a brlyt an earlier
    wave already touched keeps its panes and the delta's new panes are appended
    (a duplicate pane name would double-apply, so it is refused)."""
    out = {arc: {b: list(p) for b, p in brs.items()} for arc, brs in base.items()}
    for arc, brs in delta.items():
        dst = out.setdefault(arc, {})
        for brlyt, panes in brs.items():
            cur = dst.setdefault(brlyt, []); seen = {p['pane'] for p in cur}
            for p in panes:
                if p['pane'] in seen:
                    raise ValueError('Food layout pane overlaps earlier wave: %s / %s' % (brlyt, p['pane']))
                cur.append(p); seen.add(p['pane'])
    return out


def _wbf1_glyphs():
    from .channel_korean_font import korean_shared_fonts
    from .channel_font import font_data
    rfna = ChannelArchive(korean_shared_fonts()[0]).get('wbf1.brfna')
    return set(font_data(b'RFNT' + rfna[4:])[1])


def _check_glyphs(ko, glyphs, where):
    missing = sorted({c for c in ko if c != '\n' and ord(c) not in glyphs})
    if missing:
        raise ValueError('Korean glyphs missing from wbf1 (%s): %s' % (where, ''.join(missing)))


def _replace_textbox_in_layout(payload, pane, ja, ko, fw_scale=None, keep_buffer=False):
    import struct
    from .channels import layout_sections, textbox, replace_textbox, rebuild_layout
    secs = layout_sections(payload); hit = False
    for i, sec in enumerate(secs):
        tb = textbox(sec)
        if tb and tb[0] == pane:
            if tb[1].rstrip('\0') != ja:
                raise ValueError('Textbox %s text differs: %r' % (pane, tb[1][:20]))
            new = replace_textbox(sec, ko)
            if fw_scale is not None:            # squeeze the horizontal font width in place (nw4r fontSize.width)
                buf = bytearray(new)
                struct.pack_into('>f', buf, 0x64, struct.unpack_from('>f', buf, 0x64)[0] * fw_scale)
                new = bytes(buf)
            if keep_buffer:                     # rev >= 12: never shrink the stock textBufBytes (runtime SetString room)
                buf = bytearray(new)
                struct.pack_into('>H', buf, 76, max(struct.unpack_from('>H', sec, 76)[0], struct.unpack_from('>H', buf, 76)[0]))
                new = bytes(buf)
            secs[i] = new; hit = True
            break
    if not hit:
        raise ValueError('Textbox pane not found: ' + pane)
    return rebuild_layout(payload, secs)


def _redraw_v12(raw, spec, plate=None):
    """Texture redraw for the rev >= 12 layer: v6 text/button styles or the v12 'retext' mode
    (`plate` = the stock photo-free sibling for the rev >= 13 plate option)."""
    if spec['mode'] == 'retext':
        from .food_texture_v12 import retext
        return retext(raw, spec, plate=plate)
    if spec['mode'] in ('text', 'button'):
        from .food_texture_v6 import restyle
        return restyle(raw, spec)
    raise ValueError('Unknown v12 texture mode: ' + spec['mode'])


def korean_content2(content, revision=2):
    from .food_texture import redraw_label, redraw_header, redraw_tile, korean_font_renderer
    outer = ChannelArchive(content); record = dict(home_csv=None, textures={})
    csv, record['home_csv'] = korean_home_csv(outer.get(HOME_CSV))
    outer = ChannelArchive(outer.replace(HOME_CSV, csv))
    cfg = json.loads(TEXTURES.read_text(encoding='utf-8'))
    renderer = korean_font_renderer()
    touched = {HOME_CSV}
    for arc, labels in cfg['labels'].items():
        name = 'Dtest/' + arc; inner = ChannelArchive(outer.get(name)); done = []
        for tpl, spec in labels.items():
            raw = inner.get(tpl)
            if raw[:4] != bytes.fromhex('0020af30'):
                raise ValueError('Expected a raw TPL: ' + tpl)
            new, meta = redraw_label(raw, spec['ko'], renderer)
            decode(new, 0)
            inner = ChannelArchive(inner.replace(tpl, new)); done.append(dict(tpl=tpl, ko=spec['ko'], **meta))
        before = ChannelArchive(outer.get(name)); packed = inner.compact()
        if set(ChannelArchive(packed).files) != set(before.files):
            raise ValueError('Texture archive topology changed: ' + name)
        outer = ChannelArchive(outer.replace(name, packed)); record['textures'][arc] = done
        touched.add(name)
    record['labels'] = sum(len(v) for v in record['textures'].values())
    record['texture_config_sha256'] = sha256(TEXTURES.read_bytes())
    if revision >= 4:
        glyphs = _wbf1_glyphs()
        tag = ('v13' if revision >= 13 else 'v12' if revision >= 12 else 'v11' if revision >= 11 else 'v10' if revision >= 10
               else 'v7' if revision >= 7 else 'v6' if revision >= 6 else 'v4')
        hidden = {}
        if revision >= 10:
            tex = _merge_cfg(json.loads(TEXTURES_V7.read_text(encoding='utf-8'))['textures'],
                             json.loads(TEXTURES_V10.read_text(encoding='utf-8'))['textures'])
            lay = _merge_cfg(json.loads(LAYOUTS_V7.read_text(encoding='utf-8'))['layouts'],
                             json.loads(LAYOUTS_V10.read_text(encoding='utf-8'))['layouts'])
            if revision >= 11:
                tex = _merge_cfg(tex, json.loads(TEXTURES_V11.read_text(encoding='utf-8'))['textures'], override=True)
                lay = _merge_layouts(lay, json.loads(LAYOUTS_V11.read_text(encoding='utf-8'))['layouts'])
            if revision >= 12:                    # rc7b: additions only (an overlap with v7/v10/v11 is refused)
                tex = _merge_cfg(tex, json.loads(TEXTURES_V12.read_text(encoding='utf-8'))['textures'])
                v12 = json.loads(LAYOUTS_V12.read_text(encoding='utf-8'))
                lay = _merge_layouts(lay, v12['layouts']); hidden = v12.get('hidden', {})
            if revision >= 13:                    # rc7c: the category tiles again, now from stock (refines v7/v11/v12 entries)
                tex = _merge_cfg(tex, json.loads(TEXTURES_V13.read_text(encoding='utf-8'))['textures'], override=True)
            tex_cfg = lay_cfg = None
        else:
            tex_cfg, lay_cfg = {'v7': (TEXTURES_V7, LAYOUTS_V7), 'v6': (TEXTURES_V6, LAYOUTS_V6), 'v4': (TEXTURES_V4, LAYOUTS)}[tag]
            tex = json.loads(tex_cfg.read_text(encoding='utf-8'))['textures']
            lay = json.loads(lay_cfg.read_text(encoding='utf-8'))['layouts']
        record[tag + '_textures'] = {}; record[tag + '_layouts'] = {}
        arcs = sorted(set(tex) | set(lay) | set(hidden))
        for arc in arcs:
            name = 'Dtest/' + arc; inner = ChannelArchive(outer.get(name)); before = ChannelArchive(outer.get(name))
            tdone = []
            for tpl, spec in tex.get(arc, {}).items():
                if spec.get('ko'):
                    _check_glyphs(spec['ko'], glyphs, tpl)
                raw = inner.get(tpl)
                if raw[:4] != bytes.fromhex('0020af30'):
                    raise ValueError('Expected a raw TPL: ' + tpl)
                if spec['mode'] == 'blank':       # clear an empty-slot placeholder (rc7: 02_btn_menu_NOdata)
                    from .food_menu_art import decode_any, encode_any
                    from PIL import Image
                    img = decode_any(raw, 0)
                    new = encode_any(raw, 0, Image.new('RGBA', img.size, (0, 0, 0, 0))); meta = dict(blank=True)
                elif spec['mode'] == 'retext':    # rc7b: lettering inside coloured art (kwce.food_texture_v12)
                    plate = None
                    if spec.get('plate'):         # rc7c (rev >= 13): the stock photo-free sibling is the exact plate
                        stock_inner = ChannelArchive(ChannelArchive(content).get(name))
                        if raw != stock_inner.get(tpl):
                            raise ValueError('Plate retext expects the stock texture: ' + tpl)
                        plate = stock_inner.get(spec['plate']['from'])
                    new, meta = _redraw_v12(raw, spec, plate)
                elif spec['mode'] in ('text', 'button'):
                    from .food_texture_v6 import restyle
                    new, meta = restyle(raw, spec)
                else:
                    fn = {'label': redraw_label, 'header': redraw_header, 'tile': redraw_tile}[spec['mode']]
                    kw = {}
                    if spec['mode'] == 'tile':
                        if 'x0' in spec: kw['x0'] = spec['x0']
                        if 'size' in spec: kw['size'] = spec['size']
                    new, meta = fn(raw, spec['ko'], renderer, **kw)
                    decode(new, 0)
                inner = ChannelArchive(inner.replace(tpl, new)); tdone.append(dict(tpl=tpl, ko=spec.get('ko'), mode=spec['mode'], **meta))
            ldone = []
            arc_hidden = hidden.get(arc, {})
            for brlyt in list(lay.get(arc, {})) + [b for b in arc_hidden if b not in lay.get(arc, {})]:
                panes = lay.get(arc, {}).get(brlyt, [])
                raw = inner.get(brlyt)
                if raw[:4] != b'RLYT':
                    raise ValueError('Expected a raw RLYT (uncompressed): ' + brlyt)
                for pane in panes:
                    _check_glyphs(pane['ko'], glyphs, brlyt + '/' + pane['pane'])
                    raw = _replace_textbox_in_layout(raw, pane['pane'], pane['ja'], pane['ko'], pane.get('fw_scale'),
                                                     keep_buffer=revision >= 12)
                done = dict(brlyt=brlyt, panes=len(panes))
                if arc_hidden.get(brlyt):         # rev >= 12: reading lines the Korean SPD fills with the name itself
                    from .food_address_card import edit_layout
                    raw = edit_layout(raw, hide=arc_hidden[brlyt]); done['hidden'] = list(arc_hidden[brlyt])
                inner = ChannelArchive(inner.replace(brlyt, raw)); ldone.append(done)
            packed = inner.compact()
            if set(ChannelArchive(packed).files) != set(before.files):
                raise ValueError('Archive topology changed: ' + name)
            outer = ChannelArchive(outer.replace(name, packed)); touched.add(name)
            if tdone: record[tag + '_textures'][arc] = tdone
            if ldone: record[tag + '_layouts'][arc] = ldone
        if revision >= 10:
            record['v10_texture_config_sha256'] = sha256(TEXTURES_V10.read_bytes())
            record['v10_layout_config_sha256'] = sha256(LAYOUTS_V10.read_bytes())
            record['v7_texture_config_sha256'] = sha256(TEXTURES_V7.read_bytes())
            record['v7_layout_config_sha256'] = sha256(LAYOUTS_V7.read_bytes())
            if revision >= 11:
                record['v11_texture_config_sha256'] = sha256(TEXTURES_V11.read_bytes())
                record['v11_layout_config_sha256'] = sha256(LAYOUTS_V11.read_bytes())
            if revision >= 12:
                record['v12_texture_config_sha256'] = sha256(TEXTURES_V12.read_bytes())
                record['v12_layout_config_sha256'] = sha256(LAYOUTS_V12.read_bytes())
            if revision >= 13:
                record['v13_texture_config_sha256'] = sha256(TEXTURES_V13.read_bytes())
        else:
            record[tag + '_texture_config_sha256'] = sha256(tex_cfg.read_bytes())
            record[tag + '_layout_config_sha256'] = sha256(lay_cfg.read_bytes())
    if revision >= 8:
        from .food_save_banner import korean_save_banner, BANNER as SAVE_BANNER
        newc2, record['save_banner'] = korean_save_banner(outer.compact())
        outer = ChannelArchive(newc2); touched.add(SAVE_BANNER)
    if revision >= 9:
        # rc3: five postal boxes, evenly spaced digits, reading lines hidden (kwce.food_address_card)
        from .food_address_card import korean_address_card, TITLE_ARC
        newc2, record['address_card'] = korean_address_card(outer.compact())
        outer = ChannelArchive(newc2); touched.add(TITLE_ARC)
    result = outer.compact()
    original = ChannelArchive(content); final = ChannelArchive(result)
    if set(final.files) != set(original.files) or any(final.get(n) != original.get(n) for n in original.files if n not in touched):
        raise ValueError('Unrelated content-2 resource changed')
    return result, record

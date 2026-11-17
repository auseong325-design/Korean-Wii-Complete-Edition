"""Korean local text resources of the Kirby TV Channel (content 2 and 5).

Everything here derives a NEW resource from an original one; originals are
only read. Source strings are compared with the translation table so a
different source revision is refused instead of silently mistranslated.
"""
import re
import struct
import xml.etree.ElementTree as ET
from .channels import ChannelArchive, layout_sections, textbox, replace_textbox, rebuild_layout
from .channel_font import font_data, extend_font
from .wiiroom_formats import decompress_lz11, compress_lz11_optimal
from . import kirbytv_u8

KO_DIR = 'KR/KO'


# ------------------------------------------------------------------ dialog

def _font_metrics(font):
    blocks, mapping, widths = font_data(font)
    finf = blocks[b'FINF'][1]
    default = finf[12:15]
    width = finf[29]
    return mapping, widths, default, width


def _line_width(text, size_w, mapping, widths, default, font_width):
    total = 0
    for ch in text:
        glyph = mapping.get(ord(ch))
        advance = (widths.get(glyph, default) if glyph is not None else default)[2]
        total += advance
    return total * size_w / font_width


def fit_textbox(section, text, metrics, container=None, minimum=0.7):
    """Shrink only the horizontal font size when a line would overflow.

    `container` is the width of an enclosing button picture: nw4r does not
    clip text, so a caption may use the button graphic's width.
    """
    mapping, widths, default, font_width = metrics
    box_w = struct.unpack_from('>f', section, 0x44)[0]
    size_w, size_h = struct.unpack_from('>ff', section, 100)
    widest = max(_line_width(line.replace('[@X]', '00').replace('[@T]', ''), size_w, mapping, widths, default, font_width)
                 for line in text.split('\n'))
    limit = max(box_w, container or 0) - 2
    if widest <= limit:
        return section, 1.0
    scale = limit / widest
    if scale < minimum:
        raise ValueError(f'Korean text needs {scale:.2f} horizontal scale: {text!r}')
    out = bytearray(section)
    struct.pack_into('>f', out, 100, size_w * scale)
    return bytes(out), round(scale, 3)


HANGUL_PX = 26
HANGUL_ADVANCE = 27
HANGUL_WEIGHT = 700


def korean_runtime_dialog(runtime, table, glyph_text, ttf):
    from .kirbytv_font import extend_font_sized
    archive = ChannelArchive(runtime)
    font_path = 'arc/font/run.brfnt'
    font = archive.get(font_path)
    chars = set(glyph_text)
    for _, target in table.values():
        chars.update(target)
    extended, font_record = extend_font_sized(font, ''.join(sorted(chars)), ttf, HANGUL_PX, HANGUL_ADVANCE, HANGUL_WEIGHT)
    metrics = _font_metrics(extended)
    replace = {font_path: extended}
    done = {}
    scales = {}
    for path in archive.files:
        if not path.endswith('.brlyt'):
            continue
        layout = path.rsplit('/', 1)[-1][:-6]
        sections = layout_sections(archive.get(path))
        changed = False
        stack, last = [], None
        for i, section in enumerate(sections):
            kind = section[:4]
            if kind == b'pas1':
                stack.append(last)
                continue
            if kind == b'pae1':
                stack.pop()
                continue
            if kind in (b'pan1', b'pic1', b'txt1', b'wnd1', b'bnd1'):
                last = (kind, struct.unpack_from('>f', section, 0x44)[0])
            box = textbox(section)
            if not box or not box[1].strip():
                continue
            key = f'{layout}/{box[0]}'
            if key not in table:
                raise ValueError('Untranslated dialog text box ' + key)
            source, target = table[key]
            if box[1] != source:
                raise ValueError('Dialog source differs: ' + key)
            if re.findall(r'\[@[A-Z]\]', source) != re.findall(r'\[@[A-Z]\]', target):
                raise ValueError('Dialog tag changed: ' + key)
            parent = stack[-1] if stack else None
            container = parent[1] - 12 if parent and parent[0] == b'pic1' else None
            fitted, scale = fit_textbox(replace_textbox(section, target), target, metrics, container)
            sections[i] = fitted
            changed = True
            done[key] = target
            if scale != 1.0:
                scales[key] = scale
        if changed:
            replace[path] = rebuild_layout(archive.get(path), sections)
    if set(done) != set(table):
        raise ValueError('Dialog table has unused entries: ' + ', '.join(sorted(set(table) - set(done))))
    missing = {c for c in chars if ord(c) >= 32 and ord(c) not in metrics[0]}
    if missing:
        raise ValueError('Dialog font still lacks glyphs')
    result = kirbytv_u8.edit(runtime, replace=replace)
    return result, dict(text_boxes=len(done), horizontally_scaled=scales, font=dict(file=font_path, **font_record))


def korean_dialog_bin(dialog_bin, table, glyph_text, ttf):
    raw = decompress_lz11(dialog_bin)
    outer = ChannelArchive(raw)
    if set(outer.files) != {'cursor.arc', 'runtime_dialog.arc'}:
        raise ValueError('Unexpected dialog.bin contents')
    runtime, record = korean_runtime_dialog(outer.get('runtime_dialog.arc'), table, glyph_text, ttf)
    rebuilt = kirbytv_u8.edit(raw, replace={'runtime_dialog.arc': runtime})
    packed = compress_lz11_optimal(rebuilt)
    record.update(raw_size=len(rebuilt), compressed_size=len(packed), compression='LZ11 (same as source)')
    return packed, record


# --------------------------------------------------------------------- BMG

def _bmg_parse(data):
    if data[:8] != b'MESGbmg1':
        raise ValueError('Not a BMG')
    count = struct.unpack_from('>I', data, 12)[0]
    pos = 32
    sections = []
    for _ in range(count):
        size = struct.unpack_from('>I', data, pos + 4)[0]
        sections.append(data[pos:pos + size])
        pos += size
    return sections


def bmg_messages(data):
    sections = _bmg_parse(data)
    inf = next(s for s in sections if s[:4] == b'INF1')
    dat = next(s for s in sections if s[:4] == b'DAT1')
    count, stride = struct.unpack_from('>HH', inf, 8)
    rows = []
    for i in range(count):
        offset = struct.unpack_from('>I', inf, 16 + i * stride)[0]
        end = dat.index(b'\0', 8 + offset)
        rows.append(dat[8 + offset:end].decode('utf-8'))
    return rows


def korean_bmg(data, table):
    """Rebuild a UTF-8 BMG (encoding 4) with every message translated."""
    if data[16] != 4:
        raise ValueError('Expected UTF-8 BMG')
    sections = _bmg_parse(data)
    if [s[:4] for s in sections] != [b'INF1', b'DAT1']:
        raise ValueError('Unexpected BMG sections')
    inf, dat = sections
    count, stride = struct.unpack_from('>HH', inf, 8)
    if stride != 4:
        raise ValueError('BMG attributes not supported')
    rows = bmg_messages(data)
    body = bytearray(b'\0')
    offsets = {}
    new_inf = bytearray(inf[:16])
    for row in rows:
        if row not in table:
            raise ValueError('Untranslated BMG message')
        target = table[row]
        if target not in offsets:
            offsets[target] = len(body)
            body += target.encode('utf-8') + b'\0'
        new_inf += struct.pack('>I', offsets[target])
    new_inf += bytes(-len(new_inf) % 32)
    struct.pack_into('>I', new_inf, 4, len(new_inf))
    new_dat = bytearray(b'DAT1' + bytes(4)) + body
    new_dat += bytes(-len(new_dat) % 32)
    struct.pack_into('>I', new_dat, 4, len(new_dat))
    out = bytearray(data[:32]) + new_inf + new_dat
    struct.pack_into('>I', out, 8, len(out))
    result = bytes(out)
    if bmg_messages(result) != [table[r] for r in rows]:
        raise ValueError('BMG rebuild verification failed')
    return result, dict(messages=len(rows), distinct=len(offsets), encoding='UTF-8')


# --------------------------------------------------------------- error XML

def korean_error_xml(data, table):
    text = data.decode('utf-8-sig')
    root = ET.fromstring(text.encode('utf-8'))
    ids = {u.attrib['id'] for u in root.iter('trans_unit')}
    blocks = []
    for base, (source, target, kind) in table.items():
        node = next((u for u in root.iter('trans_unit') if u.attrib['id'] == base + '_en'), None)
        if node is None or node.find(f'{kind}/target').text != source:
            raise ValueError('Error XML source differs: ' + base)
        if base + '_ko' in ids:
            raise ValueError('Korean error text already present: ' + base)
        if ']]>' in target:
            raise ValueError('CDATA terminator in translation')
        kind_attr = 'btn' if kind == 'label' else 'dialog'
        blocks.append(f'\t<trans_unit id="{base}_ko" type="{kind_attr}">\r\n      <{kind} size="">\r\n'
                      f'        <target xml:lang="ko-KR"><![CDATA[{target}]]></target>\r\n      </{kind}>\r\n    </trans_unit>\r\n\t\r\n')
    anchor = '  </locale>\r\n'
    if text.count(anchor) != 1:
        raise ValueError('Error XML locale end differs')
    result = text.replace(anchor, ''.join(blocks) + anchor)
    raw = (b'\xef\xbb\xbf' if data.startswith(b'\xef\xbb\xbf') else b'') + result.encode('utf-8')
    check = ET.fromstring(result.encode('utf-8'))
    for base, (_, target, kind) in table.items():
        node = next(u for u in check.iter('trans_unit') if u.attrib['id'] == base + '_ko')
        if node.find(f'{kind}/target').text != target:
            raise ValueError('Error XML verification failed')
    return raw, dict(added_units=len(blocks), suffix='_ko')


# ----------------------------------------------------------- config files

def _crlf(lines):
    return ('\r\n'.join(lines) + '\r\n').encode('ascii')


def korean_configs():
    """config/KR/KO/*.pcf modelled on config/US/EN (NTSC frame settings)."""
    base = f'config/{KO_DIR}'
    common = ['###############################################################################',
              '# KWCE Korean resource set (language 9). Generated; see docs/channels/kirbytv.md',
              '###############################################################################']
    files = {
        f'{base}/config.koKR.pcf': _crlf(common + [
            'include\t\t\t\t\t\t\tconfig/config.common.pcf',
            'include\t\t\t\t\t\t\tconfig/US/config.region.pcf',
            'native_code_page\t\t\t\tkorean_uhc',
            'keyboard_country_code\t\t\tunited_states',
            'keyboard_keymap_file\t\t\tconfig/US/keymap.ini',
            f'dialog_archive\t\t\t\t\tlayout/{KO_DIR}/dialog.bin',
            f'banner_file\t\t\t\t\t\tbanner/{KO_DIR}/banner.ini',
            f'hbm_manual_jpeg_file\t\t\thbm/{KO_DIR}/manual.jpg']),
        f'{base}/config.ntsc.pcf': _crlf(common + [
            f'include\t\t\t\t\t\t\t{base}/config.koKR.pcf',
            'frame_buffer_size\t\t\t\t640 480',
            'ortho_rect\t\t\t\t\t\t-320 +240 +320 -240\t# left top right bottom',
            'window_rect\t\t\t\t\t\t-320 +240 +320 -240\t# left top right bottom',
            'display_rect\t\t\t\t\t0 0 640 480\t\t\t# xmin ymin xmax ymax',
            'efb_size\t\t\t\t\t\t640 456', 'xfb_size\t\t\t\t\t\t640 456',
            'vi_origin\t\t\t\t\t\t 24  12', 'vi_size\t\t\t\t\t\t\t672 456']),
        f'{base}/config.ntsc.wide.pcf': _crlf(common + [
            f'include\t\t\t\t\t\t\t{base}/config.koKR.pcf',
            'frame_buffer_size\t\t\t\t854 480',
            'ortho_rect\t\t\t\t\t\t-427 +240 +427 -240\t# xmin ymin xmax ymax',
            'window_rect\t\t\t\t\t\t-427 +240 +427 -240\t# xmin ymin xmax ymax',
            'display_rect\t\t\t\t\t0 0 854 480 # xmin ymin xmax ymax',
            'efb_size\t\t\t\t\t\t640 456', 'xfb_size\t\t\t\t\t\t640 456',
            'vi_origin\t\t\t\t\t\t 22  12', 'vi_size\t\t\t\t\t\t\t680 456']),
        f'{base}/config.prog.ntsc.pcf': _crlf(common + [f'include\t\t\t\t\t\t\t{base}/config.ntsc.pcf']),
        f'{base}/config.prog.ntsc.wide.pcf': _crlf(common + [f'include\t\t\t\t\t\t\t{base}/config.ntsc.wide.pcf']),
    }
    return files


def _url(text):
    return ''.join(c if c.isascii() and (c.isalnum() or c in '-_.~') else ''.join(f'%{b:02X}' for b in c.encode('utf-8')) for c in text)


def korean_banner_ini(original, name):
    text = original.decode('latin-1')
    lines = text.split('\r\n')
    out = []
    for line in lines:
        if line.startswith('title_text'):
            line = 'title_text\t\t' + _url(name) + '\t# UTF-8/URL Encoded'
        elif line.startswith('banner_tpl'):
            line = f'banner_tpl\t\tbanner/{KO_DIR}/banner.tpl'
        elif line.startswith('icon_tpl'):
            line = f'icon_tpl\t\tbanner/{KO_DIR}/icons.tpl'
        elif line.startswith('# EU_EN banner'):
            line = '# KR_KO banner setting file (KWCE)'
        out.append(line)
    result = '\r\n'.join(out).encode('latin-1')
    if b'title_text\t\t' + _url(name).encode() not in result:
        raise ValueError('banner.ini title not replaced')
    return result


# ------------------------------------------------------------------- HOME

def network_csv_korean(data, source, target):
    """Extend the 7-column network.csv to the 10 HOME message columns."""
    if data[:2] != b'\xfe\xff':
        raise ValueError('Expected UTF-16BE CSV')
    text = data[2:].decode('utf-16-be')
    cells = re.findall(r'"([^"]*)"', text)
    if len(cells) != 7 or cells[1] != source or text != '\t'.join(f'"{c}"' for c in cells) + '\r\n':
        raise ValueError('network.csv differs from the reviewed source')
    if '"' in target:
        raise ValueError('Quote in HOME message')
    # Columns: JP EN DE FR ES IT NL SC TC KO; SC/TC keep English like home.csv's TC.
    row = cells + [cells[1], cells[1], target]
    out = b'\xfe\xff' + ('\t'.join(f'"{c}"' for c in row) + '\r\n').encode('utf-16-be')
    return out, dict(columns_before=7, columns_after=10, korean_column=9)

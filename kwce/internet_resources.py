"""Korean resources for the USA Internet Channel (contents 0, 2, 3, 5, 6).

All inputs are the pinned USA v1024 contents; console fonts and the Korean
HOME Menu come from the user's own local NAND extract and stay in ignored
build outputs. Every function refuses an unexpected source instead of
guessing, and returns a small record for the build manifest.
"""
import hashlib
import io
import re
import struct

from .channels import ChannelArchive, compress_lz10, layout_sections, load_library, rebuild_layout, textbox
from . import internet_manual

FORMAT_TOKEN = re.compile(r'%(?:\d+|0?\d*[sdui])|\\n')
LNG_ENTRY = re.compile(r'^(-?\d+)="(.*)"$')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- language file
def korean_lng(english, cfg, keep_english=None):
    """keep_english: {index: expected English text} entries written unchanged (v4 keyboard hints)."""
    if sha256(english) != cfg['source_sha256']:
        raise ValueError('english.lng differs from the pinned source')
    keep_english = {int(k): v for k, v in (keep_english or {}).items()}
    lines = english.decode('utf-8').split('\n')
    out, index, kept = [], 0, 0
    tr = cfg['translations']
    for line in lines:
        m = LNG_ENTRY.match(line)
        if m:
            en, ko = m.group(2), tr[str(index)]
            if index in keep_english:
                if en != keep_english[index]:
                    raise ValueError(f'lng entry {index} is {en!r}, expected {keep_english[index]!r}')
                ko = en
            if sorted(FORMAT_TOKEN.findall(en)) != sorted(FORMAT_TOKEN.findall(ko)):
                raise ValueError(f'lng entry {index}: format tokens differ')
            if any(c in ko for c in '\r\n\t') or ko.startswith(' ') != en.startswith(' ') or ko.endswith(' ') != en.endswith(' '):
                raise ValueError(f'lng entry {index}: layout characters differ')
            kept += ko == en
            out.append(f'{m.group(1)}="{ko}"')
            index += 1
        elif line.startswith('Language='):
            out.append(f'Language="{cfg["info"]["Language"]}"')
        elif line.startswith('LanguageName='):
            out.append(f'LanguageName="{cfg["info"]["LanguageName"]}"')
        else:
            out.append(line)
    if index != cfg['source_entries'] or len(tr) != index:
        raise ValueError('lng entry coverage differs')
    data = '\n'.join(out).encode('utf-8')
    return data, dict(entries=index, translated=index - kept, kept_identical=kept, sha256=sha256(data),
                      **({'kept_english_entries': sorted(keep_english)} if keep_english else {}))


def full_image_labels(archive, specs):
    """Replace whole thumbnails with a plain tile and a label (local test favorites only)."""
    load_library()
    from PIL import Image
    records = {}
    for name, spec in specs.items():
        data = archive.get(name)
        w, h = Image.open(io.BytesIO(data)).size
        new, size = relabel(data, dict(spec, box=[0, 0, w, h]))
        archive = ChannelArchive(archive.replace(name, new))
        records[name] = dict(text=spec['text'], size=[w, h], font_px=size)
    return archive, records


def characters(text):
    return {c for c in text if ord(c) >= 0x20}


# ---------------------------------------------------------------- HTML pages
def _ncr(text):
    return ''.join(c if ord(c) < 128 else f'&#{ord(c)};' for c in text)


def localize_pages(archive, pages, *, ncr_undeclared=False):
    """pages: {file: {english run template: korean}} for the small UI pages.

    With ncr_undeclared, pages that declare no charset get the Korean text as
    numeric character references, so the bytes stay ASCII and decode the same
    under any fallback encoding.
    """
    records = {}
    for name, mapping in pages.items():
        html = archive.get(name).decode('utf-8')
        undeclared = 'charset' not in html.lower()
        if ncr_undeclared and undeclared:
            mapping = {k: _ncr(v) for k, v in mapping.items()}
        used = set()
        new = internet_manual.localize_html(html, mapping, used)
        if used != set(mapping):
            raise ValueError(f'{name}: unmatched page text {sorted(set(mapping) - used)}')
        archive = ChannelArchive(archive.replace(name, new.encode('utf-8')))
        records[name] = dict(texts=len(used), character_references=bool(ncr_undeclared and undeclared)) if ncr_undeclared else len(used)
    return archive, records


def localize_manual(archive, cfg, prefix='help_A/'):
    mapping = cfg['translations']
    kept = set(cfg['kept_english'])
    kept_pages = set(cfg.get('kept_pages', {}))
    used = set()
    files = []
    for name in sorted(archive.files):
        rel = name
        if not name.endswith('.html') or not any(rel == t or (t.endswith('/') and rel.startswith(t)) for t in cfg['targets']):
            continue
        html = archive.get(name).decode('utf-8')
        missing = [t for t in internet_manual.untranslated(html, mapping) if t not in kept and name not in kept_pages]
        if missing:
            raise ValueError(f'{name}: untranslated manual text {missing[:3]}')
        new = internet_manual.localize_html(html, mapping, used)
        archive = ChannelArchive(archive.replace(name, new.encode('utf-8')))
        files.append(name)
    unused = set(mapping) - used
    if unused:
        raise ValueError(f'Unused manual translations: {sorted(unused)[:3]}')
    return archive, dict(html_files=len(files), translated_runs=len(used), kept_license_runs=len(kept), kept_pages=sorted(kept_pages))


# ---------------------------------------------------------------- text images
def _font(size):
    load_library()
    from PIL import ImageFont
    from .opera_font import KOREAN_SHARED
    raw = ChannelArchive(KOREAN_SHARED.read_bytes()).get('Wii-kr_Round Gothic B.ttf')
    return ImageFont.truetype(io.BytesIO(raw), size)


def relabel(data, spec):
    """Erase an English label inside spec['box'] and draw the Korean text there."""
    load_library()
    from PIL import Image, ImageDraw
    source = Image.open(io.BytesIO(data))
    fmt = source.format
    image = source.convert('RGBA')
    x0, y0, x1, y1 = spec['box']
    if not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height):
        raise ValueError('Label box outside the image')
    draw = ImageDraw.Draw(image)
    fill = spec.get('fill', 'row')
    if fill == 'row':
        sample_x = max(0, x0 - 1)
        for y in range(y0, y1):
            draw.line([(x0, y), (x1 - 1, y)], fill=image.getpixel((sample_x, y)))
    elif fill == 'hblend':
        # Blend each row between the pixels just outside the box (keeps both gradients).
        if x0 < 1 or x1 >= image.width:
            raise ValueError('Blend box needs pixels on both sides')
        for y in range(y0, y1):
            a, b = image.getpixel((x0 - 1, y)), image.getpixel((x1, y))
            for x in range(x0, x1):
                t = (x - x0 + 1) / (x1 - x0 + 1)
                image.putpixel((x, y), tuple(round(p + (q - p) * t) for p, q in zip(a, b)))
    else:
        draw.rectangle([x0, y0, x1 - 1, y1 - 1], fill=tuple(fill) + (255,))
    text = spec['text']
    for size in range(spec['size'], 7, -1):
        font = _font(size)
        spacing = max(1, size // 6)
        l, t, r, b = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align=spec.get('align', 'center'))
        if r - l <= x1 - x0 - 4 and b - t <= y1 - y0 - 2:
            break
    else:
        raise ValueError(f'Korean label does not fit: {text!r}')
    if spec.get('align', 'center') == 'left':
        x = x0 + 1 - l
    else:
        x = x0 + (x1 - x0 - (r - l)) / 2 - l
    y = y0 + (y1 - y0 - (b - t)) / 2 - t
    draw.multiline_text((x, y), text, font=font, fill=tuple(spec['color']) + (255,), spacing=spacing, align=spec.get('align', 'center'))
    out = io.BytesIO()
    if fmt == 'BMP':
        image.convert('RGB').save(out, 'BMP')
    elif fmt == 'PNG':
        alpha = image.getchannel('A').getextrema()
        (image if alpha[0] < 255 else image.convert('RGB')).save(out, 'PNG')
    else:
        raise ValueError(f'Unsupported label image format {fmt}')
    return out.getvalue(), size


def relabel_images(archive, images):
    records = {}
    for name, spec in images.items():
        new, size = relabel(archive.get(name), spec)
        archive = ChannelArchive(archive.replace(name, new))
        records[name] = dict(text=spec['text'], font_px=size)
    return archive, records


# ---------------------------------------------------------------- CSS (v6)
def css_value(archive, spec):
    """Replace one declaration inside one rule of a stylesheet (v6 error heading size)."""
    name = spec['file']
    text = archive.get(name).decode('utf-8')
    if text.count(spec['old']) != 1:
        raise ValueError(f'{name}: expected one {spec["old"]!r}')
    at = text.index(spec['old'])
    start = text.rfind('{', 0, at)
    selector = text[text.rfind('}', 0, start) + 1:start].strip()
    if selector != spec['selector'] or '}' in text[start:at]:
        raise ValueError(f'{name}: {spec["old"]!r} is not inside the {spec["selector"]} rule')
    new = text[:at] + spec['new'] + text[at + len(spec['old']):]
    return ChannelArchive(archive.replace(name, new.encode('utf-8'))), dict(file=name, selector=selector, old=spec['old'], new=spec['new'])


# ---------------------------------------------------------------- Opera prefs (v5)
def set_pref(data, section, key, value):
    """Insert `key=value` right after the [section] header of an Opera prefs file."""
    text = data.decode('utf-8')
    if '\r' in text or not text.startswith('Opera Preferences version 2.1'):
        raise ValueError('Unexpected Opera prefs file')
    lines = text.split('\n')
    headers = [i for i, line in enumerate(lines) if line.strip() == f'[{section}]']
    if len(headers) != 1:
        raise ValueError(f'Expected one [{section}] section')
    start = headers[0] + 1
    end = next((j for j in range(start, len(lines)) if lines[j].startswith('[')), len(lines))
    if any(line.split('=', 1)[0].strip().lower() == key.lower() for line in lines[start:end]):
        raise ValueError(f'{key} already set in [{section}]')
    lines.insert(start, f'{key}={value}')
    return '\n'.join(lines).encode('utf-8')


def prefs(archive, names, spec):
    for name in names:
        archive = ChannelArchive(archive.replace(name, set_pref(archive.get(name), spec['section'], spec['key'], spec['value'])))
    return archive, names


# ---------------------------------------------------------------- favorites
def parse_adr(data):
    lines = data.decode('utf-8').split('\n')
    if lines[-1] != '' or (len(lines) - 1) % 6:
        raise ValueError('Unexpected favorites file layout')
    return [lines[i:i + 6] for i in range(0, len(lines) - 1, 6)]


def write_adr(entries):
    return ('\n'.join(line for entry in entries for line in entry) + '\n').encode('utf-8')


def adr_entries(pairs):
    return [[title, url, '', f'{k:.6f}', f'{k + 1:.6f}', f'{k + 1:.6f}'] for k, (title, url) in enumerate(pairs, 1)]


def favorites(archive, cfg, *, local, keep_listing=False):
    base = 'default_bookmarks/'
    records = {}
    for folder in cfg['folders']:
        names = [f'{base}{folder}/{n}' for n in ('append1.adr', 'opera6.adr', 'files.dat', 'files169.dat')]
        for n in names:
            if n not in archive.files:
                raise ValueError(f'Missing favorites file {n}')
        if local:
            adr = write_adr(adr_entries(cfg['local_test']))
            if keep_listing:
                # First-run import copies <folder>/append1.adr via files.dat; the
                # original 4-line files.dat/169 structure (with its thumbnail
                # lines) is what the parser expects, so keep it and replace only
                # the two .adr files with the test entries.
                for n in names[:2]:
                    archive = ChannelArchive(archive.replace(n, adr))
                records[folder] = dict(entries=len(cfg['local_test']), listing='original', urls='local test pages')
            else:
                listing = f'{folder}/append1.adr opera6.adr\n'.encode('ascii')
                for n, payload in zip(names, (adr, adr, listing, listing)):
                    archive = ChannelArchive(archive.replace(n, payload))
                records[folder] = dict(entries=len(cfg['local_test']), thumbnails=0, urls='local test pages')
        elif folder == cfg['source_folder']:
            changed = 0
            for n in names[:2]:
                entries = parse_adr(archive.get(n))
                for e in entries:
                    if e[0] in cfg['titles']:
                        e[0] = cfg['titles'][e[0]]
                        changed += 1
                archive = ChannelArchive(archive.replace(n, write_adr(entries)))
            records[folder] = dict(titles_translated=changed, urls='original')
        else:
            src = f'{base}{cfg["source_folder"]}/'
            for n, other in ((names[2], src + 'files.dat'), (names[3], src + 'files169.dat')):
                archive = ChannelArchive(archive.replace(n, archive.get(other)))
            records[folder] = dict(listing=f'uses {cfg["source_folder"]} favorites', urls='original')
    return archive, records


# ---------------------------------------------------------------- save banner (content 3)
def save_banner(content, cfg):
    archive = ChannelArchive(content)
    name = cfg['file']
    wibn = bytearray(archive.get(name))
    if wibn[:4] != b'WIBN' or wibn[0x20:0x60].decode('utf-16-be').rstrip('\0') != cfg['title'][0]:
        raise ValueError('Save banner identity differs')
    text = cfg['title'][1].encode('utf-16-be')
    if len(text) > 0x3e:
        raise ValueError('Save banner title too long')
    wibn[0x20:0x60] = text + bytes(0x40 - len(text))
    archive = ChannelArchive(archive.replace(name, bytes(wibn)))
    return archive.compact(), dict(file=name, title=cfg['title'][1])


# ---------------------------------------------------------------- layouts
def set_textbox(section, text):
    """Replace a text box string, never shrinking its buffer (runtime may reuse it)."""
    buf, _ = struct.unpack_from('>HH', section, 76)
    payload = (text + '\0').encode('utf-16-be')
    size = max(buf, len(payload))
    result = bytearray(section)
    offset = len(result)
    result.extend(payload + bytes(size - len(payload)))
    result.extend(bytes(-len(result) % 4))
    struct.pack_into('>I', result, 4, len(result))
    struct.pack_into('>HH', result, 76, size, len(payload))
    struct.pack_into('>I', result, 88, offset)
    return bytes(result)


def localize_layout(data, texts, group=None):
    sections = layout_sections(data)
    seen = set()
    for i, s in enumerate(sections):
        box = textbox(s)
        if box and box[0] in texts:
            en, ko = texts[box[0]]
            if box[1] != en:
                raise ValueError(f'Text box {box[0]} holds {box[1]!r}, expected {en!r}')
            sections[i] = set_textbox(s, ko)
            seen.add(box[0])
    if seen != set(texts):
        raise ValueError(f'Text boxes not found: {sorted(set(texts) - seen)}')
    if group:
        old, new = group
        hits = [i for i, s in enumerate(sections) if s[:4] == b'grp1' and s[8:24].split(b'\0')[0] == old.encode()]
        if len(hits) != 1 or any(s[:4] == b'grp1' and s[8:24].split(b'\0')[0] == new.encode() for s in sections):
            raise ValueError('Expected one language group to retag')
        s = bytearray(sections[hits[0]])
        s[8:24] = new.encode() + bytes(16 - len(new))
        sections[hits[0]] = bytes(s)
    return rebuild_layout(data, sections)


def keyboard(archive, cfg):
    name = cfg['keyboard_archive']
    inner = ChannelArchive(archive.get(name))
    original = inner
    for layout, texts in cfg['keyboard_layouts'].items():
        inner = ChannelArchive(inner.replace(layout, localize_layout(inner.get(layout), texts)))
    for n in original.files:
        if n not in cfg['keyboard_layouts'] and inner.get(n) != original.get(n):
            raise ValueError('Keyboard resource outside the edited layouts changed')
    archive = ChannelArchive(archive.replace(name, inner.compact()))
    return archive, dict(archive=name, layouts=sorted(cfg['keyboard_layouts']), labels=sum(len(v) for v in cfg['keyboard_layouts'].values()))


# ---------------------------------------------------------------- HOME Menu (content 5)
def _home_font_codes(raw_archive):
    from .channel_font import font_data
    arc = ChannelArchive(raw_archive)
    fonts = [font_data(arc.get(p))[1] for p in arc.files if p.endswith('.brfnt')]
    if len(fonts) != 1:
        raise ValueError('Unknown Korean HOME Menu font set')
    return fonts[0]


def korean_csv(data, columns, korean):
    if data[:2] != b'\xfe\xff':
        raise ValueError('HOME CSV is not UTF-16BE with BOM')
    text = data[2:].decode('utf-16-be')
    cells = list(re.finditer(r'"([^"]*)"', text))
    if len(cells) % columns:
        raise ValueError('HOME CSV column count differs')
    rows = len(cells) // columns
    targets = [cells[r * columns + korean].group(1) for r in range(rows)]
    if not all(any('\uac00' <= c <= '\ud7a3' for c in t) for t in targets):
        raise ValueError('HOME CSV Korean column missing')
    for i in reversed(range(len(cells))):
        a, b = cells[i].span(1)
        text = text[:a] + targets[i // columns] + text[b:]
    return b'\xfe\xff' + text.encode('utf-16-be'), targets


def home(archive, cfg):
    load_library()
    from libWiiPy.archive import decompress_lz77
    from .home_menu import KOREAN_SHARED
    shared = KOREAN_SHARED.read_bytes()
    korean = decompress_lz77(ChannelArchive(shared).get(cfg['source']))
    if ChannelArchive(korean).files.keys() != ChannelArchive(archive.get(cfg['archives'][1])).files.keys():
        raise ValueError('Korean HOME Menu archive generation differs')
    for name in cfg['archives']:
        archive = ChannelArchive(archive.replace(name, korean))
    codes = _home_font_codes(korean)
    csv = {}
    for name in cfg['csv']:
        data, targets = korean_csv(archive.get(name), cfg['columns'], cfg['korean_column'])
        missing = sorted({c for t in targets for c in characters(t) if ord(c) not in codes and c not in '\r\n'})
        if missing:
            raise ValueError(f'{name}: Korean HOME font lacks {missing}')
        archive = ChannelArchive(archive.replace(name, data))
        csv[name] = dict(rows=len(targets), columns_filled=cfg['columns'])
    return archive, dict(archives=cfg['archives'], korean_source='console shared1 content 0x17 ' + cfg['source'],
                         korean_source_sha256=sha256(shared), csv=csv, font_coverage_verified=True)


# ---------------------------------------------------------------- banner (content 0)
def banner(content, cfg, name):
    load_library()
    from libWiiPy.archive import decompress_lz77
    prefix = bytearray(content[:0x640])
    if prefix[0x80:0x84] != b'IMET':
        raise ValueError('Banner IMET identity')
    outer = ChannelArchive(content[0x640:])
    records = []
    for path, spec in cfg.items():
        payload = outer.get(path)
        if payload[:4] != b'IMD5' or hashlib.md5(payload[32:]).digest() != payload[16:32] or payload[32:36] != b'LZ77':
            raise ValueError(f'{path}: IMD5/LZ77 identity')
        inner = ChannelArchive(decompress_lz77(payload[32:]))
        before = inner
        inner = ChannelArchive(inner.replace(spec['layout'], localize_layout(inner.get(spec['layout']), spec['texts'], (spec['group_from'], spec['group_to']))))
        if any(inner.get(n) != before.get(n) for n in before.files if n != spec['layout']):
            raise ValueError('Banner change escaped the layout')
        raw = inner.compact()
        packed = b'LZ77' + compress_lz10(raw)
        if decompress_lz77(packed) != raw:
            raise ValueError('Banner LZ77 roundtrip')
        outer = ChannelArchive(outer.replace(path, b'IMD5' + len(packed).to_bytes(4, 'big') + bytes(8) + hashlib.md5(packed).digest() + packed))
        struct.pack_into('>I', prefix, 0x40 + (0x4c if path.endswith('icon.bin') else 0x50), len(raw))
        records.append(dict(archive=path, layout=spec['layout'], group=f'{spec["group_from"]}->{spec["group_to"]}', texts={k: v[1] for k, v in spec['texts'].items()}))
    text = name.encode('utf-16-be')
    if len(text) > 84:
        raise ValueError('IMET name too long')
    for i in range(10):
        at = 0x40 + 0x5c + 84 * i
        prefix[at:at + 84] = text + bytes(84 - len(text))
    prefix[0x630:0x640] = bytes(16)
    prefix[0x630:0x640] = hashlib.md5(bytes(prefix[0x40:0x640])).digest()
    return bytes(prefix) + outer.compact(), dict(imet_names=10, name=name, layouts=records)

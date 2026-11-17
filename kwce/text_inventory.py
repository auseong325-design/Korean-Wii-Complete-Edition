"""Text inventory of a channel WAD for the full localization review (2026-11-16).

Walks every content through U8 / IMD5 / LZ77 / LZ10 / LZ11 / Yaz0 / ASH layers and collects
  - BMG messages (MESGbmg1: UTF-16 / Shift-JIS / UTF-8 / CP1252),
  - BRLYT text-box strings (txt1),
  - HTML / text files (manuals, Opera pages),
  - font character sets (RFNT / RFNA CMAP).
`inventory(korean_wad, original_wad)` pairs every text container with the original's same path and marks it
changed / unchanged / new, so untranslated strings can be found where the build did (or did not) touch.
Only local analysis: nothing is written outside the caller's report.
"""
import re
import struct

from .channels import load_library, ChannelArchive

TEXT_EXT = ('.html', '.htm', '.txt', '.xml', '.js', '.css', '.ini', '.csv')
KEEP = {'wii', 'mii', 'miis', 'nintendo', 'wiiconnect', 'wiilink', 'home', 'ok', 'sd', 'usb', 'opera', 'dvd',
        'pin', 'url', 'http', 'https', 'www', 'com', 'jpg', 'png', 'gif', 'html', 'css', 'pdf', 'mb', 'kb', 'gb',
        'ds', 'tv', 'ip', 'dns', 'mac', 'ssid', 'wep', 'wpa', 'aes', 'tkip', 'lan', 'id', 'faq', 'kirby',
        'flash', 'adobe', 'macromedia', 'utf', 'euc', 'kr', 'nwc', 'xxx', 'wiimmfi', 'fujifilm', 'hal'}


def _decompress(name, data):
    """One layer of compression or None."""
    try:
        if data[:4] == b'LZ77' or (data[:1] == b'\x10' and name.lower().endswith(('.lz', '.lz7', '.lz77', '.cmp', '.lzs'))):
            from libWiiPy.archive import decompress_lz77
            return decompress_lz77(data)
        if data[:1] == b'\x11' and len(data) > 8:
            from .wiiroom_formats import decompress_lz11
            out = decompress_lz11(data)
            return out if out[:4] in (b'U\xaa8-', b'MESG', b'RLYT', b'RFNT', b'RFNA') or len(out) > 0x100 else None
        if data[:4] == b'Yaz0':
            from .votes_resources import decode_yaz0
            return decode_yaz0(data)
        if data[:4] == b'ASH0':
            from .formats import ash_decompress
            return ash_decompress(data)
    except Exception:
        return None
    return None


def _clean(s):
    return s.replace('\x00', '').strip()


def bmg_strings(data):
    if data[:8] != b'MESGbmg1':
        return []
    enc = data[0x10]; count = struct.unpack_from('>I', data, 0xc)[0]
    pos = 0x20; inf = dat = None
    for _ in range(count):
        if pos + 8 > len(data):
            break
        kind, size = data[pos:pos + 4], struct.unpack_from('>I', data, pos + 4)[0]
        if kind == b'INF1':
            inf = pos
        elif kind == b'DAT1':
            dat = pos + 8
        pos += max(size, 8)
    if inf is None or dat is None:
        return []
    n, esize = struct.unpack_from('>HH', data, inf + 8)
    out = []
    for i in range(n):
        off = struct.unpack_from('>I', data, inf + 16 + i * esize)[0]
        p = dat + off; chars = []
        if enc == 2 or enc == 0:
            while p + 1 < len(data):
                c = struct.unpack_from('>H', data, p)[0]
                if c == 0:
                    break
                if c == 0x1a:
                    ln = data[p + 2]; chars.append('{}'); p += max(ln, 4); continue
                chars.append(chr(c)); p += 2
            s = ''.join(chars)
        else:
            end = p
            raw = bytearray()
            while end < len(data) and data[end] != 0:
                if data[end] == 0x1a:
                    ln = data[end + 1]; raw += b'{}'; end += max(ln, 2); continue
                raw.append(data[end]); end += 1
            s = raw.decode({3: 'shift_jis', 4: 'utf-8'}.get(enc, 'cp1252'), errors='replace')
        out.append((i, s))
    return out


def brlyt_strings(data):
    if data[:4] != b'RLYT':
        return []
    from .channels import layout_sections
    out = []
    try:
        sections = layout_sections(data)
    except Exception:
        return []
    fonts = []
    for s in sections:
        if s[:4] == b'fnl1':
            n = struct.unpack_from('>H', s, 8)[0]
            for i in range(n):
                off = struct.unpack_from('>I', s, 12 + 8 * i)[0]
                fonts.append(s[12 + off:s.index(b'\0', 12 + off)].decode('ascii', 'replace'))
        if s[:4] == b'txt1':
            name = s[0xc:0x1c].split(b'\0')[0].decode('ascii', 'replace')
            strlen, font = struct.unpack_from('>H', s, 0x4e)[0], struct.unpack_from('>H', s, 0x52)[0]
            stroff = struct.unpack_from('>I', s, 0x58)[0]
            if strlen and stroff:
                text = s[stroff:stroff + strlen].decode('utf-16-be', 'replace')
                out.append((name, _clean(text), fonts[font] if font < len(fonts) else '?'))
    return out


def html_strings(data):
    if data[:2] in (b'\xfe\xff', b'\xff\xfe'):
        text = data.decode('utf-16', 'replace')
    else:
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            text = data.decode('shift_jis', 'replace')
    text = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', text)
    text = re.sub(r'(?s)<!--.*?-->', ' ', text)
    attrs = re.findall(r'(?i)\b(?:alt|title|value)\s*=\s*"([^"]*)"', text)
    body = re.sub(r'(?s)<[^>]+>', '\n', text)
    import html as _h
    lines = [_h.unescape(x).strip() for x in body.split('\n')] + [_h.unescape(a).strip() for a in attrs]
    return [x for x in lines if x]


def font_chars(data):
    from .channel_font import font_data
    if data[:4] == b'RFNA':
        data = b'RFNT' + data[4:]
    _, mapping, _ = font_data(data)
    return set(mapping)


def classify(s):
    """'ko' Hangul, 'ja' kana/kanji without Hangul, 'en' Latin words (not allow-listed), 'mixed-ja', 'other'."""
    hangul = any('가' <= c <= '힣' or 'ㄱ' <= c <= 'ㆎ' for c in s)
    kana = any('぀' <= c <= 'ヿ' for c in s)
    kanji = any('一' <= c <= '鿿' for c in s)
    words = [w for w in re.findall(r'[A-Za-z]{3,}', s) if w.lower() not in KEEP]
    if hangul and (kana or kanji):
        return 'mixed-ja'
    if hangul:
        return 'ko'
    if kana or kanji:
        return 'ja'
    if words:
        return 'en'
    return 'other'


def walk(name, data, depth=0, out=None):
    """{path: bytes} of text containers (BMG, BRLYT, HTML/text, fonts) under one blob."""
    out = {} if out is None else out
    if depth > 8 or len(data) < 4:
        return out
    if data[:4] == b'U\xaa8-':
        try:
            arc = ChannelArchive(data)
        except Exception:
            return out
        for p in arc.files:
            walk(f'{name}/{p}', arc.get(p), depth + 1, out)
        return out
    if data[:4] == b'IMD5':
        return walk(name, data[32:], depth + 1, out)
    if data[:8] == b'MESGbmg1' or data[:4] in (b'RLYT', b'RFNT', b'RFNA'):
        out[name] = data; return out
    if name.lower().endswith(TEXT_EXT):
        out[name] = data; return out
    inner = _decompress(name.rsplit('/', 1)[-1], data)
    if inner is not None and inner != data:
        walk(name, inner, depth + 1, out)
    return out


def wad_containers(wad):
    t = load_library().title.Title(); t.load_wad(wad)
    out = {}
    for i in range(len(t.tmd.content_records)):
        c = t.get_content_by_index(i)
        if c[:4] == b'IMET' or c[0x40:0x44] == b'IMET':
            walk(f'content{i}', c[c.find(b'U\xaa8-'):], 0, out)
        else:
            walk(f'content{i}', c, 0, out)
    return out


def strings_of(path, data):
    if data[:8] == b'MESGbmg1':
        return [('bmg', str(i), s) for i, s in bmg_strings(data)]
    if data[:4] == b'RLYT':
        return [('lyt', f'{n}@{f}', s) for n, s, f in brlyt_strings(data)]
    if data[:4] in (b'RFNT', b'RFNA'):
        return []
    return [('txt', str(i), s) for i, s in enumerate(html_strings(data))]


def inventory(korean_wad, original_wad=None):
    ko = wad_containers(korean_wad)
    og = wad_containers(original_wad) if original_wad else {}
    report = dict(containers=[], fonts={})
    for path, data in sorted(ko.items()):
        if data[:4] in (b'RFNT', b'RFNA'):
            try:
                report['fonts'][path] = font_chars(data)
            except Exception:
                pass
            continue
        state = 'new' if path not in og else ('changed' if og[path] != data else 'unchanged')
        items = []
        for kind, key, s in strings_of(path, data):
            s = _clean(s)
            if s:
                items.append(dict(kind=kind, key=key, text=s, cls=classify(s)))
        if items:
            report['containers'].append(dict(path=path, state=state, items=items))
    return report

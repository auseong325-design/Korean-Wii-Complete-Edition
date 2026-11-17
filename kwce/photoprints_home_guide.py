"""Photo Prints HOME Menu on a Korean console: dialogs, operations-guide chrome and exit prompt (revision 13).

Static facts from the content-1 DOL (identical in the original, build-v12 and hardware-v8;
`home_language_facts` re-checks them on every build):
* 0x8000a9a4 calls SCGetLanguage (0x800d03e8, SYSCONF item 0xb; Korean = 9) and
  0x8000b87c stores the result as the HOME language, replacing anything outside 0..6
  with 1 (English). A Korean console therefore runs the HOME Button Menu in language 1.
* 0x80014e04 loads HomeButton3/LZ77_homeBtn<_LANG>.arc from content 3 and
  HomeButton3/LZ77_homeBtn_nwm_<lang>.arc from content 7 through two 7-entry tables
  (0x802eaf98, 0x802eafb4), and manual.jpg, HomeButton3/home.csv and
  HomeButton3/network.csv from content 2. Content 3's own home.csv copies are never loaded.
So up to build-v12 the HOME dialogs show column 1 (English) of content 2's 10-column
home.csv, the operations guide uses nwm_eng (English chrome; it inherits the HOME font)
and its exit prompt is network.csv column 1 (English).

The HOME files are byte-identical to Wii no Ma's, whose v46 HOME guide was checked on
screen, so revision 13 follows the same recipe:
* content 2 home.csv: columns 0-6 take the Korean column 9 (the console's own HOME text).
* content 2 network.csv: its original seven columns all carry the Korean exit prompt.
* content 3: the Korean HOME font in all 14 HOME archives gains the prompt glyphs it
  lacks, copied from the console's Korean wbf2 (kwce.wiiroom_manual_font_v42).
* content 7: the three chrome textures of every NWM archive are redrawn in Korean with
  the Wii no Ma labels (kwce.wiiroom_manual_v40), and the four NWM archives that carry
  their own font (fra/ita/jpn/ned) get the extended Korean HOME font
  (kwce.wiiroom_manual_override_v46). nwm_eng, the one a Korean console loads, inherits
  the HOME font.
"""
import hashlib
import re
import struct

from .channels import ChannelArchive, compress_lz10, load_library
from .channel_font import font_data

HOME_CSV = 'HomeButton3/home.csv'
NETWORK = 'HomeButton3/network.csv'
PROMPT = '자세한 설명을 보기 위해\r\n채널을 종료하시겠습니까?\r\n(저장하지 않은 내용은 사라집니다.)'
KOREAN_COLUMN = 9
FILLED_COLUMNS = tuple(range(7))   # HOME languages the DOL can select (0..6)

# (VA, expected word) checked in the decompressed DOL before anything is changed.
DOL_FACTS = {
    0x8000a9b4: ('bl', 0x8000b87c),            # HOME language setter
    0x8000a9a4: ('bl', 0x800d03e8),            # SCGetLanguage
    0x800d03f0: ('word', 0x3880000b),          # li r4, 0xb (SYSCONF language item)
    0x8000b884: ('word', 0x2c040007),          # cmpwi r4, 7
    0x8000b8a0: ('word', 0x988300a8),          # stb r4, 0xa8(r3)
    0x8000b8a8: ('word', 0x38000001),          # li r0, 1  (out of range -> English)
    0x8000b8ac: ('word', 0x980300a8),          # stb r0, 0xa8(r3)
    0x80014f98: ('word', 0x8bc400a8),          # lbz r30, 0xa8(r4)
    0x80015028: ('word', 0x38600003),          # HOME archive from content 3
    0x800150c8: ('word', 0x38600007),          # NWM archive from content 7
    0x80015104: ('word', 0x389e022c),          # r4 = 'HomeButton3/home.csv'
    0x80015114: ('word', 0x38600002),          #   ... from content 2
    0x8001513c: ('word', 0x389e0241),          # r4 = 'HomeButton3/network.csv'
    0x80015140: ('word', 0x38600002),          #   ... from content 2
}
TABLES = {0x802eaf98: ['HomeButton3/LZ77_homeBtn.arc'] + [f'HomeButton3/LZ77_homeBtn_{x}.arc' for x in
                                                          ('ENG', 'GER', 'FRA', 'SPA', 'ITA', 'NED')],
          0x802eafb4: [f'HomeButton3/LZ77_homeBtn_nwm_{x}.arc' for x in ('jpn', 'eng', 'ger', 'fra', 'spa', 'ita', 'ned')]}
STRING_BASE = 0x802abf18


def sha(data):
    return hashlib.sha256(data).hexdigest()


def home_language_facts(dol):
    """Check the instruction words and tables the HOME analysis relies on; return a record."""
    off = struct.unpack_from('>18I', dol, 0)
    addr = struct.unpack_from('>18I', dol, 0x48)
    size = struct.unpack_from('>18I', dol, 0x90)

    def at(va):
        for o, a, s in zip(off, addr, size):
            if s and a <= va < a + s:
                return o + va - a
        raise ValueError(f'{va:#x} outside the DOL')

    for va, (kind, value) in DOL_FACTS.items():
        word = struct.unpack_from('>I', dol, at(va))[0]
        expected = (0x48000001 | ((value - va) & 0x03fffffc)) if kind == 'bl' else value
        if word != expected:
            raise ValueError(f'DOL word at {va:#x} differs from the reviewed HOME code')
    for table, names in TABLES.items():
        for i, name in enumerate(names):
            pointer = struct.unpack_from('>I', dol, at(table + 4 * i))[0]
            o = at(pointer)
            if dol[o:o + len(name) + 1] != name.encode('ascii') + b'\0':
                raise ValueError(f'HOME archive table entry {table:#x}[{i}] differs')
    for delta, name in ((0x22c, HOME_CSV), (0x241, NETWORK)):
        o = at(STRING_BASE + delta)
        if dol[o:o + len(name) + 1] != name.encode('ascii') + b'\0':
            raise ValueError(f'{name} string moved')
    return dict(language_source='SCGetLanguage 0x800d03e8 (Korean 9)', setter='0x8000b87c keeps 0..6, else 1 (English)',
                korean_console_home_language=1, home_archive='content 3 HomeButton3/LZ77_homeBtn_ENG.arc',
                guide_archive='content 7 HomeButton3/LZ77_homeBtn_nwm_eng.arc', csv_content=2,
                checked_words=len(DOL_FACTS), checked_table_entries=sum(len(v) for v in TABLES.values()))


def _cells(data):
    if data[:2] != b'\xfe\xff':
        raise ValueError('Expected UTF-16BE CSV')
    text = data[2:].decode('utf-16-be')
    return text, list(re.finditer(r'"([^"]*)"', text))


def _skeleton(data):
    """The CSV with every quoted cell emptied: separators and line ends only."""
    return re.sub(r'"[^"]*"', '""', _cells(data)[0])


def korean_home_csv(data):
    """Ten-column home.csv whose columns 0-6 repeat the Korean column 9."""
    text, cells = _cells(data)
    if len(cells) != 40:
        raise ValueError('Expected four by ten HOME messages')
    values = [m.group(1) for m in cells]
    for row in range(4):
        korean = values[row * 10 + KOREAN_COLUMN]
        if not re.search('[\uac00-\ud7a3]', korean):
            raise ValueError(f'home.csv row {row} has no Korean column')
        for column in FILLED_COLUMNS:
            values[row * 10 + column] = korean
    out = text
    for m, value in reversed(list(zip(cells, values))):
        lo, hi = m.span(1)
        out = out[:lo] + value + out[hi:]
    result = b'\xfe\xff' + out.encode('utf-16-be')
    check = [m.group(1) for m in _cells(result)[1]]
    if check != values or _skeleton(result) != _skeleton(data):
        raise ValueError('home.csv structure changed')
    return result, dict(file=HOME_CSV, columns=10, filled_columns=list(FILLED_COLUMNS), source_column=KOREAN_COLUMN,
                        rows=4, korean=[values[r * 10 + KOREAN_COLUMN] for r in range(4)], sha256=sha(result))


def korean_network_csv(original):
    """The original seven-column network.csv with every cell set to the Korean exit prompt."""
    text, cells = _cells(original)
    if (len(cells) != 7 or not cells[0].group(1).startswith('ゲームを終了します。')
            or not cells[1].group(1).startswith('This will quit the game.')):
        raise ValueError('network.csv is not the reviewed original seven-column prompt')
    out = text
    for m in reversed(cells):
        lo, hi = m.span(1)
        out = out[:lo] + PROMPT + out[hi:]
    result = b'\xfe\xff' + out.encode('utf-16-be')
    if [m.group(1) for m in _cells(result)[1]] != [PROMPT] * 7 or _skeleton(result) != _skeleton(original):
        raise ValueError('network.csv structure changed')
    return result, dict(file=NETWORK, columns=7, korean=PROMPT, all_columns=True, source_sha256=sha(original), sha256=sha(result))


def korean_guide_chrome(content7):
    """Redraw the three NWM chrome textures of every guide archive in Korean (Wii no Ma v40 labels)."""
    load_library()
    from libWiiPy.archive import decompress_lz77
    from PIL import Image
    from . import tpl
    from .wiiroom_manual_v40 import CHROME, smooth_mask
    archive = ChannelArchive(content7)
    records = []
    for name in archive.files:
        if 'LZ77_homeBtn_nwm_' not in name:
            continue
        before = ChannelArchive(decompress_lz77(archive.get(name)))
        language = before
        for basename, text in CHROME.items():
            paths = [p for p in language.files if p.endswith('/' + basename)]
            if len(paths) != 1:
                raise ValueError('Guide chrome identity')
            raw = language.get(paths[0])
            rec = tpl.texture_records(raw)[0]
            if rec['format'] != 1:
                raise ValueError('Guide chrome must be I8 coverage')
            mask = smooth_mask((rec['width'], rec['height']), text, (1, 1, rec['width'] - 1, rec['height'] - 1))
            new = tpl.encode(raw, 0, Image.merge('RGBA', (mask, mask, mask, mask)))
            tones = sum(n > 0 for n in tpl.decode(new, 0).getchannel('R').histogram()[1:255])
            if tones < 32 or len(new) != len(raw):
                raise ValueError('Guide chrome antialiasing/texture size regression')
            language = ChannelArchive(language.replace(paths[0], new))
            records.append(dict(archive=name.rsplit('/', 1)[-1], texture=basename, text=text, size=[rec['width'], rec['height']],
                                intermediate_tones=tones))
        if any(language.get(p) != before.get(p) for p in before.files if p.rsplit('/', 1)[-1] not in CHROME):
            raise ValueError('Unrelated guide resource changed')
        envelope = b'LZ77' if archive.get(name).startswith(b'LZ77') else b''
        archive = ChannelArchive(archive.replace(name, envelope + compress_lz10(language.compact())))
    if len(records) != 21:
        raise ValueError('Expected seven guide archives with three chrome textures each')
    return archive.compact(), records


def _font_codes(lz_archive):
    from libWiiPy.archive import decompress_lz77
    arc = ChannelArchive(decompress_lz77(lz_archive))
    fonts = [p for p in arc.files if p.endswith('.brfnt')]
    return {p: set(font_data(arc.get(p))[1]) for p in fonts}


def review_sheet(content7_before, content7_after, path, languages=('eng', 'jpn')):
    """Before/after sheet of the guide chrome textures (2x), <= 1600 px; returns its size."""
    load_library()
    from libWiiPy.archive import decompress_lz77
    from PIL import Image, ImageDraw
    from . import tpl
    from .wiiroom_manual_v40 import CHROME
    tiles = []
    for lang in languages:
        name = f'HomeButton3/LZ77_homeBtn_nwm_{lang}.arc'
        for tag, content in (('original', content7_before), ('Korean r13', content7_after)):
            inner = ChannelArchive(decompress_lz77(ChannelArchive(content).get(name)))
            for p in sorted(inner.files):
                if p.rsplit('/', 1)[-1] in CHROME:
                    tiles.append((f'nwm_{lang} {tag} {p.rsplit("/", 1)[-1]}', tpl.decode(inner.get(p), 0).convert('RGBA')))
    width = 16 + max(im.width for _, im in tiles) * 2
    sheet = Image.new('RGB', (width, sum(im.height * 2 + 22 for _, im in tiles) + 8), (40, 40, 90))
    draw = ImageDraw.Draw(sheet)
    y = 4
    for label, im in tiles:
        draw.text((8, y), label, fill=(255, 255, 0))
        y += 13
        big = im.resize((im.width * 2, im.height * 2))
        back = Image.new('RGBA', big.size, (60, 60, 120, 255))
        back.alpha_composite(big)
        sheet.paste(back.convert('RGB'), (8, y))
        y += big.height + 9
    sheet.thumbnail((1600, 1600))
    sheet.save(path)
    return dict(size=list(sheet.size))


def korean_home_guide(content2, content3, content7, network_original):
    """Revision-13 contents 2, 3 and 7 (bytes) and a record. Every check runs before returning."""
    load_library()
    from .wiiroom_manual_font_v42 import korean_prompt_fonts
    from .wiiroom_manual_override_v46 import korean_nwm_font_overrides
    c2 = ChannelArchive(content2)
    home_csv, home_rec = korean_home_csv(c2.get(HOME_CSV))
    network, network_rec = korean_network_csv(network_original)
    new2 = ChannelArchive(ChannelArchive(c2.replace(HOME_CSV, home_csv)).replace(NETWORK, network)).compact()
    new3, font_rec = korean_prompt_fonts(content3, PROMPT)
    chrome7, chrome_rec = korean_guide_chrome(content7)
    new7, override_rec = korean_nwm_font_overrides(chrome7, new3, PROMPT)
    # glyph coverage: every Korean HOME text in every font the HOME/guide can draw it with
    texts = set(PROMPT) | set(''.join(home_rec['korean']))
    needed = {ord(c) for c in texts if ord(c) >= 32 and c not in '\r\n'}
    a3, a7 = ChannelArchive(new3), ChannelArchive(new7)
    for name in a3.files:
        if 'LZ77_homeBtn' in name:
            for path, codes in _font_codes(a3.get(name)).items():
                if not needed <= codes:
                    raise ValueError(f'{name}: HOME font lacks {sorted(chr(c) for c in needed - codes)}')
    for name in a7.files:
        for path, codes in _font_codes(a7.get(name)).items():
            if not needed <= codes:
                raise ValueError(f'{name}: guide font lacks {sorted(chr(c) for c in needed - codes)}')
    changed2 = sorted(n for n in c2.files if ChannelArchive(new2).get(n) != c2.get(n))
    if changed2 != sorted([HOME_CSV, NETWORK]):
        raise ValueError(f'content 2 change escaped home.csv/network.csv: {changed2}')
    return (new2, new3, new7), dict(home_csv=home_rec, network_prompt=network_rec, home_fonts=font_rec,
                                    guide_chrome=chrome_rec, guide_font_overrides=override_rec,
                                    glyphs_checked=len(needed), changed_content2_files=changed2)

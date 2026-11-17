"""Korean HOME Menu resources for USA channels, taken from the console's own
Korean shared content (local NAND extract, never redistributed).

The USA HOME Menu library selects LZ77_homeBtn_<LANG>.arc by system language
and falls back to English for Korean. Each language archive is replaced with
the Korean archive of the same HomeButton library generation. With the
dialog fix enabled, the old seven-column message tables also receive Korean
fallback text. Final Korean-only builds fill all seven legacy language
columns; layouts, fonts and sounds are preserved.
"""
import hashlib,re,struct
from .channels import ROOT,ChannelArchive

KOREAN_SHARED=ROOT/'workspace/extracted-system/nand-current/shared1/00000017.app'
KOREAN_SHARED_SHA256='026cc2d29ba61991d820be466d7475a876396e949349b0c84054a01198e77d97'

LANGS=['ENG','FRA','GER','ITA','NED','SPA']
SOURCES={'HomeButton2':'HomeButton2/LZ77_homeBtn_KOR.arc','HomeButton3':'Homebutton3/LZ77_homeBtn_KOR.arc'}
KOREAN_MENU_RESOURCE=ROOT/'workspace/extracted-system/nand-current/title/00000001/00000002/content/0000009d.app'
KOREAN_CSV_SHA256='c1add6f75385a4464b272dda1314cc5e3ba8fa7c2a2ecb6f83eac975bd270bf5'
SAVE_WARNING='(저장하지 않은 내용은 사라집니다.)'


def korean_dialog_messages():
    raw=ChannelArchive(KOREAN_MENU_RESOURCE.read_bytes()).get('homebutton/home.csv')
    if hashlib.sha256(raw).hexdigest()!=KOREAN_CSV_SHA256:raise ValueError('Unknown Korean HOME message source')
    cells=re.findall(r'"([^"]*)"',raw.decode('utf-16'))
    if len(cells)!=40:raise ValueError('Expected four Korean system HOME message rows')
    return cells[9::10]


def localize_dialog_csv(data,messages,columns=(1,)):
    """Translate the selected English fallback in the older seven-column ABI.

    The Korean HOME archive is a subset font: it contains Wii/? and Hangul,
    not the English confirmation sentence. Keep unselected columns and the
    exact seven-column layout; the newer system CSV itself has ten columns.
    """
    if data[:2]!=b'\xfe\xff'or len(messages)!=4 or not columns or any(c not in range(7)for c in columns):raise ValueError('Unsupported HOME message CSV')
    text=data[2:].decode('utf-16-be');matches=list(re.finditer(r'"([^"]*)"',text))
    if len(matches)!=28:raise ValueError('Expected four seven-language HOME rows')
    english=[matches[i].group(1)for i in range(1,28,7)]
    if not english[2].startswith('Return to the Wii Menu?')or not english[3].startswith('Reset the software?'):
        raise ValueError('Unknown HOME confirmation messages')
    targets=[]
    for row,(before,target)in enumerate(zip(english,messages)):
        if row>=2 and 'Anything not saved will be lost.'in before:target+='\r\n'+SAVE_WARNING
        if '"'in target or '\0'in target:raise ValueError('Unsafe HOME message delimiters')
        targets.append(target)
    for index in reversed(range(28)):
        if index%7 not in columns:continue
        start,end=matches[index].span(1);text=text[:start]+targets[index//7]+text[end:]
    after=re.findall(r'"([^"]*)"',text)
    if len(after)!=28 or any(after[i]!=m.group(1)for i,m in enumerate(matches)if i%7 not in columns):
        raise ValueError('Unrelated HOME language or CSV structure changed')
    return b'\xfe\xff'+text.encode('utf-16-be'),targets


def korean_runtime_home_messages(content):
    """News/Forecast pass their own compressed CSV to HBM, not content6 CSV."""
    from .channels import load_library,compress_lz10
    load_library();from libWiiPy.archive import decompress_lz77
    path='home_nosave.csv.LZ';packed=content.get(path);original=decompress_lz77(packed)
    changed,targets=localize_dialog_csv(original,korean_dialog_messages(),tuple(range(7)))
    rebuilt=(b'LZ77'if packed.startswith(b'LZ77')else b'')+compress_lz10(changed)
    if decompress_lz77(rebuilt)!=changed:raise ValueError('HOME message compression roundtrip failed')
    result=ChannelArchive(content.replace(path,rebuilt))
    if any(content.get(n)!=result.get(n)for n in content.files if n!=path):raise ValueError('Unrelated channel UI resource changed')
    return result,dict(file=path,translated_columns=list(range(7)),translated_rows=4,
        source_csv_sha256=hashlib.sha256(original).hexdigest(),output_csv_sha256=hashlib.sha256(changed).hexdigest(),
        common_home_font_coverage_required=True,compression_roundtrip=True)


def korean_home_menu(content,fix_dialogs=False,all_dialog_languages=False):
    raw=KOREAN_SHARED.read_bytes();korean=ChannelArchive(raw);archive=ChannelArchive(content);replaced=[]
    messages=korean_dialog_messages()if fix_dialogs else None
    csv_records=[]
    for folder,source in SOURCES.items():
        data=korean.get(source)
        for lang in LANGS:
            name=f'{folder}/LZ77_homeBtn_{lang}.arc'
            if name in archive.files:archive=ChannelArchive(archive.replace(name,data));replaced.append(name)
        if fix_dialogs:
            from .channels import load_library
            from .channel_font import font_data
            load_library();from libWiiPy.archive import decompress_lz77
            language=ChannelArchive(decompress_lz77(data))
            fonts=[font_data(language.get(p))[1]for p in language.files if p.endswith('.brfnt')]
            if len(fonts)!=1:raise ValueError('Unknown HOME subset font')
            for name in [folder+'/home.csv',folder+'/home_nosave.csv']:
                if name not in archive.files:continue
                columns=tuple(range(7))if all_dialog_languages else(1,)
                changed,targets=localize_dialog_csv(archive.get(name),messages,columns)
                if any(ord(c)>=32 and ord(c)not in fonts[0]for text in targets for c in text):
                    raise ValueError('Korean HOME message has missing glyphs')
                archive=ChannelArchive(archive.replace(name,changed));replaced.append(name)
                csv_records.append(dict(file=name,translated_columns=list(columns),translated_rows=4,font_coverage_verified=True))
    if not replaced:raise ValueError('No HOME Menu language archives found')
    original=ChannelArchive(content)
    for name in original.files:
        if name not in replaced and archive.get(name)!=original.get(name):raise ValueError('HOME Menu common file changed')
    record=dict(replaced=replaced,korean_source='console shared1 content 0x17',korean_source_sha256=hashlib.sha256(raw).hexdigest())
    if fix_dialogs:record.update(dialog_csv=csv_records,dialog_source_sha256=KOREAN_CSV_SHA256,dialog_fonts_unchanged=True)
    return archive.compact(),record


def replace_shrinking(archive,name,payload):
    """Write payload over the file's old bytes, shrink the U8 size field, zero the freed bytes.

    Nothing else moves: every other file keeps its offset and the archive keeps its length (a longer
    Everybody Votes content 10 failed to initialise, so HOME fixes never grow a content).
    """
    offset,size=archive.files[name]
    if len(payload)>size:raise ValueError(f'{name}: new file is larger than the old one')
    data=bytearray(archive.data)
    data[offset:offset+size]=payload+bytes(size-len(payload))
    struct.pack_into('>I',data,archive.nodes[name]+8,len(payload))
    result=ChannelArchive(bytes(data))
    if result.get(name)!=payload or any(result.get(n)!=archive.get(n)for n in archive.files if n!=name):
        raise ValueError('In-place replacement changed an unrelated file')
    if any(result.files[n][0]!=archive.files[n][0]for n in archive.files):
        raise ValueError('In-place replacement moved a file')
    return bytes(data)


def home_font_mapping(raw):
    """Code points of the one .brfnt inside a HOME archive file (LZ77-wrapped *.arc or Yaz0-wrapped *.szs U8)."""
    from .channels import load_library
    from .channel_font import font_data
    load_library();from libWiiPy.archive import decompress_lz77
    from .votes_resources import decode_yaz0
    if raw[:4]==b'Yaz0':raw=decode_yaz0(raw)
    elif raw[:4]==b'LZ77' or raw[:1]==b'\x10':raw=decompress_lz77(raw)   # the *.arc files are bare LZ10 streams
    archive=ChannelArchive(raw)
    fonts=[font_data(archive.get(p))[1]for p in archive.files if p.endswith('.brfnt')]
    if len(fonts)!=1:raise ValueError('Unknown HOME subset font')
    return fonts[0]


def missing_glyphs(texts,mapping):
    """Characters (code point >= 32) of the texts that a HOME font cannot draw."""
    return sorted({c for text in texts for c in text if ord(c)>=32 and ord(c)not in mapping})


def korean_default_home(content):
    """Nintendo Channel content 6: Korean HOME Menu for the DEFAULT language slot, in place.

    The channel maps every console language above 6 (Korean is 9) to slot 0 (0x80048a60), the
    Japanese default: archive HomeButtonN/LZ77_homeBtn.arc and message column 0 of HomeButtonN/home*.csv.
    korean_home_menu() replaced only the six ENG..SPA archives, so a Korean console still drew the
    Japanese HOME Menu. Here each default archive becomes the console's own Korean archive byte for
    byte (shared1 0x17 *_KOR.arc, pinned by sha256) and the four message tables get the Korean text in
    all seven columns. Files are overwritten in place (the U8 size shrinks, freed bytes are zeroed), so
    nothing moves and the content keeps its length. Raises if a Korean sentence needs a glyph that the
    archive's own HOME font lacks. Returns (content bytes, record).
    """
    raw=KOREAN_SHARED.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=KOREAN_SHARED_SHA256:raise ValueError('Unknown Korean shared HOME content')
    korean=ChannelArchive(raw);archive=original=ChannelArchive(content);messages=korean_dialog_messages()
    touched=[];archives=[];tables=[]
    for folder,source in SOURCES.items():
        target=folder+'/LZ77_homeBtn.arc';data=korean.get(source)
        if target not in archive.files or data[:1]!=b'\x10' or archive.get(target)[:1]!=b'\x10':raise ValueError('Unknown default HOME archive')
        before=archive.get(target);mapping=home_font_mapping(data)
        archive=ChannelArchive(replace_shrinking(archive,target,data));touched.append(target)
        archives.append(dict(file=target,source=source,bytes_before=len(before),bytes_after=len(data),
            sha256_before=hashlib.sha256(before).hexdigest(),sha256_after=hashlib.sha256(data).hexdigest()))
        for name in(folder+'/home.csv',folder+'/home_nosave.csv'):
            before=archive.get(name);changed,targets=localize_dialog_csv(before,messages,tuple(range(7)))
            if missing_glyphs(targets,mapping):raise ValueError('Korean HOME message has missing glyphs')
            archive=ChannelArchive(replace_shrinking(archive,name,changed));touched.append(name)
            tables.append(dict(file=name,translated_columns=list(range(7)),translated_rows=4,
                bytes_before=len(before),bytes_after=len(changed),sha256_before=hashlib.sha256(before).hexdigest(),
                sha256_after=hashlib.sha256(changed).hexdigest(),font_coverage_verified=True))
    if len(archive.data)!=len(content):raise ValueError('HOME content length changed')
    if {n for n in original.files if archive.get(n)!=original.get(n)}!=set(touched):raise ValueError('Unexpected HOME files changed')
    return archive.data,dict(default_archives=archives,dialog_csv=tables,korean_source='console shared1 content 0x17',
        korean_source_sha256=KOREAN_SHARED_SHA256,dialog_source_sha256=KOREAN_CSV_SHA256,in_place=True,
        content_length=len(content))


def korean_official_table_home(content):
    """Nintendo Channel content 5: the HOME message table the executable really reads, in place.

    The executable loads HomeButton3/home.csv from group 3 = content 5 (0x8004f394 passes group 3), not
    from the seven-column copies in content 6. Content 5 holds the official ten-column table (ja en de fr
    es it nl zh zh ko) and a Korean console is mapped to slot 0, the Japanese column. The official Korean
    text of column 9 is copied into columns 0..6; columns 7..9 stay. Written in place (the U8 size
    shrinks, freed bytes are zeroed), so the content keeps its length. Raises if a Korean sentence needs
    a glyph that the official Korean HOME archive's font lacks. Returns (content bytes, record).
    """
    raw=KOREAN_SHARED.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=KOREAN_SHARED_SHA256:raise ValueError('Unknown Korean shared HOME content')
    mapping=home_font_mapping(ChannelArchive(raw).get(SOURCES['HomeButton3']))
    archive=original=ChannelArchive(content);name='HomeButton3/home.csv';before=archive.get(name)
    if before[:2]!=b'\xfe\xff':raise ValueError('Unsupported HOME message CSV')
    text=before[2:].decode('utf-16-be');matches=list(re.finditer(r'"([^"]*)"',text))
    if len(matches)!=40:raise ValueError('Expected four ten-language HOME rows')
    cells=[m.group(1)for m in matches];korean=cells[9::10]
    if not all(any('\uac00'<=c<='\ud7a3'for c in cell)for cell in korean):raise ValueError('Column 9 is not Korean')
    if any('\uac00'<=c<='\ud7a3'for cell in cells[0:40:10]for c in cell):raise ValueError('Column 0 already Korean')
    if any('"'in cell or '\0'in cell for cell in korean):raise ValueError('Unsafe HOME message delimiters')
    targets=[korean[i//10]if i%10<7 else cells[i]for i in range(40)]
    for index in reversed(range(40)):
        start,end=matches[index].span(1);text=text[:start]+targets[index]+text[end:]
    changed=b'\xfe\xff'+text.encode('utf-16-be');after=re.findall(r'"([^"]*)"',text)
    if len(after)!=40 or any(after[i]!=cells[i]for i in range(40)if i%10>=7):raise ValueError('Unrelated HOME language or CSV structure changed')
    if missing_glyphs(korean,mapping):raise ValueError('Korean HOME message has missing glyphs')
    archive=ChannelArchive(replace_shrinking(archive,name,changed))
    if len(archive.data)!=len(content):raise ValueError('HOME content length changed')
    if {n for n in original.files if archive.get(n)!=original.get(n)}!={name}:raise ValueError('Unexpected HOME files changed')
    return archive.data,dict(file=name,translated_columns=list(range(7)),source_column=9,kept_columns=[7,8,9],translated_rows=4,
        bytes_before=len(before),bytes_after=len(changed),sha256_before=hashlib.sha256(before).hexdigest(),
        sha256_after=hashlib.sha256(changed).hexdigest(),font_coverage_verified=True,korean_source='console shared1 content 0x17',
        korean_source_sha256=KOREAN_SHARED_SHA256,in_place=True,content_length=len(content))

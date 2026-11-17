"""Hangul-capable TrueType font for the Korean Set Personal Data build.

Input is the pinned OFL Noto Sans KR variable font (configs/channel-tools.lock.json
font_source). It is subset to the characters the channel can show (ASCII and
Latin for the other bundled catalogs, punctuation, Hangul compatibility jamo
for keyboard keys, all 11,172 Hangul syllables) and instanced at wght 400 to
match upstream's Noto Sans JP Regular. Name, copyright and OFL license records
are kept (OFL 1.1 conditions 2 and 3; the only Reserved Font Name is 'Source').
Output bytes are deterministic: the head timestamp is not recalculated.
"""
import hashlib,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FONT=ROOT/'workspace/channels/forecast/references/NotoSansKR.ttf'
FONT_SHA256='194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252'
WEIGHT=400
RANGES=[(0x20,0x7E),(0xA0,0xFF),(0x100,0x17F),(0x2010,0x2027),(0x2030,0x203A),(0x2190,0x2193),
        (0x3000,0x3003),(0x3008,0x3011),(0x3131,0x318E),(0xAC00,0xD7A3)]
DROP=['GSUB','GPOS','GDEF','BASE','STAT','DSIG','vhea','vmtx','VORG','MVAR','HVAR','VVAR','avar','fvar','gvar','cvar']

def unicodes(extra=''):
    wanted={c for lo,hi in RANGES for c in range(lo,hi+1)}
    wanted.update(ord(c)for c in extra if ord(c)>=0x20)
    return sorted(wanted)

def korean_font(extra_text='',path=FONT):
    from kwce.channels import load_library
    load_library()
    from fontTools.ttLib import TTFont
    from fontTools import subset
    from fontTools.varLib import instancer
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=FONT_SHA256:raise ValueError('Pinned OFL font differs')
    font=TTFont(io.BytesIO(raw),recalcTimestamp=False)
    options=subset.Options();options.name_IDs=['*'];options.name_languages=['*'];options.name_legacy=True
    options.layout_features=[];options.notdef_outline=True;options.glyph_names=False;options.hinting=False
    options.drop_tables=list(options.drop_tables)+[t for t in['GSUB','GPOS','GDEF','BASE','DSIG','VORG','vhea','vmtx']if t not in options.drop_tables]
    wanted=unicodes(extra_text);sub=subset.Subsetter(options);sub.populate(unicodes=wanted);sub.subset(font)
    static=instancer.instantiateVariableFont(font,{'wght':WEIGHT},inplace=False,updateFontNames=False)
    for table in DROP:
        if table in static:del static[table]
    names=static['name']
    for rec in list(names.names):
        if rec.nameID in(2,17):names.setName('Regular',rec.nameID,rec.platformID,rec.platEncID,rec.langID)
        elif rec.nameID in(4,):names.setName('Noto Sans KR Regular',4,rec.platformID,rec.platEncID,rec.langID)
        elif rec.nameID==6:names.setName('NotoSansKR-Regular',6,rec.platformID,rec.platEncID,rec.langID)
        elif rec.nameID in(1,16):names.setName('Noto Sans KR',rec.nameID,rec.platformID,rec.platEncID,rec.langID)
    static['OS/2'].usWeightClass=WEIGHT
    static.recalcTimestamp=False;out=io.BytesIO();static.save(out);data=out.getvalue()
    check=TTFont(io.BytesIO(data));cmap=check.getBestCmap()
    missing=[c for c in wanted if c not in cmap and(0xAC00<=c<=0xD7A3 or 0x3131<=c<=0x3163 or 0x20<=c<=0x7E)]
    if missing:raise ValueError(f'Font lacks {len(missing)} required characters')
    record=dict(source='google/fonts b38c5c93 ofl/notosanskr NotoSansKR[wght].ttf',source_sha256=FONT_SHA256,license='OFL-1.1',
        weight=WEIGHT,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),glyphs=len(check.getGlyphOrder()),mapped=len(cmap),
        hangul_syllables=sum(1 for c in range(0xAC00,0xD7A4)if c in cmap),compat_jamo=sum(1 for c in range(0x3131,0x318F)if c in cmap),
        copyright=check['name'].getDebugName(0),license_url=check['name'].getDebugName(14))
    return data,record

def coverage(data,text):
    """Characters of `text` (>= U+0020) missing from the font."""
    from kwce.channels import load_library
    load_library()
    from fontTools.ttLib import TTFont
    cmap=TTFont(io.BytesIO(data)).getBestCmap()
    return sorted({c for c in text if ord(c)>=0x20 and ord(c)not in cmap})

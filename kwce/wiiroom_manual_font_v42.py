"""Extend the HOME subset with the exact native Korean glyphs used by its prompt."""
import hashlib,math,struct
from .channels import ChannelArchive,load_library,compress_lz10
from .channel_font import font_data
from .channel_korean_font import korean_shared_fonts
from .wbf_text import WiiFontRenderer
from .wiiroom_manual_v40 import PROMPT

def extend_native_font(data,renderer,prompt=PROMPT):
    load_library();from PIL import Image
    blocks,mapping,widths=font_data(data);tg0=blocks[b'TGLP'][1];finf=bytearray(blocks[b'FINF'][1])
    cw,ch,baseline,maxwidth=tg0[8:12];sheet_size=struct.unpack_from('>I',tg0,12)[0]
    sheets,fmt,cols,rows,sw,sh=struct.unpack_from('>6H',tg0,16);pointer=struct.unpack_from('>I',tg0,28)[0]
    if (cw,ch,baseline,maxwidth)!=(21,22,19,22)or fmt!=0 or sheet_size!=sw*sh//2 or bytes(finf[28:31])!=bytes([27,25,21]):raise ValueError('Unreviewed HOME subset font')
    if (renderer.height,renderer.width,renderer.ascent,renderer.baseline)!=(27,25,21,19):raise ValueError('Native Korean font metrics differ')
    missing=sorted({ord(c)for c in prompt if ord(c)>=32 and ord(c)not in mapping});first=sheets*cols*rows;extra=[]
    if not missing:return data,dict(added_glyphs=0)
    if any(c not in renderer.mapping for c in missing):raise ValueError('Native Korean prompt glyph missing')
    for page in range(math.ceil(len(missing)/(cols*rows))):
        image=Image.new('L',(sw,sh))
        for item in range(cols*rows):
            n=page*cols*rows+item
            if n>=len(missing):break
            code=missing[n];cell,left,gw,advance=renderer.glyph(code)
            # HOME's nominal 21x22 cells have a 22x23 pitch. The verified
            # wbf2 glyphs fit that entire pitch without scaling or redraw.
            if cell.width>cw+1 or cell.height>ch+1:raise ValueError('Native glyph exceeds HOME cell pitch')
            image.paste(cell,((item%cols)*(cw+1),(item//cols)*(ch+1)))
            mapping[code]=first+n;widths[first+n]=bytes([left&255,gw,advance])
        tiled=bytearray()
        for by in range(0,sh,8):
            for bx in range(0,sw,8):
                for y in range(8):
                    for x in range(0,8,2):tiled.append((image.getpixel((bx+x,by+y))>>4)<<4|(image.getpixel((bx+x+1,by+y))>>4))
        if len(tiled)!=sheet_size:raise ValueError('Native glyph sheet size')
        extra.append(bytes(tiled))
    tg=bytearray(tg0[:32]);tg.extend(bytes(-(16+len(finf)+len(tg))%32));sheet_offset=16+len(finf)+len(tg)
    tg.extend(data[pointer:pointer+sheet_size*sheets]);tg.extend(b''.join(extra))
    struct.pack_into('>I',tg,4,len(tg));struct.pack_into('>H',tg,16,sheets+len(extra));struct.pack_into('>I',tg,28,sheet_offset)
    count=first+len(missing);wd=bytearray(b'CWDH'+bytes(12));struct.pack_into('>HHI',wd,8,0,count-1,0)
    wd.extend(b''.join(widths.get(i,finf[12:15])for i in range(count)));wd.extend(bytes(-len(wd)%4));struct.pack_into('>I',wd,4,len(wd))
    cm=bytearray(b'CMAP'+bytes(16));struct.pack_into('>HHHHI',cm,8,min(mapping),max(mapping),2,0,0);cm.extend(struct.pack('>H',len(mapping)))
    for code,glyph in sorted(mapping.items()):cm.extend(struct.pack('>HH',code,glyph))
    cm.extend(bytes(-len(cm)%4));struct.pack_into('>I',cm,4,len(cm))
    struct.pack_into('>III',finf,16,16+len(finf)+8,16+len(finf)+len(tg)+8,16+len(finf)+len(tg)+len(wd)+8)
    result=bytearray(data[:16]+finf+tg+wd+cm);struct.pack_into('>I',result,8,len(result));struct.pack_into('>H',result,14,4)
    _,checked,_=font_data(bytes(result))
    if checked!=mapping:raise ValueError('Native prompt font map verification')
    return bytes(result),dict(added_glyphs=len(missing),original_sheet_bytes_preserved=True,native_glyphs_not_redrawn=True,all_prompt_glyphs_verified=True)

def korean_prompt_fonts(content,prompt=PROMPT):
    load_library();from libWiiPy.archive import decompress_lz77
    native,source=korean_shared_fonts();renderer=WiiFontRenderer(ChannelArchive(native).get('wbf2.brfna'))
    archive=ChannelArchive(content);cache={};records=[]
    for name in archive.files:
        if 'LZ77_homeBtn'not in name:continue
        before=ChannelArchive(decompress_lz77(archive.get(name)));after=before
        fonts=[p for p in before.files if p.endswith('.brfnt')]
        if len(fonts)!=1:raise ValueError('HOME prompt font identity')
        p=fonts[0];old=before.get(p);key=hashlib.sha256(old).hexdigest()
        if key not in cache:cache[key]=extend_native_font(old,renderer,prompt)
        new,record=cache[key];after=ChannelArchive(after.replace(p,new))
        if any(before.get(p)!=after.get(p)for p in before.files if not p.endswith('.brfnt')):raise ValueError('Unrelated HOME resource changed')
        envelope=b'LZ77'if archive.get(name).startswith(b'LZ77')else b''
        archive=ChannelArchive(archive.replace(name,envelope+compress_lz10(after.compact())));records.append(dict(archive=name,**record))
    if len(records)!=14:raise ValueError('Expected fourteen HOME subset fonts')
    return archive.compact(),dict(source='verified local Korean system wbf2',source_sha256=source['source_sha256'],archives=records,all_prompt_glyphs_verified=True)

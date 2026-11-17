"""Append OFL Hangul glyphs to RFNT I4 sheets; preserve existing glyphs."""
import math,struct
from .channels import load_library

def font_data(data):
    if data[:6]!=b'RFNT\xfe\xff' or len(data)<48:raise ValueError('Unsupported font')
    pos=16;blocks={};mapping={};widths={}
    for _ in range(struct.unpack_from('>H',data,14)[0]):
        size=struct.unpack_from('>I',data,pos+4)[0];kind=data[pos:pos+4]
        if size<8 or pos+size>len(data):raise ValueError('Font section bounds')
        b=data[pos:pos+size]
        if kind==b'CWDH':
            first,last=struct.unpack_from('>HH',b,8)
            for i in range(first,last+1):widths[i]=b[16+3*(i-first):19+3*(i-first)]
        elif kind==b'CMAP':
            first,last,method=struct.unpack_from('>HHH',b,8)
            if method==0:
                base=struct.unpack_from('>H',b,20)[0];mapping.update({c:base+c-first for c in range(first,last+1)})
            elif method==1:
                for c in range(first,last+1):
                    glyph=struct.unpack_from('>H',b,20+2*(c-first))[0]
                    if glyph!=65535:mapping[c]=glyph
            elif method==2:
                for i in range(struct.unpack_from('>H',b,20)[0]):
                    c,glyph=struct.unpack_from('>HH',b,22+4*i);mapping[c]=glyph
            else:raise ValueError('Unknown font map')
        else:blocks[kind]=(pos,b)
        pos+=size
    return blocks,mapping,widths

def extend_font(data,characters,ttf):
    load_library();from PIL import Image,ImageDraw,ImageFont
    blocks,mapping,widths=font_data(data);oldpos,tglp=blocks[b'TGLP']
    cw,ch,baseline,maxwidth=tglp[8:12];sheet_size=struct.unpack_from('>I',tglp,12)[0]
    sheets,fmt,cols,rows,sw,sh=struct.unpack_from('>6H',tglp,16);pointer=struct.unpack_from('>I',tglp,28)[0]
    if fmt not in[0,2]or sheet_size!=(sw*sh//2 if fmt==0 else sw*sh)or sw%8 or sh%(8 if fmt==0 else 4):raise ValueError('Only tiled I4/IA4 font supported')
    missing=sorted({ord(c)for c in characters if ord(c)>=32 and ord(c)not in mapping})
    if not missing:return data,dict(added_glyphs=0)
    per_sheet=cols*rows;first=sheets*per_sheet
    if first+len(missing)>=65535:raise ValueError('Font glyph capacity')
    font=ImageFont.truetype(str(ttf),cw-2 if fmt==2 else cw)
    # Noto Sans KR's variable default is Thin; use Medium for the Wii UI.
    font.set_variation_by_axes([600 if fmt==2 else 500])
    extra=[]
    for page in range(math.ceil(len(missing)/per_sheet)):
        image=Image.new('L',(sw,sh));alpha=Image.new('L',(sw,sh))
        for item in range(per_sheet):
            n=page*per_sheet+item
            if n>=len(missing):break
            character=chr(missing[n]);x=(item%cols)*(cw+1);y=(item//cols)*(ch+1)
            # Render each cell independently: outlines cannot spill into the
            # neighboring glyph. IA4 carries black intensity under opaque
            # outline alpha, matching the original Latin city font.
            cell=Image.new('L',(cw,ch));cell_draw=ImageDraw.Draw(cell)
            cell_draw.text((1 if fmt==2 else 0,baseline),character,font=font,fill=255,anchor='ls')
            image.paste(cell,(x,y))
            if fmt==2:
                edge=Image.new('L',(cw,ch));ImageDraw.Draw(edge).text((1,baseline),character,font=font,fill=255,stroke_width=1,stroke_fill=255,anchor='ls');alpha.paste(edge,(x,y))
            mapping[missing[n]]=first+n;widths[first+n]=bytes([0,min(cw,255),min(cw,255)])
        tiled=bytearray()
        tile_height=8 if fmt==0 else 4
        for by in range(0,sh,tile_height):
            for bx in range(0,sw,8):
                for y in range(tile_height):
                    if fmt==0:
                        for x in range(0,8,2):tiled.append((image.getpixel((bx+x,by+y))>>4)<<4|(image.getpixel((bx+x+1,by+y))>>4))
                    else:
                        for x in range(8):
                            a=alpha.getpixel((bx+x,by+y));fill=image.getpixel((bx+x,by+y));intensity=min(255,round(fill*255/a))if a else 0
                            tiled.append(((a>>4)<<4)|(intensity>>4))
        extra.append(bytes(tiled))
    # Rebuild pointers while retaining all original sheet bytes and metrics.
    finf=bytearray(blocks[b'FINF'][1]);tg=bytearray(tglp[:32]);tg.extend(bytes(-((16+len(finf)+len(tg)))%32))
    sheet_offset=16+len(finf)+len(tg)
    tg.extend(data[pointer:pointer+sheet_size*sheets]);tg.extend(b''.join(extra))
    struct.pack_into('>I',tg,4,len(tg));struct.pack_into('>H',tg,16,sheets+len(extra));struct.pack_into('>I',tg,28,sheet_offset)
    count=first+len(missing);wd=bytearray(b'CWDH'+bytes(12));struct.pack_into('>HHI',wd,8,0,count-1,0)
    wd.extend(b''.join(widths.get(i,finf[12:15])for i in range(count)));wd.extend(bytes(-len(wd)%4));struct.pack_into('>I',wd,4,len(wd))
    cm=bytearray(b'CMAP'+bytes(16));struct.pack_into('>HHHHI',cm,8,min(mapping),max(mapping),2,0,0)
    cm.extend(struct.pack('>H',len(mapping)))
    for code,glyph in sorted(mapping.items()):cm.extend(struct.pack('>HH',code,glyph))
    cm.extend(bytes(-len(cm)%4));struct.pack_into('>I',cm,4,len(cm))
    struct.pack_into('>III',finf,16,16+len(finf)+8,16+len(finf)+len(tg)+8,16+len(finf)+len(tg)+len(wd)+8)
    result=bytearray(data[:16]+finf+tg+wd+cm);struct.pack_into('>I',result,8,len(result));struct.pack_into('>H',result,14,4)
    _,checked,_=font_data(bytes(result))
    if any(checked[c]!=g for c,g in mapping.items()):raise ValueError('Font mapping verification failed')
    return bytes(result),dict(added_glyphs=len(missing),original_sheet_bytes_preserved=True,sheets_before=sheets,sheets_after=sheets+len(extra),added_glyph_weight=600 if fmt==2 else 500,added_black_outline_pixels=1 if fmt==2 else 0)

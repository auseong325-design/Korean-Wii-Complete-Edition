"""Narrow the Hangul glyphs of a 43K RFNA system font (wbf1/wbf2) in place.

The Mii Contest channel draws its system-font text at the font's own aspect
(layout font width is not applied to it), and the console font's Hangul is
designed wide. Each Hangul cell is resampled to `factor` of its width, the
CWDH glyph/advance widths shrink with it, and every CX Huffman sheet is
re-encoded and zero-padded to its original size so no pointer moves.
"""
import struct
from . import cx_huffman
from .channel_font import font_data
from .channels import load_library

HANGUL=lambda c:0xac00<=c<=0xd7a3 or 0x3131<=c<=0x318e or 0x1100<=c<=0x11ff


def _untile_i4(raw,w,h):
    px=bytearray(w*h);i=0
    for by in range(0,h,8):
        for bx in range(0,w,8):
            for y in range(8):
                row=(by+y)*w+bx
                for x in range(0,8,2):
                    b=raw[i];i+=1;px[row+x]=(b>>4)*17;px[row+x+1]=(b&15)*17
    return px


def _tile_i4(px,w,h):
    out=bytearray()
    for by in range(0,h,8):
        for bx in range(0,w,8):
            for y in range(8):
                row=(by+y)*w+bx
                for x in range(0,8,2):out.append((min(15,(px[row+x]+8)//17)<<4)|min(15,(px[row+x+1]+8)//17))
    return bytes(out)


def narrow_hangul(rfna,factor):
    load_library();from PIL import Image
    if rfna[:4]!=b'RFNA':raise ValueError('Expected RFNA font')
    blocks,mapping,widths=font_data(b'RFNT'+rfna[4:]);_,tglp=blocks[b'TGLP']
    cw,ch=tglp[8],tglp[9];sheet_size=struct.unpack_from('>I',tglp,12)[0]
    sheets,fmt,cols,rows,sw,sh=struct.unpack_from('>6H',tglp,16);pointer=struct.unpack_from('>I',tglp,28)[0]
    if fmt!=0x8000 or sheet_size!=sw*sh//2:raise ValueError('Only compressed I4 RFNA sheets supported')
    per=cols*rows;glyphs={}
    for code,g in mapping.items():
        if HANGUL(code):glyphs.setdefault(g//per,set()).add(g%per)
    out=bytearray(rfna);pos=pointer;changed=set();stats=dict(glyphs=0,sheets=0,factor=factor)
    for sheet in range(sheets):
        n=struct.unpack_from('>I',rfna,pos)[0];stream=rfna[pos+4:pos+4+n]
        if sheet in glyphs:
            px=_untile_i4(cx_huffman.decompress(stream),sw,sh)
            image=Image.frombytes('L',(sw,sh),bytes(px))
            for item in sorted(glyphs[sheet]):
                g=sheet*per+item;left,gw,adv=widths[g]
                new_gw=max(1,round(gw*factor));x=(item%cols)*(cw+1);y=(item//cols)*(ch+1)
                # The faintest 4-bit level is dropped so each sheet still fits its original size.
                cell=image.crop((x,y,x+gw,y+ch)).resize((new_gw,ch),Image.LANCZOS).point(lambda v:0 if v<26 else v)
                image.paste(0,(x,y,x+cw,y+ch));image.paste(cell,(x,y))
                widths[g]=bytes([left,new_gw,max(1,round(adv*factor))]);changed.add(g);stats['glyphs']+=1
            packed=cx_huffman.compress(_tile_i4(image.tobytes(),sw,sh))
            if len(packed)>n:raise ValueError(f'Narrowed sheet {sheet} exceeds original size')
            out[pos+4:pos+4+n]=packed+bytes(n-len(packed));stats['sheets']+=1
        pos+=4+n
    # Rewrite the changed CWDH entries in place (RFNA keeps the RFNT block layout).
    at=16
    for _ in range(struct.unpack_from('>H',rfna,14)[0]):
        kind=rfna[at:at+4];size=struct.unpack_from('>I',rfna,at+4)[0]
        if kind==b'CWDH':
            first,last=struct.unpack_from('>HH',rfna,at+8)
            for g in changed:
                if first<=g<=last:out[at+16+3*(g-first):at+19+3*(g-first)]=widths[g]
        at+=size
    if len(out)!=len(rfna):raise ValueError('Font size changed')
    return bytes(out),stats

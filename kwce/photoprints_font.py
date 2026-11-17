"""Append Hangul glyphs to the channel's own `font_rodan_28.brfna`.

content[2]'s font is FOT-Rodan (RFNT block layout, CX Huffman I4 sheets,
fmt 0x8000) — NOT the system shared RFNA, so it has every kanji/kana the UI
needs but no Hangul. This keeps all existing glyphs and appends the Hangul
syllables actually used by the Korean UI, each rendered from the console's
verified 43K Korean shared font (wbf2) resampled into the rodan cell, re-tiled
to I4 and CX-Huffman compressed into new sheets. The sheet_size/format are
unchanged; only sheet count, pointers and the CMAP/CWDH grow.
"""
import struct
from .channels import load_library
from .channel_font import font_data
from .channel_korean_font import korean_shared_fonts
from .korean_font_narrow import _tile_i4,_untile_i4
from .wbf_text import WiiFontRenderer
from . import cx_huffman

HANGUL=lambda c:0xac00<=c<=0xd7a3 or 0x3130<=c<=0x318f


def _korean_renderer():
    fonts,_=korean_shared_fonts()
    from .channels import ChannelArchive
    return WiiFontRenderer(ChannelArchive(fonts).get('wbf2.brfna'))


# nw4r samples a glyph at (cellX+1, cellY+1): every cell has a 1-px left/top
# border and the glyph window is [1, 1+glyphWidth) x [1, 1+cellHeight). Both the
# original rodan sheets (sampled) and the 43K wbf2 Hangul (2,350/2,350) keep
# their ink inside that window. WiiFontRenderer.glyph crops from the border
# column instead, so its glyphs lose their last ink column.
class ExactCellRenderer(WiiFontRenderer):
    def glyph(self,code):
        g=self.mapping.get(code)
        if g is None:g=self.mapping.get(self.default,0)
        per=self.cols*self.rows;sheet=self._sheet(g//per);item=g%per
        x=(item%self.cols)*(self.cw+1)+1;y=(item//self.cols)*(self.ch+1)+1
        left,gw,adv=self.widths[g];left=left-256 if left>127 else left
        return sheet.crop((x,y,x+gw,y+self.ch)),left,gw,adv


def exact_korean_renderer():
    fonts,_=korean_shared_fonts()
    from .channels import ChannelArchive
    return ExactCellRenderer(ChannelArchive(fonts).get('wbf2.brfna'))


def append_hangul(rfna,characters):
    load_library();from PIL import Image
    if rfna[:4]!=b'RFNA':raise ValueError('Expected RFNA font')
    blocks,mapping,widths=font_data(b'RFNT'+rfna[4:])
    _,finf=blocks[b'FINF'];_,tglp=blocks[b'TGLP']
    cw,ch,baseline=tglp[8],tglp[9],tglp[10]
    sheet_size=struct.unpack_from('>I',tglp,12)[0]
    sheets,fmt,cols,rows,sw,sh=struct.unpack_from('>6H',tglp,16)
    pointer=struct.unpack_from('>I',tglp,28)[0]
    if fmt!=0x8000 or sheet_size!=sw*sh//2:raise ValueError('Only CX Huffman I4 RFNA supported')
    per=cols*rows
    missing=sorted({ord(c) for c in characters if HANGUL(ord(c)) and ord(c) not in mapping})
    if not missing:return rfna,dict(added_glyphs=0,sheets_before=sheets,sheets_after=sheets)
    # Read the existing variable-length sheet streams verbatim.
    pos=pointer;existing=[]
    for _ in range(sheets):
        n=struct.unpack_from('>I',rfna,pos)[0];existing.append(rfna[pos:pos+4+n]);pos+=4+n
    renderer=_korean_renderer()
    f=(ch-4)/renderer.ch  # scale system cell (~23px) up to the rodan cell
    first=sheets*per;new_sheets=[]
    import math
    for page in range(math.ceil(len(missing)/per)):
        image=Image.new('L',(sw,sh))
        for item in range(per):
            n=page*per+item
            if n>=len(missing):break
            code=missing[n];cell,left,gw,adv=renderer.glyph(code)
            tw=max(1,min(cw,round(gw*f)));th=max(1,round(renderer.ch*f))
            scaled=cell.resize((tw,th),Image.LANCZOS)
            x=(item%cols)*(cw+1);y=(item//cols)*(ch+1)
            oy=y+max(0,baseline-round(renderer.baseline*f))
            image.paste(scaled,(x+max(0,round(left*f)),oy))
            glyph=first+n;mapping[code]=glyph;widths[glyph]=bytes([0,tw,max(1,min(cw,round(adv*f)))])
        packed=cx_huffman.compress(_tile_i4(image.tobytes(),sw,sh))
        new_sheets.append(struct.pack('>I',len(packed))+packed)
    count=first+len(missing)
    finf=bytearray(finf);tg=bytearray(tglp[:32]);tg.extend(bytes(-(16+len(finf)+32)%32))
    sheet_offset=16+len(finf)+len(tg)
    tg.extend(b''.join(existing));tg.extend(b''.join(new_sheets))
    struct.pack_into('>I',tg,4,len(tg));struct.pack_into('>H',tg,16,sheets+len(new_sheets));struct.pack_into('>I',tg,28,sheet_offset)
    wd=bytearray(b'CWDH'+bytes(12));struct.pack_into('>HHI',wd,8,0,count-1,0)
    wd.extend(b''.join(widths.get(i,finf[12:15]) for i in range(count)));wd.extend(bytes(-len(wd)%4));struct.pack_into('>I',wd,4,len(wd))
    cm=bytearray(b'CMAP'+bytes(16));struct.pack_into('>HHHHI',cm,8,min(mapping),max(mapping),2,0,0)
    cm.extend(struct.pack('>H',len(mapping)))
    for code,glyph in sorted(mapping.items()):cm.extend(struct.pack('>HH',code,glyph))
    cm.extend(bytes(-len(cm)%4));struct.pack_into('>I',cm,4,len(cm))
    struct.pack_into('>III',finf,16,16+len(finf)+8,16+len(finf)+len(tg)+8,16+len(finf)+len(tg)+len(wd)+8)
    result=bytearray(b'RFNA'+rfna[4:8]);result.clear()
    result=bytearray(rfna[:16]+bytes(finf)+bytes(tg)+bytes(wd)+bytes(cm))
    struct.pack_into('>I',result,8,len(result));struct.pack_into('>H',result,14,4)
    _,checked,_=font_data(b'RFNT'+bytes(result[4:]))
    for code in missing:
        if checked.get(code)!=mapping[code]:raise ValueError('Hangul mapping verification failed')
    return bytes(result),dict(added_glyphs=len(missing),sheets_before=sheets,sheets_after=sheets+len(new_sheets),
        source='console 43K shared wbf2',cell=[cw,ch])



# ---------------------------------------------------------------------------
# v6+: ArchiveFont-valid append (fixes the boot crash of v1-v3).
#
# The game loads font_rodan_28.brfna with nw4r::ut::ArchiveFont, which requires
# the GLGR (glyph group) block first and uses it to size/load sheets, CWDH and
# CMAP blocks. append_hangul() above rebuilt the file as FINF/TGLP/CWDH/CMAP
# only, so ArchiveFont construction failed, the font kept mFontInfo=NULL and
# ArchiveFontBase::FindGlyphIndex (0x801bdf40, lwz r6,16(r6)) read 0x00000010.
# This variant keeps every original block byte-for-byte except pointers/counts,
# updates GLGR (sizes + per-set MSB-first use bits), appends the new sheets and
# a new CWDH, and inserts a Hangul CMAP FIRST in the chain because the last
# original CMAP is a 0000-FFFF scan map that would otherwise shadow Hangul.
# ---------------------------------------------------------------------------

def _align(x,a):return (x+a-1)//a*a


def _parse_rfna(f):
    if f[:6]!=b'RFNA\xfe\xff':raise ValueError('Expected big-endian RFNA')
    if struct.unpack_from('>I',f,8)[0]!=len(f) or struct.unpack_from('>H',f,12)[0]!=16:raise ValueError('RFNA header')
    pos=16;blocks=[]
    for _ in range(struct.unpack_from('>H',f,14)[0]):
        kind=f[pos:pos+4];size=struct.unpack_from('>I',f,pos+4)[0]
        if size<8 or pos+size>len(f):raise ValueError('RFNA block bounds')
        blocks.append((kind,pos,size));pos+=size
    if pos!=len(f):raise ValueError('RFNA trailing data')
    kinds=[k for k,_,_ in blocks]
    ncw=kinds.count(b'CWDH');ncm=kinds.count(b'CMAP')
    if kinds!=[b'GLGR',b'FINF',b'TGLP']+[b'CWDH']*ncw+[b'CMAP']*ncm:raise ValueError('Unexpected RFNA block order')
    _,gp,gs=blocks[0];G=f[gp+8:gp+gs]
    sheet_size,gps,nset,nsheet,ncwdh,ncmap=struct.unpack_from('>IHHHHH',G,0)
    if (ncwdh,ncmap)!=(ncw,ncm):raise ValueError('GLGR block counts differ')
    names=list(struct.unpack_from(f'>{nset}H',G,14));A=_align(14+2*nset,4)
    ss=list(struct.unpack_from(f'>{nsheet}I',G,A));o=A+4*nsheet
    sc=list(struct.unpack_from(f'>{ncwdh}I',G,o));o+=4*ncwdh
    sm=list(struct.unpack_from(f'>{ncmap}I',G,o));o+=4*ncmap
    ws,wc,wm=((n+31)//32 for n in(nsheet,ncwdh,ncmap))
    words=struct.unpack_from(f'>{nset*(ws+wc+wm)}I',G,o);o+=4*len(words)
    bits=lambda w,n:[(w[i//32]>>(31-i%32))&1 for i in range(n)]
    useS=[bits(words[i*ws:(i+1)*ws],nsheet) for i in range(nset)]
    b0=nset*ws;useC=[bits(words[b0+i*wc:b0+(i+1)*wc],ncwdh) for i in range(nset)]
    b1=b0+nset*wc;useM=[bits(words[b1+i*wm:b1+(i+1)*wm],ncmap) for i in range(nset)]
    if min(names)!=gp+8+o:raise ValueError('GLGR name area position differs')
    _,tp,tsz=blocks[2];T=f[tp+8:tp+tsz]
    sheets=struct.unpack_from('>H',T,8)[0];image=struct.unpack_from('>I',T,20)[0]
    if sheets!=nsheet:raise ValueError('TGLP/GLGR sheet count differs')
    streams=[];p=image
    for _ in range(nsheet):
        n=struct.unpack_from('>I',f,p)[0];streams.append(f[p+4:p+4+n]);p+=4+n
    if p!=tp+tsz:raise ValueError('TGLP stream layout differs')
    if [len(s) for s in streams]!=ss:raise ValueError('GLGR sheet sizes differ')
    if [b[2] for b in blocks if b[0]==b'CWDH']!=sc or [b[2] for b in blocks if b[0]==b'CMAP']!=sm:raise ValueError('GLGR block sizes differ')
    return dict(blocks=blocks,G=G,gp=gp,gs=gs,sheet_size=sheet_size,gps=gps,nset=nset,nsheet=nsheet,
        names=names,name_blob=f[min(names):gp+gs],useS=useS,useC=useC,useM=useM,
        tglp=(tp,tsz,T),image=image,streams=streams)


def find_glyph(f,code):
    """Emulate ResFontBase::FindGlyphIndex: first CMAP in the chain whose range holds code wins."""
    finf=_parse_rfna(f)['blocks'][1][1];ptr=struct.unpack_from('>I',f,finf+8+16)[0]
    while ptr:
        lo,hi,meth=struct.unpack_from('>HHH',f,ptr);nxt=struct.unpack_from('>I',f,ptr+8)[0]
        if lo<=code<=hi:
            if meth==0:return struct.unpack_from('>H',f,ptr+12)[0]+code-lo
            if meth==1:
                g=struct.unpack_from('>H',f,ptr+12+2*(code-lo))[0];return None if g==0xffff else g
            n=struct.unpack_from('>H',f,ptr+12)[0];a,b=0,n-1
            while a<=b:
                m=(a+b)//2;c,g=struct.unpack_from('>HH',f,ptr+14+4*m)
                if c==code:return g
                if c<code:a=m+1
                else:b=m-1
            return None
        ptr=nxt
    return None


def check_rfna(f):
    """Structural ArchiveFont checks: GLGR first, counts/sizes, names, pointer chains."""
    P=_parse_rfna(f);bl=P['blocks']
    finf=bl[1][1];pg,pw,pm=struct.unpack_from('>III',f,finf+8+8)
    cw=[b for b in bl if b[0]==b'CWDH'];cm=[b for b in bl if b[0]==b'CMAP']
    if pg!=bl[2][1]+8 or pw!=cw[0][1]+8 or pm!=cm[0][1]+8:raise ValueError('FINF pointers differ')
    for chain,off in((cw,4),(cm,8)):
        for i,(_,p,_) in enumerate(chain):
            nxt=struct.unpack_from('>I',f,p+8+off)[0]
            if nxt!=(chain[i+1][1]+8 if i+1<len(chain) else 0):raise ValueError('Block chain pointer differs')
    for o in P['names']:
        if f.find(b'\0',o)<0:raise ValueError('GLGR name offset')
    if P['image']%32:raise ValueError('Sheet image alignment')
    return dict(sheets=P['nsheet'],cwdh=len(cw),cmap=len(cm),sets=P['nset'],
        all_sheets_in_set0=all(P['useS'][0]))


def append_hangul_rfna(rfna,characters,exact=False):
    load_library();from PIL import Image
    P=_parse_rfna(rfna);bl=P['blocks']
    _,tp,tsz,T=(None,)+P['tglp']
    cw,ch,baseline=T[0],T[1],T[2];nsheet=P['nsheet']
    fmt,cols,rows,sw,sh=struct.unpack_from('>5H',T,10)
    if fmt!=0x8000 or P['sheet_size']!=sw*sh//2:raise ValueError('Only CX Huffman I4 RFNA supported')
    _,mapping,_=font_data(b'RFNT'+rfna[4:])
    codes=sorted({ord(c) for c in characters if 0xac00<=ord(c)<=0xd7a3 and ord(c) not in mapping})
    if len({c for c in characters if HANGUL(ord(c)) and not 0xac00<=ord(c)<=0xd7a3}):
        raise ValueError('Only precomposed Hangul syllables are supported in the appended map')
    if not codes:return rfna,dict(added_glyphs=0)
    per=cols*rows;first=nsheet*per
    if exact:
        # v10+: crop the system glyph from its real window, scale uniformly so the
        # system advance (22) maps to the cell width, paste into the cell window
        # at (1,1) and keep the bearing in CWDH. Ink then lies in [1,1+gw) and
        # left+gw <= advance, so nothing is clipped or overlaps.
        renderer=exact_korean_renderer()
        sys_adv=max(renderer.widths[renderer.mapping[c]][2] for c in codes)
        f=cw/sys_adv
    else:
        renderer=_korean_renderer();f=(ch-4)/renderer.ch
    import math
    streams=[];widths=[];layouts=[]
    for page in range(math.ceil(len(codes)/per)):
        image=Image.new('L',(sw,sh))
        for item in range(per):
            n=page*per+item
            if n>=len(codes):break
            cell,left,gw,adv=renderer.glyph(codes[n])
            x=(item%cols)*(cw+1);y=(item//cols)*(ch+1)
            if exact:
                left_n=round(left*f);advance=min(cw,round(adv*f))
                tw=max(1,min(round(gw*f),cw-max(left_n,0),advance-left_n));th=max(1,min(ch,round(renderer.ch*f)))
                off_y=max(0,min(ch-th,round(baseline-renderer.baseline*f)))
                window=Image.new('L',(cw,ch));window.paste(cell.resize((tw,th),Image.LANCZOS),(0,off_y))
                image.paste(window,(x+1,y+1))
                widths.append(bytes([left_n&0xff,tw,advance]))
                continue
            tw=max(1,min(cw,round(gw*f)));th=max(1,round(renderer.ch*f))
            image.paste(cell.resize((tw,th),Image.LANCZOS),(x+max(0,round(left*f)),y+max(0,baseline-round(renderer.baseline*f))))
            widths.append(bytes([0,tw,max(1,min(cw,round(adv*f)))]))
        if exact:
            from . import photoprints_cx
            packed,layout=photoprints_cx.compress(_tile_i4(image.tobytes(),sw,sh));layouts.append(layout)
        else:
            packed=cx_huffman.compress(_tile_i4(image.tobytes(),sw,sh))
        packed+=bytes(-len(packed)%4)
        if cx_huffman.decompress(packed)!=_tile_i4(image.tobytes(),sw,sh):raise ValueError('CX sheet roundtrip')
        streams.append(packed)
    nset=P['nset'];nsheet2=nsheet+len(streams)
    cwb=[b for b in bl if b[0]==b'CWDH'];cmb=[b for b in bl if b[0]==b'CMAP']
    # New blocks (pointers patched after layout).
    cw_data=struct.pack('>HHI',first,first+len(codes)-1,0)+b''.join(widths)
    cw_block=bytearray(b'CWDH'+struct.pack('>I',0)+cw_data);cw_block.extend(bytes(-len(cw_block)%4));struct.pack_into('>I',cw_block,4,len(cw_block))
    if codes==list(range(codes[0],codes[-1]+1)):
        cm_data=struct.pack('>HHHHI',codes[0],codes[-1],0,0,0)+struct.pack('>H',first)
    else:
        cm_data=struct.pack('>HHHHI',codes[0],codes[-1],2,0,0)+struct.pack('>H',len(codes))+b''.join(struct.pack('>HH',c,first+i) for i,c in enumerate(codes))
    cm_block=bytearray(b'CMAP'+struct.pack('>I',0)+cm_data);cm_block.extend(bytes(-len(cm_block)%4));struct.pack_into('>I',cm_block,4,len(cm_block))
    # GLGR (sizes + use bits; new sheets/CWDH/CMAP used by every set; new CMAP is index 0).
    useS=[u+[1]*len(streams) for u in P['useS']];useC=[u+[1] for u in P['useC']];useM=[[1]+u for u in P['useM']]
    def pack(bitlist):
        out=[0]*((len(bitlist)+31)//32)
        for i,b in enumerate(bitlist):
            if b:out[i//32]|=1<<(31-i%32)
        return out
    sizeS=[len(s) for s in P['streams']]+[len(s) for s in streams]
    sizeC=[b[2] for b in cwb]+[len(cw_block)];sizeM=[len(cm_block)]+[b[2] for b in cmb]
    A=_align(14+2*nset,4)
    head=struct.pack('>IHHHHH',P['sheet_size'],P['gps'],nset,nsheet2,len(sizeC),len(sizeM))
    arrays=b''.join(struct.pack('>I',x) for x in sizeS+sizeC+sizeM)
    use=b''.join(struct.pack('>I',w) for u in useS for w in pack(u))+b''.join(struct.pack('>I',w) for u in useC for w in pack(u))+b''.join(struct.pack('>I',w) for u in useM for w in pack(u))
    names_rel=16+8+A+len(arrays)+len(use)              # new file offset of the name area
    old_names=P['names'];base=min(old_names)
    newnames=[o-base+names_rel for o in old_names]
    if max(newnames)>0xffff:raise ValueError('GLGR name offsets exceed u16')
    gdata=bytearray(head+struct.pack(f'>{nset}H',*newnames));gdata.extend(bytes(A-len(gdata)));gdata+=arrays+use+P['name_blob']
    glgr=b'GLGR'+struct.pack('>I',8+len(gdata))+bytes(gdata)
    if len(glgr)%4:raise ValueError('GLGR alignment')
    # Layout.
    finf_start=16+len(glgr);finf=bytearray(rfna[bl[1][1]:bl[1][1]+bl[1][2]])
    tglp_start=finf_start+len(finf);image=_align(tglp_start+32,32)
    tglp=bytearray(rfna[tp:tp+32]);tglp.extend(bytes(image-tglp_start-32))
    for s in P['streams']+streams:tglp+=struct.pack('>I',len(s))+s
    struct.pack_into('>H',tglp,16,nsheet2);struct.pack_into('>I',tglp,28,image);struct.pack_into('>I',tglp,4,len(tglp))
    cw_start=tglp_start+len(tglp);old_cw=[bytearray(rfna[p:p+s]) for _,p,s in cwb]
    pos=cw_start;cw_starts=[]
    for b in old_cw+[cw_block]:cw_starts.append(pos);pos+=len(b)
    cm_starts=[];cm_all=[cm_block]+[bytearray(rfna[p:p+s]) for _,p,s in cmb]
    for b in cm_all:cm_starts.append(pos);pos+=len(b)
    for i,b in enumerate(old_cw+[cw_block]):struct.pack_into('>I',b,12,cw_starts[i+1]+8 if i+1<len(cw_starts) else 0)
    for i,b in enumerate(cm_all):struct.pack_into('>I',b,16,cm_starts[i+1]+8 if i+1<len(cm_starts) else 0)
    struct.pack_into('>III',finf,16,tglp_start+8,cw_starts[0]+8,cm_starts[0]+8)
    body=glgr+bytes(finf)+bytes(tglp)+b''.join(bytes(b) for b in old_cw)+bytes(cw_block)+b''.join(bytes(b) for b in cm_all)
    out=bytearray(rfna[:16]+body);struct.pack_into('>I',out,8,len(out));struct.pack_into('>H',out,14,len(bl)+2)
    out=bytes(out);rec=check_rfna(out)
    for i,c in enumerate(codes):
        if find_glyph(out,c)!=first+i:raise ValueError('Hangul chain lookup failed')
    for c in list(mapping)[::37]:
        if find_glyph(out,c)!=find_glyph(rfna,c):raise ValueError('Original glyph lookup changed')
    record=dict(added_glyphs=len(codes),sheets_before=nsheet,sheets_after=nsheet2,glgr_preserved=True,
        hangul_cmap_first=True,cmap_method=0 if cm_data[4:6]==b'\0\0' else 2,source='console 43K shared wbf2',cell=[cw,ch],**rec)
    if exact:record.update(placement='nw4r cell window (1,1), bearing in CWDH',scale=round(f,4),first_appended_glyph=first,
        cx_layout=dict(bfs=layouts.count('bfs'),deadline=layouts.count('deadline')))
    return out,record


def glyph_ink_report(rfna,glyphs):
    """Decode the CX/I4 sheets and check each glyph's ink against nw4r's window.

    A glyph is drawn from sheet pixels [cellX+1, cellX+1+glyphWidth) x
    [cellY+1, cellY+1+cellHeight); ink in the border column/row or right of the
    glyph width is never drawn (clipped). Also flags empty cells, a glyph box
    wider than its advance (overlap) and ink outside the cell grid."""
    P=_parse_rfna(rfna);T=P['tglp'][2];cw,ch=T[0],T[1]
    fmt,cols,rows,sw,sh=struct.unpack_from('>5H',T,10);per=cols*rows
    W={}
    for kind,pos,size in P['blocks']:
        if kind!=b'CWDH':continue
        b,e,_=struct.unpack_from('>HHI',rfna,pos+8)
        for g in range(b,e+1):W[g]=struct.unpack_from('>bBb',rfna,pos+16+3*(g-b))
    sheets={};rep=dict(checked=0,clipped=[],empty=[],overlap=[],margin_ink_sheets=[])
    for g in glyphs:
        s=g//per
        if s not in sheets:
            px=_untile_i4(cx_huffman.decompress(P['streams'][s]),sw,sh);sheets[s]=px
            uw,uh=cols*(cw+1),rows*(ch+1)
            if any(px[y*sw+x] for y in range(sh) for x in range(uw,sw)) or any(px[y*sw:(y+1)*sw].count(0)!=sw for y in range(uh,sh)):
                rep['margin_ink_sheets'].append(s)
        px=sheets[s];item=g%per;x0=(item%cols)*(cw+1);y0=(item//cols)*(ch+1)
        left,gw,adv=W[g];rep['checked']+=1
        ink=[(x,y) for y in range(ch+1) for x in range(cw+1) if px[(y0+y)*sw+x0+x]]
        if not ink:rep['empty'].append(g);continue
        if any(x<1 or x>=1+gw or y<1 for x,y in ink):rep['clipped'].append(g)
        if left<0 or left+gw>adv:rep['overlap'].append(g)
    rep['ok']=not(rep['clipped'] or rep['empty'] or rep['overlap'] or rep['margin_ink_sheets'])
    return rep

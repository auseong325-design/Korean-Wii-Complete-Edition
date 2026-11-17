"""Inventory (and redraw helpers) for baked-text textures in the Photo Prints
Channel. The channel's user text is overwhelmingly live BRLYT text drawn with
the (now Hangul-capable) rodan font; a small set of TPLs carry baked Japanese
pixels — the product-name banners the WiiLink English patch itself replaces
(arc/timg/C_01_ItemName_*.tpl, C_01syozai_obi.tpl) plus the IMET banner/icon
wordmarks. This lists them (with a contact sheet for review) and offers a redraw
entry point via kwce.tpl + kwce.wbf_text. Evidence images are written under
workspace/private only.
"""
import sys
from pathlib import Path
from .channels import ROOT,ChannelArchive,load_library,sha256
from . import bspatch

# TPLs the WiiLink English patch rewrites in layout.arc = the baked-text set.
BAKED_TEXT_TPL=['arc/timg/C_01syozai_obi.tpl','arc/timg/C_01_ItemName_A4.tpl',
    'arc/timg/C_01_ItemName_digicame.tpl','arc/timg/C_01_ItemName_NameCard_Mii.tpl',
    'arc/timg/C_01_ItemName_NameCard_pic.tpl','arc/timg/C_01_ItemName_SQ.tpl']


def _layout(content2):
    load_library();from libWiiPy.archive import decompress_lz77
    return ChannelArchive(decompress_lz77(ChannelArchive(content2).get('layout.arc.LZ')))


def inventory(content2):
    from .tpl import decode
    from .channel_texture import texture_records
    arc=_layout(content2);rows=[]
    for name in sorted(arc.files):
        if not name.endswith('.tpl'):continue
        data=arc.get(name)
        try:recs=texture_records(data)
        except Exception:recs=[]
        rows.append(dict(name=name,textures=len(recs),
            formats=sorted({r['format'] for r in recs}),
            sizes=[f"{r['width']}x{r['height']}" for r in recs[:4]],
            baked_text=name in BAKED_TEXT_TPL))
    return rows


def contact_sheet(content2,out_path,names=None,max_side=1600):
    """Decode the baked-text TPLs into one tiled contact sheet for review."""
    load_library();from PIL import Image,ImageDraw
    from .tpl import decode
    arc=_layout(content2);names=names or BAKED_TEXT_TPL;tiles=[]
    for name in names:
        try:img=decode(arc.get(name),0).convert('RGBA')
        except Exception:continue
        tiles.append((name,img))
    if not tiles:raise ValueError('No baked-text textures decoded')
    pad=6;w=min(max_side,max(t[1].width for t in tiles)+pad*2)
    bg=Image.new('RGBA',(w,sum(min(t[1].height,220)+24 for t in tiles)+pad),(32,32,32,255))
    d=ImageDraw.Draw(bg);y=pad
    for name,img in tiles:
        h=min(img.height,220);d.text((pad,y),name,fill=(220,220,220,255));y+=16
        bg.alpha_composite(img.crop((0,0,min(img.width,w-pad*2),h)),(pad,y));y+=h+8
    out=Path(out_path);bg.save(out);return dict(tiles=[t[0] for t in tiles],path=str(out),size=list(bg.size))



# Korean product-name labels for the baked-text banners (rendered with the
# verified system Korean font, so no channel-font dependency).
PRODUCT_LABELS={
    'arc/timg/C_01_ItemName_A4.tpl':'Wii 포토북(스탠더드 타입)',
    'arc/timg/C_01_ItemName_digicame.tpl':'디지털 카메라 프린트',
    'arc/timg/C_01_ItemName_NameCard_Mii.tpl':'Wii 명함(Mii)',
    'arc/timg/C_01_ItemName_NameCard_pic.tpl':'Wii 명함(사진)',
    'arc/timg/C_01_ItemName_SQ.tpl':'Wii 포토북(스퀘어 타입)',
}


def _text_color(image):
    """Dominant saturated (non-white/near-black) colour in the original banner."""
    best=(60,180,230);count=0;hist={}
    for p in image.convert('RGB').getdata():
        r,g,b=p
        if max(r,g,b)-min(r,g,b)<40 or max(r,g,b)<60:continue
        hist[p]=hist.get(p,0)+1
    if hist:best=max(hist,key=hist.get)
    return best


def redraw_product_names(layout_bytes,exact=False):
    """Redraw the Korean product-name banners in the decompressed layout U8.

    Keeps each texture's format/size; renders the Korean label with the console
    Korean font, auto-fitting the width, in the banner's own text colour on a
    white background. exact=True (v10+) reads each system glyph from nw4r's real
    cell window (cellX+1, cellY+1), so no glyph loses its last ink column.
    Returns (bytes, record)."""
    load_library();from PIL import Image,ImageChops
    from .tpl import decode,encode
    from .channel_texture import texture_records
    from .channel_korean_font import korean_shared_fonts
    from .wbf_text import WiiFontRenderer
    from .photoprints_font import ExactCellRenderer
    fonts,_=korean_shared_fonts();renderer=(ExactCellRenderer if exact else WiiFontRenderer)(ChannelArchive(fonts).get('wbf2.brfna'))
    arc=ChannelArchive(layout_bytes);done=[]
    for name,label in PRODUCT_LABELS.items():
        if name not in arc.files:continue
        data=arc.get(name);rec=texture_records(data)[0];w,h=rec['width'],rec['height']
        original=decode(data,0).convert('RGB');color=_text_color(original)
        size=h-6
        while size>8 and renderer.line_width(label,size/renderer.height)>w-8:size-=1
        cov=Image.new('L',(w,h));renderer.render(label,size,cov,centre=(w/2,h/2))
        out=Image.new('RGBA',(w,h),(255,255,255,255))
        tint=Image.new('RGBA',(w,h),color+(255,));tint.putalpha(cov)
        out=Image.alpha_composite(out,tint)
        arc=ChannelArchive(arc.replace(name,encode(data,0,out)))
        done.append(dict(texture=name,label=label,size=[w,h],px=size))
    return arc.data,dict(redrawn=done,skipped_no_text=['arc/timg/C_01syozai_obi.tpl'])

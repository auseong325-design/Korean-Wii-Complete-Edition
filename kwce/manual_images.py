"""Korean versions of channel manual images (diagrams and common buttons).

Diagram images keep their original size and frame art. Each embedded English
screenshot is replaced by a local Korean Dolphin capture stretched into the
same slot, the original red highlight pixels are re-applied on top, and label
boxes are refilled with their own sampled colour before Korean text is drawn.
Captures are private local evidence; generated images stay in ignored builds.
"""
import io
from .channels import ROOT,load_library

FONT=ROOT/'workspace/channels/forecast/references/NotoSansKR.ttf'

def _font(size,weight=500):
    from PIL import ImageFont
    font=ImageFont.truetype(str(FONT),size)
    try:font.set_variation_by_axes([weight])
    except Exception:pass
    return font

def _fit(draw,text,box,max_size,weight):
    x0,y0,x1,y1=box
    for size in range(max_size,7,-1):
        font=_font(size,weight);l,t,r,b=draw.multiline_textbbox((0,0),text,font=font,spacing=max(1,size//6),align='center')
        if r-l<=x1-x0-4 and b-t<=y1-y0-2:return font,(l,t,r,b),max(1,size//6)
    raise ValueError(f'Korean label does not fit: {text!r}')

def _label(image,box,text,fill,color,max_size,weight):
    from PIL import ImageDraw
    draw=ImageDraw.Draw(image);x0,y0,x1,y1=box
    if fill=='row':
        # Keep vertical gradients: every row takes the colour at the box's left edge.
        for y in range(y0,y1):draw.line([(x0,y),(x1-1,y)],fill=image.getpixel((max(0,x0-1),y)))
    elif fill is not None:
        draw.rectangle([x0,y0,x1-1,y1-1],fill=tuple(fill) if isinstance(fill,list)else image.getpixel(tuple(fill['sample'])))
    font,(l,t,r,b),spacing=_fit(draw,text,box,max_size,weight)
    draw.multiline_text((x0+(x1-x0-(r-l))/2-l,y0+(y1-y0-(b-t))/2-t),text,font=font,fill=tuple(color),spacing=spacing,align='center')

def _is_red(pixel):
    r,g,b=pixel[:3];return r>190 and g<70 and b<70

def compose(original,spec,captures):
    load_library();from PIL import Image
    source=Image.open(io.BytesIO(original));fmt=source.format;base=source.convert('RGB');image=base.copy()
    # A replaced screenshot can leave the edge of an old red oval outside
    # its slot. Explicit boxes remove just those red pixels before pasting;
    # use the nearest original non-red neighbour to retain the frame gradient.
    for x0,y0,x1,y1 in spec.get('remove_old_red',[]):
        if not 0<=x0<x1<=base.width or not 0<=y0<y1<=base.height:raise ValueError('Old callout cleanup bounds')
        for y in range(y0,y1):
            for x in range(x0,x1):
                r,g,b=base.getpixel((x,y))
                # Include the pale antialiasing fringe of the old red oval.
                if not(r>150 and r>max(g,b)+15):continue
                replacement=None
                for radius in range(1,17):
                    for nx,ny in [(x,y-radius),(x,y+radius),(x-radius,y),(x+radius,y)]:
                        if 0<=nx<base.width and 0<=ny<base.height:
                            nr,ng,nb=base.getpixel((nx,ny))
                            if not(nr>150 and nr>max(ng,nb)+15):
                                replacement=(nr,ng,nb);break
                    if replacement is not None:break
                if replacement is None:raise ValueError('Old callout has no nearby background')
                image.putpixel((x,y),replacement)
    for shot in spec.get('shots',[]):
        x0,y0,x1,y1=shot['box'];capture=Image.open(captures/shot['capture']).convert('RGB')
        # Dolphin's on-screen FPS counter sits in the top-right corner of the captures.
        w,h=capture.size;overlay=shot.get('overlay_box',[0.925,0,1,0.045]);mx,my,ex,ey=[int(v*([w,h,w,h][i]))for i,v in enumerate(overlay)]
        if not 0<mx<ex<=w or not 0<=my<ey<=h:raise ValueError('Capture overlay bounds')
        from PIL import ImageDraw
        cover=ImageDraw.Draw(capture)
        if shot.get('overlay_fill')=='mirror':
            # Reflect the pixels just left of the counter so the tiled background continues.
            if 2*mx-ex<0:raise ValueError('Capture overlay mirror bounds')
            for y in range(my,ey):
                for x in range(mx,ex):capture.putpixel((x,y),capture.getpixel((2*mx-1-x,y)))
        else:
            for y in range(my,ey):cover.line([(mx,y),(ex-1,y)],fill=capture.getpixel((mx-2,y)))
        if 'crop' in shot:
            w,h=capture.size;c=shot['crop'];capture=capture.crop((int(c[0]*w),int(c[1]*h),int(c[2]*w),int(c[3]*h)))
        image.paste(capture.resize((x1-x0,y1-y0),Image.LANCZOS),(x0,y0))
        # Re-apply the original red rings and callout lines that crossed the slot.
        if shot.get('keep_red',True):
            # red_exclude: boxes of red screen content (not callouts) to leave out.
            excluded=shot.get('red_exclude',[])
            for y in range(y0,y1):
                for x in range(x0,x1):
                    p=base.getpixel((x,y))
                    if _is_red(p)and not any(a<=x<c and b<=y<d for a,b,c,d in excluded):image.putpixel((x,y),p)
        from PIL import ImageDraw
        ring=ImageDraw.Draw(image)
        for r in shot.get('rings',[]):
            ring.rounded_rectangle(r,radius=8,outline=(255,255,255),width=4)
            ring.rounded_rectangle(r,radius=8,outline=(230,20,20),width=2)
        # Redrawn callout leaders for controls that moved in the Korean capture.
        for points in shot.get('lines',[]):ring.line([tuple(p)for p in points],fill=(230,20,20),width=2)
        for x,y in shot.get('dots',[]):ring.ellipse([x-3,y-3,x+3,y+3],fill=(230,20,20),outline=(255,255,255))
    for label in spec.get('labels',[]):
        _label(image,label['box'],label['text'],label.get('fill','row'),label.get('color',[255,255,255]),label.get('size',20),label.get('weight',400))
    out=io.BytesIO()
    if fmt=='GIF':_save_gif(image,source,out)
    elif fmt=='PNG' and spec.get('palette_colors'):
        colors=spec['palette_colors']
        if not isinstance(colors,int)or not 16<=colors<=256:raise ValueError('Manual palette bounds')
        image.quantize(colors=colors,method=Image.Quantize.MEDIANCUT).save(out,'PNG',optimize=True)
    else:image.save(out,fmt)
    return out.getvalue()

def _save_gif(image,source,out):
    # The Wii browser showed light greys of a re-quantized palette as white;
    # reusing the original palette keeps the original colour indices.
    from PIL import Image
    image.quantize(palette=source.convert('P'),dither=Image.Dither.FLOYDSTEINBERG).save(out,'GIF',version='GIF89a')

def text_image(original,spec):
    """Redraw a text-only image (for example a copyright line) on its own background."""
    load_library();from PIL import Image,ImageDraw
    source=Image.open(io.BytesIO(original));fmt=source.format;image=source.convert('RGB')
    bg=image.getpixel(tuple(spec.get('sample',[1,1])));draw=ImageDraw.Draw(image);draw.rectangle([0,0,image.width,image.height],fill=bg)
    _label(image,spec.get('box',[4,2,image.width-4,image.height-2]),spec['text'],None,spec.get('color',[80,80,80]),spec.get('size',14),spec.get('weight',700))
    out=io.BytesIO()
    if fmt=='GIF':_save_gif(image,source,out)
    else:image.save(out,fmt)
    return out.getvalue()

def padded_button(original,korean,align='right'):
    """Fit a Korean button into the English button's canvas, keeping the edge art."""
    load_library();from PIL import Image
    base=Image.open(io.BytesIO(original));fmt=base.format;canvas=base.convert('RGBA');k=Image.open(io.BytesIO(korean)).convert('RGBA')
    if k.size==canvas.size:return korean
    # Trim at most 2 columns of the Korean edge art opposite the alignment edge.
    if k.height==canvas.height and 0<k.width-canvas.width<=2:
        k=k.crop((k.width-canvas.width,0,k.width,k.height)if align=='right'else(0,0,canvas.width,k.height))
    if k.height!=canvas.height or k.width>canvas.width:raise ValueError('Korean button size mismatch')
    canvas.alpha_composite(k,(canvas.width-k.width if align=='right'else 0,0))
    out=io.BytesIO();canvas.save(out,fmt);return out.getvalue()

"""Balanced Korean suffixes in native Wii logo panes, including their motions."""
import struct
from .channels import layout_sections,rebuild_layout,load_library
from .disk_dvd_anim import _contents
from .wiiroom_visual import _font

# x/y translation, actual quad size; the native Wii textures remain untouched.
TITLE={'Pic_Logo_No':(75.,-2.,64.,64.),'Pic_Logo_Ma':(145.,-2.,64.,64.)}
BANNER={'W':(-115.25,-33.5,89.,63.),'Rect_a':(-48.5,-34.,16.,45.),
        'Rect_b':(-22.5,-34.,16.,45.),'No':(40.,-35.,80.,80.),'Ma':(132.,-35.,80.,80.)}
ICON={'Pic_W':(-29.,27.,21.,15.),'Pic_I1':(-15.,27.5,6.,16.),
      'Pic_I2':(-9.,27.5,6.,16.),'Pic_No':(8.5,27.5,18.,18.),'Pic_Ma':(32.,27.5,18.,18.)}
# Revision 56+ (hardware report 2026-10-29: 'Wii 의 방' read as three words). Measured ink gaps in
# build-v55: banner i->의 19.4 vs i->i 12.0, 의->방 34.0; icon I->의 7.4 vs I->I 1.5, 의->방 10.3.
# 의 now sits at Wii's own letter spacing (banner 11.0, icon 2.6), one word space before 방
# (banner 27.0, icon 5.8), and the whole wordmark is re-centred (sizes and y unchanged).
BANNER_V56={'W':(-112.05,-33.5,89.,63.),'Rect_a':(-45.3,-34.,16.,45.),
            'Rect_b':(-19.3,-34.,16.,45.),'No':(34.8,-35.,80.,80.),'Ma':(119.8,-35.,80.,80.)}
ICON_V56={'Pic_W':(-24.7,27.,21.,15.),'Pic_I1':(-10.7,27.5,6.,16.),
          'Pic_I2':(-4.7,27.5,6.,16.),'Pic_No':(7.9,27.5,18.,18.),'Pic_Ma':(26.9,27.5,18.,18.)}

def letter_mask(letter,size,canvas=64):
    """One font size and baseline for both Hangul glyphs; no per-glyph fitting."""
    load_library();from PIL import Image,ImageDraw
    scale=4;n=round(canvas*scale);stroke=round(canvas*.018*scale)
    font=_font(round(canvas*.94*scale));boxes=[font.getbbox(c,stroke_width=stroke)for c in ('의','방')]
    top=min(b[1]for b in boxes);bottom=max(b[3]for b in boxes)
    b=boxes[0 if letter=='의'else 1];im=Image.new('L',(n,n))
    ImageDraw.Draw(im).text(((n-(b[2]-b[0]))/2-b[0],(n-(bottom-top))/2-top),letter,
                            font=font,fill=255,stroke_width=stroke,stroke_fill=255)
    return im.resize(size,Image.Resampling.LANCZOS)

def letter_image(letter,size,inverted=False):
    from PIL import Image,ImageChops
    mask=letter_mask(letter,size)
    if inverted:mask=ImageChops.invert(mask)
    return Image.merge('RGBA',(mask,mask,mask,mask))

def geometry(ar,targets):
    """Map animated translation/size values by the same affine change as BRLYT.

    Frame times, slopes of offsets, alpha fades, and rotations keep their native
    timing. A width/height track also scales its Hermite tangent.
    """
    transforms={};layouts=[];changed_keys=0
    for path in ar.files:
        if not path.endswith('.brlyt'):continue
        data=ar.get(path);sections=layout_sections(data);changed=False
        for i,s in enumerate(sections):
            if s[:4]!=b'pic1':continue
            name=s[12:28].split(b'\0')[0].decode('ascii')
            if name not in targets:continue
            old=struct.unpack_from('>10f',s,36);x,y,w,h=targets[name]
            rule={0:(1.,x-old[0]),1:(1.,y-old[1]),8:(w/old[8],0.),9:(h/old[9],0.)}
            if name in transforms and transforms[name]!=rule:raise ValueError('Inconsistent logo copies')
            transforms[name]=rule;b=bytearray(s)
            struct.pack_into('>ff',b,36,x,y);struct.pack_into('>ff',b,68,w,h)
            if name.startswith('Pic_Logo_'):struct.pack_into('>ff',b,60,1.,1.)
            sections[i]=bytes(b);changed=True
        if changed:ar=type(ar)(ar.replace(path,rebuild_layout(data,sections)));layouts.append(path)
    if set(transforms)!=set(targets):raise ValueError('Native logo pane coverage differs')
    for path in ar.files:
        if not path.endswith('.brlan'):continue
        raw=ar.get(path);out=bytearray(raw)
        for name,material,tags in _contents(raw):
            if material or name not in transforms:continue
            for at,kind,tracks in tags:
                if kind!=b'RLPA':continue
                for te,target,curve,keys in tracks:
                    if target not in transforms[name]:continue
                    factor,offset=transforms[name][target]
                    if factor==1 and offset==0:continue
                    if curve!=2:raise ValueError('Unexpected discrete logo transform')
                    for key in keys:
                        frame,value,tangent=struct.unpack_from('>fff',raw,key)
                        struct.pack_into('>ff',out,key+4,value*factor+offset,tangent*factor);changed_keys+=1
        if out!=raw:ar=type(ar)(ar.replace(path,bytes(out)))
    return ar,dict(layouts=layouts,animated_keys=changed_keys,shared_hangul_baseline=True)

def transition_wordmark(native):
    """Keep the native Wii prefix, followed by the same balanced Korean suffix."""
    load_library();from PIL import Image
    if native.size!=(324,74):raise ValueError('Native transition wordmark dimensions')
    im=Image.new('RGBA',native.size);im.paste(native.crop((0,0,145,74)),(0,0))
    for c,x in [('의',159),('방',245)]:
        mask=letter_mask(c,(70,70));im.paste((255,255,255,255),(x,2,x+70,72),mask)
    return im

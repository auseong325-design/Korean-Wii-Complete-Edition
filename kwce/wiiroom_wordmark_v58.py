"""Revision 58+: geometric Hangul '의'/'방' drawn to the native Wii logo's metrics.

Native measurements at 50% coverage (the Japanese original and WiiLink English
share these textures; units are each layout's own):
  banner  W ink 61 tall on baseline -32.5, i stem 13 wide, i-to-i gap 13;
          Japanese 'の' strokes 9, '間' verticals 9 / horizontals 6-7, letter gaps 12.
  icon    W ink 15 tall, i stem 3, i-to-i gap 3.
  title   W ink 58.5 tall, i stem 12, i-to-i gap 13.
  wipe    (one 324x74 texture) W ink 66 tall, i stem 15 px, i-to-i gap 13 px.
Build v57 drew Round Gothic B: round stroke ends, ink 4-11 units above the W
and a 27-unit word gap before '방' (hardware photos IMG_5612/5619). Here each
syllable is built from straight bars and rings: one height with W (1.6% optical
overshoot), stroke weights at ~80% of the i stem, and the Japanese letter gap
(0.92 x the i-to-i gap) on both sides of '의'. Native Wii textures, frame
timing and every non-logo pane stay untouched; native panes only move in x so
the whole wordmark (and the title's table mark) is centred again.
"""
import struct
from .channels import layout_sections,rebuild_layout,load_library
from .disk_dvd_anim import _contents

# Stroke weights as fractions of the syllable height.
WEIGHTS={'light':dict(stem=.15,bar=.125,ring=.14),
         'medium':dict(stem=.17,bar=.145,ring=.16),
         'heavy':dict(stem=.20,bar=.17,ring=.19)}
WEIGHT='medium'
WIDTH={'의':.95,'방':1.}       # ink width / syllable height
HEIGHT=1.016                 # syllable height / native W ink height
GAP=.92                      # Hangul letter gap / native i-to-i gap

def _parts(letter,w,k):
    """Shapes in syllable units (x 0..w, y 0..1 top-down)."""
    sv,sh,so=k['stem'],k['bar'],k['ring']
    if letter=='의':
        ex=w-sv-.10                                   # ㅡ ends one gap before ㅣ
        d=.60;cx=ex/2                                 # ㅇ: circle over ㅡ
        return [('rect',w-sv,0.,w,1.),                # ㅣ, full height like the i stem
                ('ring',cx-d/2,-.008,cx+d/2,d-.008,so,so),
                ('rect',0.,.74,ex,.74+sh)]
    if letter=='방':
        bv=sv*.92;bh=sh*.86                           # 방 is denser: lighter ㅂ/ㅏ
        bw=.50;bt=.50                                 # ㅂ box
        ax=.665                                       # ㅏ stem x
        return [('rect',0.,0.,bv,bt),('rect',bw-bv,0.,bw,bt),
                ('rect',0.,.20,bw,.20+bh),('rect',0.,bt-bh,bw,bt),
                ('rect',ax,0.,ax+bv,.565),('rect',ax+bv-.01,.215,w,.215+bh),
                ('ring',.12,.625,w-.12,1.008,so*.92,so*.74)]
    raise ValueError(f'No geometric design for {letter!r}')

def glyph_mask(letter,quad,ink,size,weight=None,supersample=12):
    """Coverage mask of `size` px for a quad of `quad` units; the syllable fills the
    height of ink box `ink` (x0,y0,x1,y1, units, top-down) and is centred in its width."""
    load_library();from PIL import Image,ImageDraw,ImageChops
    k=WEIGHTS[weight or WEIGHT];x0,y0,x1,y1=ink;h=y1-y0;w=WIDTH[letter]
    s=supersample*max(1.,size[0]/quad[0],size[1]/quad[1])
    W,H=round(quad[0]*s),round(quad[1]*s);out=Image.new('L',(W,H))
    left=x0+((x1-x0)-w*h)/2
    px=lambda u:(left+u*h)*s;py=lambda v:(y0+v*h)*s
    for part in _parts(letter,w,k):
        layer=Image.new('L',(W,H));dr=ImageDraw.Draw(layer)
        if part[0]=='rect':
            _,a,b,c,d=part;box=[px(a),py(b),px(c),py(d)]
            dr.rounded_rectangle(box,radius=.22*min(box[2]-box[0],box[3]-box[1]),fill=255)
        else:
            _,a,b,c,d,tx,ty=part
            dr.ellipse([px(a),py(b),px(c),py(d)],fill=255)
            dr.ellipse([px(a+tx),py(b+ty),px(c-tx),py(d-ty)],fill=0)
        out=ImageChops.lighter(out,layer)
    return out.resize(size,Image.Resampling.BOX)

def letter_texture(letter,quad,margin,size,inverted=False,weight=None):
    """RGBA texture of TPL `size` whose `quad` shows the syllable inside `margin` units."""
    load_library();from PIL import Image,ImageChops
    mask=glyph_mask(letter,quad,(margin,margin,quad[0]-margin,quad[1]-margin),size,weight)
    if inverted:mask=ImageChops.invert(mask)
    return Image.merge('RGBA',(mask,mask,mask,mask))

def run(cap,stem_gap,start,letters=('의','방')):
    """(height, ink x spans) of the two syllables after the native ink edge `start`."""
    hk=HEIGHT*cap;g=GAP*stem_gap;x=start+g;spans=[]
    for c in letters:
        w=WIDTH[c]*hk;spans.append((x,x+w));x+=w+g
    return hk,spans

# ---- layout geometry -------------------------------------------------------
def _origin(o):
    return (o%3)/2.,(o//3)/2.          # x: 0 left,.5 centre,1 right; y: 0 top,.5 centre,1 bottom

def _pane(ar,name):
    """Displayed quad (left, bottom, width, height) of a pic1 pane in its parent's units."""
    for path in ar.files:
        if not path.endswith('.brlyt'):continue
        for s in layout_sections(ar.get(path)):
            if s[:4]==b'pic1'and s[12:28].split(b'\0')[0].decode('ascii')==name:
                x,y=struct.unpack_from('>ff',s,36);sx,sy=struct.unpack_from('>ff',s,60);w,h=struct.unpack_from('>ff',s,68)
                fx,fy=_origin(s[9]);w*=sx;h*=sy
                return x-fx*w,y-(1-fy)*h,w,h
    raise ValueError(f'Logo pane {name} missing')

def _pan_x(ar,name):
    for path in ar.files:
        if not path.endswith('.brlyt'):continue
        for s in layout_sections(ar.get(path)):
            if s[:4]==b'pan1'and s[12:28].split(b'\0')[0].decode('ascii')==name:return struct.unpack_from('>f',s,36)[0]
    raise ValueError(f'Logo null pane {name} missing')

def place(ar,targets,shift=None):
    """Move logo panes; remap their translation/size animation keys by the same affine change.

    targets: Hangul pane name -> displayed quad (left, bottom, width, height), scale 1;
    shift:   native pane name -> dx (size, scale, y and timing unchanged).
    """
    shift=dict(shift or {});rules={};layouts=[];changed_keys=0
    for path in ar.files:
        if not path.endswith('.brlyt'):continue
        data=ar.get(path);sections=layout_sections(data);changed=False
        for i,s in enumerate(sections):
            if s[:4]!=b'pic1':continue
            name=s[12:28].split(b'\0')[0].decode('ascii')
            if name not in targets and name not in shift:continue
            old=struct.unpack_from('>10f',s,36);b=bytearray(s)
            if name in targets:
                left,bottom,w,h=targets[name];fx,fy=_origin(s[9])
                x=left+fx*w;y=bottom+(1-fy)*h               # BRLYT y grows upward
                rule={0:(1.,x-old[0]),1:(1.,y-old[1]),8:(w/old[8],0.),9:(h/old[9],0.)}
                struct.pack_into('>ff',b,36,x,y);struct.pack_into('>ff',b,60,1.,1.);struct.pack_into('>ff',b,68,w,h)
            else:
                rule={0:(1.,shift[name])};struct.pack_into('>f',b,36,old[0]+shift[name])
            if name in rules and rules[name]!=rule:raise ValueError('Inconsistent logo copies')
            rules[name]=rule;sections[i]=bytes(b);changed=True
        if changed:ar=type(ar)(ar.replace(path,rebuild_layout(data,sections)));layouts.append(path)
    if set(rules)!=set(targets)|set(shift):raise ValueError('Native logo pane coverage differs')
    for path in ar.files:
        if not path.endswith('.brlan'):continue
        raw=ar.get(path);out=bytearray(raw)
        for name,material,tags in _contents(raw):
            if material or name not in rules:continue
            for at,kind,tracks in tags:
                if kind!=b'RLPA':continue
                for te,target,curve,keys in tracks:
                    if target not in rules[name]:continue
                    factor,offset=rules[name][target]
                    if factor==1 and offset==0:continue
                    if curve!=2:raise ValueError('Unexpected discrete logo transform')
                    for key in keys:
                        frame,value,tangent=struct.unpack_from('>fff',raw,key)
                        struct.pack_into('>ff',out,key+4,value*factor+offset,tangent*factor);changed_keys+=1
        if out!=raw:ar=type(ar)(ar.replace(path,bytes(out)))
    return ar,dict(layouts=layouts,animated_keys=changed_keys)

# Native ink inside each native quad, measured from its texture at 50% coverage:
# (x0, x1, y0, y1) as fractions of the displayed quad, y upward from its bottom.
INK={'banner':{'W':(0/89,87/89,1/63,62/63),'i':(2/16,15/16,1/45,43/45)},
     'icon':{'W':(0.,1.,0.,1.),'i':(2/8,6/8,0.,15/23)},
     'title':{'W':(0.,1.,0.,1.),'i':(2/22,20/22,0.,59/90)}}
PANES={'banner':('W','Rect_a','Rect_b','No','Ma'),
       'icon':('Pic_W','Pic_I1','Pic_I2','Pic_No','Pic_Ma'),
       'title':('Pic_Logo_W','Pic_Logo_I1','Pic_Logo_I2','Pic_Logo_No','Pic_Logo_Ma')}
MARGIN={'banner':2.,'icon':.5,'title':2.}
TITLE_MARK=('Pic_Logo_Mark',-160.)   # final x of the table mark in Title_Scene_Logo.brlan (checked)

def _ink(rect,f):
    left,bottom,w,h=rect;return left+f[0]*w,left+f[1]*w,bottom+f[2]*h,bottom+f[3]*h

def wordmark(ar,kind):
    """Place geometric Hangul after the native 'Wii' and centre the run; returns (archive, record)."""
    names=PANES[kind];ink=INK[kind];m=MARGIN[kind]
    W=_ink(_pane(ar,names[0]),ink['W']);i1=_ink(_pane(ar,names[1]),ink['i']);i2=_ink(_pane(ar,names[2]),ink['i'])
    cap=W[3]-W[2];hk,spans=run(cap,i2[0]-i1[1],i2[1]);bottom=(W[2]+W[3])/2-hk/2
    left=W[0];right=spans[-1][1];shift_names=list(names[:3])
    if kind=='title':
        mark,final_x=TITLE_MARK;mw=_pane(ar,mark)[2]
        if _anim_last(ar,mark,0)!=final_x:raise ValueError('Title mark animation changed')
        left=final_x-mw/2;shift_names.append(mark)
        dx=-(_pan_x(ar,'Loc_Logo')+(left+right)/2)
    else:dx=-(left+right)/2
    targets={n:(a+dx-m,bottom-m,(b-a)+2*m,hk+2*m)for n,(a,b)in zip(names[3:],spans)}
    ar,record=place(ar,targets,{n:dx for n in shift_names})
    record.update(kind=kind,weight=WEIGHT,cap_height=round(cap,3),hangul_height=round(hk,3),
                  letter_gap=round(GAP*(i2[0]-i1[1]),3),centre_shift=round(dx,3),
                  quads={n:[round(v,3)for v in t]for n,t in targets.items()})
    return ar,record,targets

def _anim_last(ar,pane,target):
    for path in ar.files:
        if not path.endswith('_Logo.brlan'):continue
        raw=ar.get(path)
        for name,material,tags in _contents(raw):
            if material or name!=pane:continue
            for at,kind,tracks in tags:
                if kind!=b'RLPA':continue
                for te,t,curve,keys in tracks:
                    if t==target:return round(struct.unpack_from('>f',raw,keys[-1]+4)[0],3)
    return None

def transition_wordmark(native,weight=None):
    """324x74 wipe texture: native 'Wii' pixels plus geometric '의방', centred."""
    load_library();from PIL import Image,ImageChops
    if native.size!=(324,74):raise ValueError('Native transition wordmark dimensions')
    # Native ink (px): W 0..93 x 6..72, i stems 100..115 / 128..143 (i-to-i gap 13).
    hk,spans=run(66.,13.,143.);dx=round((324-spans[-1][1])/2)
    im=Image.new('RGBA',native.size);im.paste(native.crop((0,0,146,74)),(dx,0))
    top=(6+72)/2-hk/2;mask=Image.new('L',native.size)
    for c,(a,b) in zip(('의','방'),spans):
        mask=ImageChops.lighter(mask,glyph_mask(c,native.size,(a+dx,top,b+dx,top+hk),native.size,weight))
    im.paste((255,255,255,255),(0,0),mask)
    return im,dict(height=round(hk,2),centre_shift=dx,spans=[[round(a+dx,2),round(b+dx,2)]for a,b in spans])

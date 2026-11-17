"""Revision 58+: Korean room weather board (g3d/Weather/Weather_02.lex, TEX0 W_Header.01).

The wall board in the room (RC5 hardware photo IMG_5620) is this channel texture,
not server data. Japanese original: 'これからの天気 / Supported by ウェザーニュース /
きょう あす あさって'; WiiLink English: 'Weather Forecast / Supported by weathernews /
Today Tomorrow Week'. The executable names the model g3d::screen::WeatherPanelThreeDays,
so the third column is the day after tomorrow ('모레'), not a week.
The flat band/body colours and the 373x80 RGB5A3 format stay; text sits on the
Japanese column centres; all four mip levels are regenerated and the file is
re-encoded with the same LZ10 container. No other model data changes.
"""
import struct
from .channels import ChannelArchive,load_library
from .wiiroom_formats import compress_lz10_optimal
from . import tpl

PATH='g3d/Weather/Weather_02.lex'
NAME='W_Header.01'
BAND=(49,189,238,255);BODY=(255,255,255,255)
HEADER='날씨 예보';CREDIT='웨더뉴스 제공'
LABELS=(('오늘',63),('내일',188),('모레',313))   # Japanese column centres (px)

def _tex0(d):
    """(offset, width, height, format, levels) of the single named TEX0."""
    found=[];pos=0
    while True:
        at=d.find(b'TEX0',pos)
        if at<0:break
        pos=at+4;size=struct.unpack_from('>I',d,at+4)[0];name_at=struct.unpack_from('>I',d,at+20)[0]
        if not(64<size and at+size<=len(d)and 0<at+name_at<len(d)):continue
        if d[at+name_at:].split(b'\0')[0]==NAME.encode():
            w,h,fmt,levels=struct.unpack_from('>HHII',d,at+28);found.append((at,w,h,fmt,levels,size))
    if len(found)!=1:raise ValueError('Weather header texture identity')
    return found[0]

def _fake(w,h,fmt,pixels):
    head=bytearray(64);struct.pack_into('>III',head,0,0x0020af30,1,12);struct.pack_into('>II',head,12,20,0)
    struct.pack_into('>HHII',head,20,h,w,fmt,64);return bytes(head)+pixels

def _text(scale,text,height):
    """Korean shared-font face whose ink of `text` is `height` px tall at `scale`x (font, bbox)."""
    from .wiiroom_visual import _font
    from PIL import Image,ImageDraw
    probe=ImageDraw.Draw(Image.new('L',(1,1)))
    for px in range(2*scale*height,scale,-1):
        f=_font(px);b=probe.textbbox((0,0),text,font=f)
        if b[3]-b[1]<=scale*height:return f,b
    raise ValueError('Weather text does not fit')

def _words(dr,text,font,x,align,fill,top=None,bottom=None,band=None,gap=.3):
    """Draw words on one baseline with `gap` x ink height between them (the font's space is wide)."""
    words=text.split(' ');boxes=[dr.textbbox((0,0),w,font=font)for w in words]
    t=min(b[1]for b in boxes);btm=max(b[3]for b in boxes);g=gap*(btm-t)
    total=sum(b[2]-b[0]for b in boxes)+g*(len(words)-1)
    x={'left':x,'right':x-total,'centre':x-total/2}[align]
    y=(band-(btm-t))/2-t if band else bottom-btm
    for w,b in zip(words,boxes):
        dr.text((x-b[0],y),w,font=font,fill=fill);x+=b[2]-b[0]+g

def board(original):
    """Korean 373x80 board image drawn over the original flat colours."""
    load_library();from PIL import Image,ImageDraw
    w,h=original.size;S=4
    if (w,h)!=(373,80)or original.getpixel((2,2))!=BAND or original.getpixel((2,77))!=BODY:raise ValueError('Weather header layout differs')
    big=Image.new('RGBA',(w*S,h*S),BODY);ImageDraw.Draw(big).rectangle((0,0,w*S-1,37*S-1),fill=BAND)
    dr=ImageDraw.Draw(big)
    f,_=_text(S,HEADER,21);_words(dr,HEADER,f,9*S,'left',BODY,band=37*S)
    f,_=_text(S,CREDIT,11);_words(dr,CREDIT,f,364*S,'right',BODY,bottom=32*S)
    for text,cx in LABELS:
        f,_=_text(S,text,21);_words(dr,text,f,cx*S,'centre',BAND,bottom=69*S)
    return big.resize((w,h),Image.Resampling.BOX)

def korean_weather_board(content):
    """Return (content bytes, record) with the Korean weather header texture."""
    load_library();from libWiiPy.archive import decompress_lz77
    from PIL import Image
    a=ChannelArchive(content);raw=a.get(PATH)
    if raw[:1]!=b'\x10':raise ValueError('Expected LZ10 weather model')
    d=bytearray(decompress_lz77(raw));at,w,h,fmt,levels,size=_tex0(d)
    if (w,h,fmt,levels)!=(373,80,5,4):raise ValueError('Unexpected weather header TEX0')
    off=at+struct.unpack_from('>I',d,at+16)[0];n0=tpl.data_size(fmt,w,h)
    image=board(tpl.decode(_fake(w,h,fmt,bytes(d[off:off+n0])),0));pos=off
    for k in range(levels):
        lw,lh=max(1,w>>k),max(1,h>>k);n=tpl.data_size(fmt,lw,lh)
        level=image if k==0 else image.resize((lw,lh),Image.Resampling.BOX)
        d[pos:pos+n]=tpl.encode(_fake(lw,lh,fmt,bytes(d[pos:pos+n])),0,level)[64:];pos+=n
    if pos>at+size:raise ValueError('Weather header mip chain exceeds TEX0')
    packed=compress_lz10_optimal(bytes(d))
    if decompress_lz77(packed)!=bytes(d):raise ValueError('Weather model LZ10 roundtrip')
    a=ChannelArchive(a.replace(PATH,packed))
    return a.compact(),dict(file=PATH,texture=NAME,header=HEADER,credit=CREDIT,labels=[t for t,_ in LABELS],
                            mip_levels=levels,format='RGB5A3',compressed_size=len(packed),original_compressed_size=len(raw))

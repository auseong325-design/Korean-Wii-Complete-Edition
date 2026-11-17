"""General GX texture (TPL) decode/encode for local channel image localization.

Supports I4, I8, IA4, IA8, RGB565, RGB5A3, RGBA8 and CMPR. Encoding keeps the
original format, size and offset so archive layout is unchanged; CMPR uses a
simple per-block min/max endpoint fit.
"""
import struct
from .channel_texture import texture_records

BLOCK={0:(8,8,4),1:(8,4,8),2:(8,4,8),3:(4,4,16),4:(4,4,16),5:(4,4,16),6:(4,4,32),14:(8,8,4)}

def data_size(fmt,w,h):
    bw,bh,bpp=BLOCK[fmt];return((w+bw-1)//bw)*((h+bh-1)//bh)*bw*bh*bpp//8

def _rgb565(v):return((v>>11)*255//31,((v>>5)&63)*255//63,(v&31)*255//31)
def _rgb5a3(v):
    if v&0x8000:return((v>>10&31)*255//31,(v>>5&31)*255//31,(v&31)*255//31,255)
    return((v>>8&15)*17,(v>>4&15)*17,(v&15)*17,(v>>12&7)*255//7)

def decode(data,index):
    from .channels import load_library
    load_library();from PIL import Image
    r=texture_records(data)[index];w,h,fmt,at=r['width'],r['height'],r['format'],r['offset']
    if fmt not in BLOCK:raise ValueError(f'Unsupported texture format {fmt}')
    px=[(0,0,0,0)]*(w*h);bw,bh,_=BLOCK[fmt];pos=at
    def put(x,y,c):
        if x<w and y<h:px[y*w+x]=c
    for by in range(0,h,bh):
        for bx in range(0,w,bw):
            if fmt==14:
                for sub in range(4):
                    sx,sy=bx+(sub%2)*4,by+(sub//2)*4
                    c0,c1=struct.unpack_from('>HH',data,pos);bits=struct.unpack_from('>I',data,pos+4)[0];pos+=8
                    a,b=_rgb565(c0),_rgb565(c1)
                    if c0>c1:pal=[a+(255,),b+(255,),tuple((2*x+y)//3 for x,y in zip(a,b))+(255,),tuple((x+2*y)//3 for x,y in zip(a,b))+(255,)]
                    else:pal=[a+(255,),b+(255,),tuple((x+y)//2 for x,y in zip(a,b))+(255,),(0,0,0,0)]
                    for i in range(16):put(sx+i%4,sy+i//4,pal[(bits>>(30-2*i))&3])
                continue
            if fmt==6:
                ar=data[pos:pos+32];gb=data[pos+32:pos+64];pos+=64
                for i in range(16):put(bx+i%4,by+i//4,(ar[2*i+1],gb[2*i],gb[2*i+1],ar[2*i]))
                continue
            for y in range(bh):
                for x in range(bw):
                    if fmt==0:
                        v=data[pos+(y*bw+x)//2];v=(v>>4)if x%2==0 else v&15;g=v*17;c=(g,g,g,g)
                    elif fmt==1:g=data[pos+y*bw+x];c=(g,g,g,g)
                    elif fmt==2:v=data[pos+y*bw+x];g=(v&15)*17;c=(g,g,g,(v>>4)*17)
                    elif fmt==3:a,g=data[pos+2*(y*bw+x)],data[pos+2*(y*bw+x)+1];c=(g,g,g,a)
                    elif fmt==4:c=_rgb565(struct.unpack_from('>H',data,pos+2*(y*bw+x))[0])+(255,)
                    else:c=_rgb5a3(struct.unpack_from('>H',data,pos+2*(y*bw+x))[0])
                    put(bx+x,by+y,c)
            pos+=bw*bh*BLOCK[fmt][2]//8
    image=Image.new('RGBA',(w,h));image.putdata(px);return image

def _q565(c):return((c[0]*31+127)//255<<11)|((c[1]*63+127)//255<<5)|((c[2]*31+127)//255)
def _q5a3(c):
    if c[3]>=0xe0:return 0x8000|((c[0]*31+127)//255<<10)|((c[1]*31+127)//255<<5)|((c[2]*31+127)//255)
    return((c[3]*7+127)//255<<12)|((c[0]*15+127)//255<<8)|((c[1]*15+127)//255<<4)|((c[2]*15+127)//255)

def encode(data,index,image):
    r=texture_records(data)[index];w,h,fmt,at=r['width'],r['height'],r['format'],r['offset']
    image=image.convert('RGBA')
    if image.size!=(w,h):raise ValueError('Replacement texture size')
    out=bytearray(data);bw,bh,_=BLOCK[fmt];pos=at;get=lambda x,y:image.getpixel((min(x,w-1),min(y,h-1)))
    lum=lambda c:(c[0]*299+c[1]*587+c[2]*114)//1000
    for by in range(0,h,bh):
        for bx in range(0,w,bw):
            if fmt==14:
                for sub in range(4):
                    sx,sy=bx+(sub%2)*4,by+(sub//2)*4;block=[get(sx+i%4,sy+i//4)for i in range(16)]
                    opaque=[c for c in block if c[3]>=128];transparent=len(opaque)<16
                    if not opaque:out[pos:pos+8]=bytes([0,0,0,0,0xff,0xff,0xff,0xff]);pos+=8;continue
                    hi=max(opaque,key=lum);lo=min(opaque,key=lum);c0,c1=_q565(hi),_q565(lo)
                    if transparent:
                        if c0>c1:c0,c1=c1,c0
                        a,b=_rgb565(c0),_rgb565(c1);pal=[a,b,tuple((x+y)//2 for x,y in zip(a,b))]
                    else:
                        if c0==c1:c1=c0-1 if c0 else 1;c0=max(c0,c1+1)
                        if c0<c1:c0,c1=c1,c0
                        a,b=_rgb565(c0),_rgb565(c1);pal=[a,b,tuple((2*x+y)//3 for x,y in zip(a,b)),tuple((x+2*y)//3 for x,y in zip(a,b))]
                    bits=0
                    for i,c in enumerate(block):
                        if transparent and c[3]<128:idx=3
                        else:idx=min(range(len(pal)),key=lambda k:sum((p-q)**2 for p,q in zip(pal[k],c[:3])))
                        bits|=idx<<(30-2*i)
                    struct.pack_into('>HHI',out,pos,c0,c1,bits);pos+=8
                continue
            if fmt==6:
                for i in range(16):
                    c=get(bx+i%4,by+i//4);out[pos+2*i]=c[3];out[pos+2*i+1]=c[0];out[pos+32+2*i]=c[1];out[pos+32+2*i+1]=c[2]
                pos+=64;continue
            for y in range(bh):
                for x in range(bw):
                    c=get(bx+x,by+y);g=lum(c)
                    if fmt==0:
                        i=pos+(y*bw+x)//2;v=g>>4
                        out[i]=(out[i]&15)|(v<<4)if x%2==0 else(out[i]&0xf0)|v
                    elif fmt==1:out[pos+y*bw+x]=g
                    elif fmt==2:out[pos+y*bw+x]=((c[3]>>4)<<4)|(g>>4)
                    elif fmt==3:out[pos+2*(y*bw+x)]=c[3];out[pos+2*(y*bw+x)+1]=g
                    elif fmt==4:struct.pack_into('>H',out,pos+2*(y*bw+x),_q565(c))
                    else:struct.pack_into('>H',out,pos+2*(y*bw+x),_q5a3(c))
            pos+=bw*bh*BLOCK[fmt][2]//8
    return bytes(out)


def encode_mipmaps(data,index,image):
    """Replace the complete existing mip chain without changing TPL metadata.

    GX can display a smaller stored level instead of the full-size image.
    Regenerate every declared level, keeping its original allocation and filters.
    """
    from .channels import load_library
    load_library();from PIL import Image
    records=texture_records(data);r=records[index]
    table=struct.unpack_from('>I',data,8)[0]
    header=struct.unpack_from('>I',data,table+8*index)[0]
    levels=data[header+34]+1
    if not 1<=levels<=max(r['width'],r['height']).bit_length():
        raise ValueError('Invalid TPL mip count')
    if image.size!=(r['width'],r['height']):raise ValueError('Replacement texture size')
    stop=min([q['offset'] for q in records if q['offset']>r['offset']]+[len(data)])
    dimensions=[(max(1,r['width']>>i),max(1,r['height']>>i))for i in range(levels)]
    total=sum(data_size(r['format'],w,h)for w,h in dimensions)
    if r['offset']+total>stop:raise ValueError('TPL mip chain exceeds allocation')
    original_header=data[header:header+36];out=bytearray(data);at=r['offset']
    for w,h in dimensions:
        struct.pack_into('>HH',out,header,h,w);struct.pack_into('>I',out,header+8,at)
        out=bytearray(encode(bytes(out),index,image.resize((w,h),Image.Resampling.LANCZOS)))
        at+=data_size(r['format'],w,h)
    out[header:header+36]=original_header
    if len(out)!=len(data):raise ValueError('TPL mip replacement length')
    return bytes(out)

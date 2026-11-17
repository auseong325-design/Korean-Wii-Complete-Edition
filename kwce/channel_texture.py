"""Bounded local TPL IA4 decode/replace for channel text textures."""
import struct

def texture_records(data):
    if len(data)<12 or struct.unpack_from('>I',data)[0]!=0x0020af30:raise ValueError('TPL magic')
    count,table=struct.unpack_from('>II',data,4)
    if not 0<count<=4096 or table<12 or table+count*8>len(data):raise ValueError('TPL table bounds')
    records=[]
    for i in range(count):
        header,palette=struct.unpack_from('>II',data,table+8*i)
        if header<12 or header+36>len(data):raise ValueError('TPL header bounds')
        h,w,fmt,start=struct.unpack_from('>HHII',data,header)
        if not 0<w<=4096 or not 0<h<=4096:raise ValueError('TPL dimensions')
        records.append(dict(index=i,width=w,height=h,format=fmt,offset=start,palette=palette))
    return records

def decode_ia4(data,index):
    from .channels import load_library
    load_library();from PIL import Image
    r=texture_records(data)[index];w,h=r['width'],r['height'];at=r['offset'];size=((w+7)//8)*((h+3)//4)*32
    if r['format']!=2 or r['palette']or at+size>len(data):raise ValueError('Expected bounded IA4 texture')
    image=Image.new('RGBA',(w,h));pos=at
    for by in range(0,h,4):
        for bx in range(0,w,8):
            for y in range(4):
                for x in range(8):
                    v=data[pos];pos+=1
                    if bx+x<w and by+y<h:image.putpixel((bx+x,by+y),((v&15)*17,)*3+((v>>4)*17,))
    return image

def replace_ia4(data,index,image):
    r=texture_records(data)[index];w,h=r['width'],r['height'];at=r['offset']
    if image.size!=(w,h)or image.mode!='RGBA':raise ValueError('Replacement texture shape')
    decode_ia4(data,index);out=bytearray(data);pos=at
    for by in range(0,h,4):
        for bx in range(0,w,8):
            for y in range(4):
                for x in range(8):
                    if bx+x<w and by+y<h:
                        red,green,blue,alpha=image.getpixel((bx+x,by+y))
                        if red!=green or red!=blue:raise ValueError('IA4 requires grayscale')
                        out[pos]=((alpha>>4)<<4)|(red>>4)
                    pos+=1
    return bytes(out)

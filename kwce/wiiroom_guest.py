"""Fictional Room visitor/room fixtures; no NAND/save/console data is read.

Mii layout: original reverse engineering at wiibrew.org/wiki/Mii_data.
Every field is chosen here, including synthetic identity fields and name.
"""
import binascii,io,struct
from .wiiroom_feed import xml_response

def synthetic_mii():
    data=bytearray(74)
    def put(offset,fields):
        value=0;width=0
        for bits,item in fields:
            if not 0<=item<1<<bits:raise ValueError('Mii field bounds')
            value=(value<<bits)|item;width+=bits
        if width not in (16,32):raise ValueError('Mii word width')
        data[offset:offset+width//8]=value.to_bytes(width//8,'big')
    put(0,[(1,0),(1,0),(4,1),(5,1),(4,3),(1,0)])
    name='안내원'.encode('utf-16-be');data[2:2+len(name)]=name
    data[22]=64;data[23]=64
    struct.pack_into('>I',data,24,0x80000001) # invented, never copied from a console
    # The system-origin bytes remain zero; this avatar has no actual origin.
    put(32,[(3,0),(3,1),(4,0),(3,0),(1,1),(1,0),(1,0)])
    put(34,[(7,1),(3,1),(1,0),(5,0)])
    put(36,[(5,0),(1,0),(4,6),(6,0),(3,1),(4,4),(5,10),(4,2)])
    put(40,[(6,0),(2,0),(3,3),(5,12),(3,0),(1,0),(3,4),(4,2),(5,0)])
    put(44,[(4,0),(4,4),(5,9),(3,0)])
    put(46,[(5,0),(2,0),(4,4),(5,13)])
    put(48,[(4,0),(3,0),(1,0),(3,4),(5,10)])
    put(50,[(2,0),(2,0),(3,0),(4,4),(5,10)])
    put(52,[(1,0),(4,4),(5,20),(5,2),(1,0)])
    creator='KWCE'.encode('utf-16-be');data[54:54+len(creator)]=creator
    return bytes(data)+binascii.crc_hqx(data,0).to_bytes(2,'big')

def add_guest_fixtures(save,stamp,until):
    from PIL import Image,ImageDraw
    from .wiiroom_visual import _font
    mii=synthetic_mii();parade=None
    for name,size,text in [('g1234',(184,80),'한국어 예시 방'),('f1234',(320,180),'Wii의 방\n한국어 예시'),('c0001',(160,120),'한국어 영상')]:
        im=Image.new('RGB',size,(35,100,131));d=ImageDraw.Draw(im);d.multiline_text((12,18),text,font=_font(20 if size[0]<200 else 28),fill='white',spacing=5)
        raw=io.BytesIO();im.save(raw,'JPEG',subsampling=2,progressive=False)
        save(f'/url1/special/1/img/{name}.img',name+'.jpg',raw.getvalue())
        if name=='g1234':parade=raw.getvalue()
    save('/url1/mii/1.mii','synthetic-guide.mii',mii)
    save('/url1/mii/1.met','synthetic-guide.xml',xml_response('ConciergeMii',dict(miiid=1,clothes=1,color1='4080C0',color2='80C0F0',action=1,prof='한국어로 안내하는 예시 Mii입니다.',name='안내원',msginfo=[dict(type=i,msglist=(dict(seq=1,face=1,msg='한국어 예시 방입니다.'),))for i in range(1,8)],movieid=1,voice=False)))
    save('/url1/special/allbin.xml','room-binary.xml',xml_response('SpPageBin',dict(bininfo=[dict(sppageid=1,miiid=1,miibin=mii,logo1id='g1234',logobin=parade)])))
    save('/url1/special/1/page.xml','room-page.xml',xml_response('SpPage',dict(sppageid=1,strdt=stamp,enddt=until,name='한국어 예시 방',stopflag=0,level=1,bgm=1,mascot=False,contact=False,
        intro=dict(inmsginfo=[dict(inmsgseq=1,inmsg='한국어 예시 방입니다.')]),
        miiinfo=[dict(seq=1,miiid=1,color1='4080C0',color2='80C0F0',msginfo=[dict(msgseq=1,msg='방문해 주셔서 감사합니다.')])],
        menu=[dict(place=1,type=3,imageid='c0001',mov=dict(movieid=1,title='한국어 영상'))],logo=dict(logo1id='g1234',logo2id='f1234'))))


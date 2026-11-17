"""DVD silver banner: original HOME scanlines and native DVD logo, no custom artwork."""
import hashlib,struct
from .formats import U8,ash_decompress
from .channels import layout_sections,rebuild_layout,load_library
from .dvd_home_ui_v3 import _materials,_material_section,_texture_names,_texture_section
from .dvd_banner_v3 import _arc,_imd5,_silent_sound
from .u8_build import build_u8
from . import tpl

def _pane(source,name,material,x,y,w,h,color=(255,255,255,255),uv_y=1):
    p=bytearray(source);p[12:28]=name.encode().ljust(16,b'\0');p[8]|=1;p[10]=255
    struct.pack_into('>fff',p,0x24,x,y,0);struct.pack_into('>fff',p,0x30,0,0,0)
    struct.pack_into('>ff',p,0x3c,1,1);struct.pack_into('>ff',p,0x44,w,h)
    p[0x4c:0x5c]=bytes(color)*4;struct.pack_into('>H',p,0x5c,material)
    struct.pack_into('>8f',p,0x60,0,0,1,0,0,uv_y,1,uv_y)
    return bytes(p)

def _layout(home,disk,size,logo):
    hs=layout_sections(home.get('arc/blyt/th_HomeBtn_d.brlyt'));ds=layout_sections(disk.get('arc/blyt/my_DiskCh_a_R.brlyt'))
    hp={s[12:28].split(b'\0')[0].decode():s for s in hs if s[:4]in(b'pic1',b'pan1')}
    dp={s[12:28].split(b'\0')[0].decode():s for s in ds if s[:4]in(b'pic1',b'pan1')}
    hm=_materials(next(s for s in hs if s[:4]==b'mat1'));dm=_materials(next(s for s in ds if s[:4]==b'mat1'))
    hn=_texture_names(next(s for s in hs if s[:4]==b'txl1'));dn=_texture_names(next(s for s in ds if s[:4]==b'txl1'))
    used=[];mats=[];textures={}
    for pane,source,names,archive in [(hp['back_00'],hm,hn,home),(hp['back_02'],hm,hn,home),(dp['DVDDisk'],dm,dn,disk)]:
        mat=bytearray(source[struct.unpack_from('>H',pane,0x5c)[0]])
        count=struct.unpack_from('>I',mat,0x3c)[0]&15
        if count!=1:raise ValueError('Reviewed DVD filler material is not single-texture')
        idx=struct.unpack_from('>H',mat,0x40)[0];name=names[idx]
        if pane==dp['DVDDisk']:name='kwce_dvd_logo.tpl';body=logo
        else:body=archive.get('arc/timg/'+name)
        if name not in used:used.append(name);textures[name]=body
        struct.pack_into('>H',mat,0x40,used.index(name));mats.append(bytes(mat))
    w,h=size;small=w<200
    root=bytearray(dp['RootPane']);struct.pack_into('>ff',root,0x44,w,h)
    header=bytearray(next(s for s in ds if s[:4]==b'lyt1'));struct.pack_into('>ff',header,12,w,h)
    # Source texture's 57 repetitions in a 456 px pane = original 8 px scanlines.
    bg=_pane(hp['back_00'],'Silver',0,0,0,w,h,(153,153,153,255))
    lines=_pane(hp['back_02'],'Scanlines',1,0,0,w,h,(185,185,185,255),h/8)
    logo_pane=_pane(dp['DVDDisk'],'DVDLogo',2,w/2-(29 if small else 65),-h/2+(19 if small else 40),
                    46 if small else 96,30 if small else 64)
    sections=[bytes(header),_texture_section(used),_material_section(mats),bytes(root),b'pas1\0\0\0\x08',bg,lines,logo_pane,b'pae1\0\0\0\x08',
              b'grp1'+struct.pack('>I',28)+b'RootGroup'.ljust(16,b'\0')+bytes(4)]
    return rebuild_layout(disk.get('arc/blyt/my_DiskCh_a_R.brlyt'),sections),textures

def content0(resource,template):
    load_library();from PIL import Image
    outer=U8(resource);common=U8(ash_decompress(outer.get('layout/common/homeBtn1.ash')));kor=U8(ash_decompress(outer.get('layout/kor/homeBtn1.ash')))
    files={n:common.get(n)for n in common.files};files.update({n:kor.get(n)for n in kor.files});home=U8(build_u8(files,dot=False))
    disk=U8(ash_decompress(outer.get('layout/common/diskBann2.ash')))
    original=disk.get('arc/timg/my_DVDDisk_a.tpl');im=tpl.decode(original,0);logo=Image.new('RGBA',(96,64))
    # Deterministic glyph extraction from the official disc texture. The
    # surrounding silver is removed by luminance, retaining original antialiasing.
    for y in range(96,152):
        for x in range(8,104):
            rr,gg,bb,aa=im.getpixel((x,y));alpha=max(0,min(255,(min(rr,gg,bb)-165)*255//90))
            logo.putpixel((x-8,y-92),(255,255,255,alpha*aa//255))
    rec=tpl.texture_records(original)[0];header=bytearray(original[:rec['offset']]);texoff=struct.unpack_from('>I',header,12)[0]
    struct.pack_into('>HH',header,texoff,64,96);raw=bytes(header)+bytes(tpl.data_size(rec['format'],96,64));raw=tpl.encode(raw,0,logo)
    layout,textures=_layout(home,disk,(608.,456.),raw);banner=_arc('banner',layout,{},textures)
    layout,textures=_layout(home,disk,(128.,96.),raw);icon=_arc('icon',layout,{},textures)
    sound=_silent_sound(U8(template[0x640:]).get('meta/sound.bin'))
    prefix=bytearray(template[:0x640]);prefix[:0x40]=b'kwceDvdSilver'.ljust(0x40,b'\0')
    struct.pack_into('>III',prefix,0x8c,len(icon),len(banner),len(sound)-32);struct.pack_into('>I',prefix,0x98,0)
    title='DVD 플레이어'.encode('utf-16-be')
    for lang in range(10):
        at=0x9c+84*lang;prefix[at:at+84]=title+bytes(84-len(title))
    prefix[0x630:0x640]=bytes(16);prefix[0x630:0x640]=hashlib.md5(prefix[0x40:0x640]).digest()
    data=bytes(prefix)+build_u8({'meta/banner.bin':_imd5(banner),'meta/icon.bin':_imd5(icon),'meta/sound.bin':sound},dot=False)
    return data,dict(banner_bytes=len(banner),icon_bytes=len(icon),sound_bytes=len(sound),title='DVD 플레이어',
                     source='native HOME back_02 scanlines, silver tint, native disc DVD logo lower-right',static_banner=True)

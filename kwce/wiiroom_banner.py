"""Translate the Room wordmark fragments; retain Nintendo marks and animations."""
import hashlib,struct
from .channels import ChannelArchive,load_library,compress_lz10
from .wiiroom_visual import redraw,_coverage
from .tpl import decode,encode

def _wordmark(image,text,*,inverted=False):
    """I4 banner panes invert intensity; the icon panes use positive masks."""
    from PIL import Image,ImageChops
    w,h=image.size;mask,_=_coverage((w,h),text,0,(1,1,w-1,h-1))
    if inverted:mask=ImageChops.invert(mask)
    return Image.merge('RGBA',(mask,mask,mask,mask))

def korean_banner(content,*,native_wordmark=False,balanced=False,tight=False,geometric=False):
    load_library();from libWiiPy.archive import decompress_lz77
    outer=ChannelArchive(content[0x640:]);prefix=bytearray(content[:0x640]);records=[]
    specs={'meta/banner.bin':{'W.tpl':'Wii','No.tpl':'의','Ma.tpl':'방','Rect.tpl':'','Dot.tpl':''},
           'meta/icon.bin':{'Icon_Logo_W.tpl':'Wii','Icon_Logo_No.tpl':'의','Icon_Logo_Ma.tpl':'방','Icon_Logo_I.tpl':''}}
    if native_wordmark:
        # W/Rect/Dot and W/I are the native animated Wii logo, shared by
        # several panes. Retain all of them rather than painting "Wii" twice.
        specs={'meta/banner.bin':{'No.tpl':'의','Ma.tpl':'방'},
               'meta/icon.bin':{'Icon_Logo_No.tpl':'의','Icon_Logo_Ma.tpl':'방'}}
    for name,mapping in specs.items():
        wrapped=outer.get(name)
        if wrapped[:4]!=b'IMD5'or hashlib.md5(wrapped[32:]).digest()!=wrapped[16:32]:raise ValueError('Room banner integrity')
        before=ChannelArchive(decompress_lz77(wrapped[32:]));archive=before
        quads=None;geometry_record=None
        if geometric:
            # Revision 58+: geometric Hangul on the native W's height and letter gap.
            from .wiiroom_wordmark_v58 import wordmark,MARGIN
            kind='banner'if name.endswith('banner.bin')else'icon'
            archive,geometry_record,targets=wordmark(archive,kind)
            quads={('No.tpl','Icon_Logo_No.tpl')[kind=='icon']:targets[('No','Pic_No')[kind=='icon']],
                   ('Ma.tpl','Icon_Logo_Ma.tpl')[kind=='icon']:targets[('Ma','Pic_Ma')[kind=='icon']]}
        for basename,text in mapping.items():
            matches=[p for p in archive.files if p.endswith('/timg/'+basename)]
            if len(matches)!=1:raise ValueError('Room logo identity')
            path=matches[0];raw=archive.get(path);image=decode(raw,0)
            if geometric:
                from .wiiroom_wordmark_v58 import letter_texture
                q=quads[basename];replacement=letter_texture(text,q[2:],MARGIN[kind],image.size,inverted=kind=='banner')
            elif balanced:
                from .wiiroom_wordmark_v36 import letter_image
                replacement=letter_image(text,image.size,inverted=name.endswith('banner.bin'))
            else:replacement=_wordmark(image,text,inverted=name.endswith('banner.bin'))if native_wordmark else redraw(image,text,'white'if text else'blank')
            archive=ChannelArchive(archive.replace(path,encode(raw,0,replacement)))
        if geometric:pass  # panes were placed by wordmark() before drawing
        elif balanced:
            from .wiiroom_wordmark_v36 import geometry,BANNER,ICON,BANNER_V56,ICON_V56
            targets=(BANNER_V56 if tight else BANNER)if name.endswith('banner.bin')else(ICON_V56 if tight else ICON)
            archive,geometry_record=geometry(archive,targets)
        elif any(archive.get(p)!=before.get(p)for p in archive.files if p.endswith(('.brlan','.brlyt'))):raise ValueError('Logo geometry/animation changed')
        allowed=set(mapping)
        for p in before.files:
            if p.endswith(('.brlan','.brlyt'))or p.rsplit('/',1)[-1]in allowed:continue
            if archive.get(p)!=before.get(p):raise ValueError('Unrelated/native Wii logo resource changed')
        raw=archive.compact();payload=b'LZ77'+compress_lz10(raw)
        outer=ChannelArchive(outer.replace(name,b'IMD5'+len(payload).to_bytes(4,'big')+bytes(8)+hashlib.md5(payload).digest()+payload))
        struct.pack_into('>I',prefix,0x40+(0x4c if name.endswith('icon.bin')else 0x50),len(raw))
        record=dict(file=name,translated_textures=len(mapping),animation_layout_preserved=not(balanced or geometric))
        if geometry_record:record['balanced_geometry']=geometry_record
        if native_wordmark:record['native_wii_logo_preserved']=True
        records.append(record)
    return bytes(prefix)+outer.compact(),records

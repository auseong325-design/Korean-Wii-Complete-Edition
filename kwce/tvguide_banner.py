"""Translate only the two TV Guide wordmark textures; retain native animation."""
import hashlib,struct
from .channels import ChannelArchive,compress_lz10,load_library
from .tpl import decode,encode
from .wiiroom_visual import _coverage

def korean_banner(content,*,mask_channels=True):
    load_library();from libWiiPy.archive import decompress_lz77
    from PIL import Image,ImageDraw
    outer=ChannelArchive(content[0x640:]);prefix=bytearray(content[:0x640]);records=[]
    for name,path,text in [('meta/banner.bin','arc/timg/Mono02.tpl','TV 가이드 채널'),('meta/icon.bin','arc/timg/NTitle01.tpl','TV 가이드\n채널')]:
        payload=outer.get(name)
        if payload[:4]!=b'IMD5'or hashlib.md5(payload[32:]).digest()!=payload[16:32]or payload[32:36]!=b'LZ77':raise ValueError('TV logo archive identity')
        before=ChannelArchive(decompress_lz77(payload[32:]));archive=before;original=before.get(path);image=decode(original,0);w,h=image.size
        mask,_=_coverage((w,h),text,0,(2,4,w-2,h-4));replacement=Image.merge('RGBA',(mask,mask,mask,mask))if mask_channels else Image.new('RGBA',(w,h),(255,255,255,0));replacement.putalpha(mask)
        if name.endswith('icon.bin'):
            # The two thin rules are part of the original wordmark texture.
            draw=ImageDraw.Draw(replacement);draw.line((3,1,w-4,1),fill=(255,255,255,255));draw.line((3,h-2,w-4,h-2),fill=(255,255,255,255))
        archive=ChannelArchive(archive.replace(path,encode(original,0,replacement)))
        if set(archive.files)!=set(before.files)or any(archive.get(p)!=before.get(p)for p in archive.files if p!=path):raise ValueError('TV artwork change escaped wordmark')
        raw=archive.compact();compressed=b'LZ77'+compress_lz10(raw)
        outer=ChannelArchive(outer.replace(name,b'IMD5'+len(compressed).to_bytes(4,'big')+bytes(8)+hashlib.md5(compressed).digest()+compressed))
        struct.pack_into('>I',prefix,0x40+(0x4c if name.endswith('icon.bin')else 0x50),len(raw))
        records.append(dict(archive=name,texture=path,dimensions=[w,h],text=text,animations_and_layout_unchanged=True))
    return bytes(prefix)+outer.compact(),records

"""Korean Everybody Votes Channel menu tile and banner artwork.

The banner's English title is 21 letter panes whose textures are shared letter
sprites. Their animations only cycle material colour and shadow alpha, so the
Korean title reuses seven of those panes (and their shadows) at new positions,
hides the rest, and draws the syllables into the 40x40 Japanese letter
textures, which only the hidden Japanese group used. The English group becomes
KOR, as in kwce.mii_contest_visual. Animation streams are kept byte-identical.
"""
import hashlib,io,struct
from .channels import ChannelArchive,load_library,layout_sections,rebuild_layout,compress_lz10
from .channel_texture import replace_ia4,texture_records
from . import tpl

KOREAN_FONT_ENTRY='Wii-kr_Round Gothic B.ttf'
# (pane index, syllable, x, y) in N_titleUS_00/01 coordinates; rows as in English.
TITLE=[(0,'모',-129,77),(1,'두',-89,77),(2,'의',-49,77),
       (9,'투',-129,31),(10,'표',-89,31),(11,'채',-35,31),(12,'널',5,31)]

def _font(size):
    load_library();from PIL import ImageFont
    from .opera_font import KOREAN_SHARED
    return ImageFont.truetype(io.BytesIO(ChannelArchive(KOREAN_SHARED.read_bytes()).get(KOREAN_FONT_ENTRY)),size)

def _syllable(text,size=40):
    from PIL import Image,ImageDraw
    image=Image.new('RGBA',(size,size),(0,0,0,0));draw=ImageDraw.Draw(image);font=_font(34)
    l,t,r,b=draw.textbbox((0,0),text,font=font,stroke_width=2)
    draw.text(((size-(r-l))/2-l,(size-(b-t))/2-t),text,font=font,fill=(255,255,255,255),stroke_width=2,stroke_fill=(70,70,70,255))
    return image

def _icon_title(size=(104,64)):
    from PIL import Image,ImageDraw
    image=Image.new('RGBA',size,(0,0,0,255));draw=ImageDraw.Draw(image)
    for text,y,px in[('모두의',4,26),('투표 채널',34,24)]:
        font=_font(px);l,t,r,b=draw.textbbox((0,0),text,font=font,stroke_width=1)
        draw.text(((size[0]-(r-l))/2-l,y-t),text,font=font,fill=(255,255,255,255),stroke_width=1,stroke_fill=(110,110,110,255))
    return image

def _materials(section):
    count=struct.unpack_from('>H',section,8)[0];offsets=struct.unpack_from(f'>{count}I',section,12)
    return {section[o:o+20].rstrip(b'\0').decode('ascii'):o for o in offsets}

def _textures(section):
    count=struct.unpack_from('>H',section,8)[0];names=[]
    for i in range(count):
        at=12+struct.unpack_from('>I',section,12+8*i)[0];names.append(section[at:section.index(b'\0',at)].decode('ascii'))
    return names

def _retag_english(sections):
    hits=0
    for i,section in enumerate(sections):
        if section[:4]==b'grp1'and section[8:24].split(b'\0')[0]==b'ENG':
            section=bytearray(section);section[8:24]=b'KOR'+bytes(13);sections[i]=bytes(section);hits+=1
    if hits!=1:raise ValueError('Expected single English menu group')

def _banner(archive):
    path='arc/blyt/banner.brlyt';sections=layout_sections(archive.get(path));_retag_english(sections)
    mi=next(i for i,s in enumerate(sections)if s[:4]==b'mat1');mat=bytearray(sections[mi]);materials=_materials(mat)
    textures=_textures(next(s for s in sections if s[:4]==b'txl1'))
    used={n:(pane,text,x,y)for pane,text,x,y in TITLE for n in(f'P_titleUS_{pane:02d}',f'P_titleShdUS_{pane:02d}')}
    seen=set()
    for i,section in enumerate(sections):
        if section[:4]!=b'pic1':continue
        name=section[12:28].rstrip(b'\0').decode('latin1')
        if not(name.startswith('P_titleUS_')or name.startswith('P_titleShdUS_')):continue
        section=bytearray(section)
        if name in used:
            pane,text,x,y=used[name];slot=TITLE.index((pane,text,x,y))
            struct.pack_into('>ff',section,0x24,float(x),float(y));struct.pack_into('>ff',section,0x44,40.0,40.0)
            # Shared English sprites are mirrored per pane (b/d, n/u); use plain coordinates.
            if section[0x5e]<1:raise ValueError('Title pane without texture coordinates')
            struct.pack_into('>8f',section,0x60,0,0,1,0,0,1,1,1)
            o=materials[name];struct.pack_into('>H',mat,o+0x40,textures.index(f'titleJP_{slot:02d}.tpl'));seen.add(name)
        else:section[8]&=0xfe  # hide the unused English letters
        sections[i]=bytes(section)
    if len(seen)!=2*len(TITLE):raise ValueError('Korean title panes not found')
    sections[mi]=bytes(mat);archive=ChannelArchive(archive.replace(path,rebuild_layout(archive.get(path),sections)))
    for slot,(_,text,_,_) in enumerate(TITLE):
        name=f'arc/timg/titleJP_{slot:02d}.tpl';old=archive.get(name);r=texture_records(old)[0]
        if(r['width'],r['height'],r['format'])!=(40,40,2):raise ValueError('Unexpected Japanese letter texture')
        archive=ChannelArchive(archive.replace(name,replace_ia4(old,0,_syllable(text))))
    return archive

def _icon(archive):
    path='arc/blyt/icon.brlyt';sections=layout_sections(archive.get(path));_retag_english(sections)
    archive=ChannelArchive(archive.replace(path,rebuild_layout(archive.get(path),sections)))
    name='arc/timg/P_titleUS_00.tpl';old=archive.get(name);r=texture_records(old)[0]
    if(r['width'],r['height'],r['format'])!=(104,64,0):raise ValueError('Unexpected tile title texture')
    return ChannelArchive(archive.replace(name,tpl.encode(old,0,_icon_title())))

def korean_menu_art(content):
    load_library();from libWiiPy.archive import decompress_lz77
    outer=ChannelArchive(content[0x640:]);records=[]
    for name,make in[('meta/banner.bin',_banner),('meta/icon.bin',_icon)]:
        wrapped=outer.get(name)
        if wrapped[:4]!=b'IMD5'or wrapped[16:32]!=hashlib.md5(wrapped[32:]).digest():raise ValueError('Original menu artwork integrity')
        original=ChannelArchive(decompress_lz77(wrapped[32:]));archive=ChannelArchive(make(original).compact())
        if any(archive.get(p)!=original.get(p)for p in archive.files if p.endswith('.brlan')):raise ValueError('Menu animation changed')
        payload=b'LZ77'+compress_lz10(archive.data)
        if decompress_lz77(payload)!=archive.data:raise ValueError('Menu compression mismatch')
        outer=ChannelArchive(outer.replace(name,b'IMD5'+len(payload).to_bytes(4,'big')+bytes(8)+hashlib.md5(payload).digest()+payload))
        records.append(dict(file=name,uncompressed_size=len(archive.data),KOR_group=True,animation_preserved=True))
    prefix=bytearray(content[:0x640])
    for row in records:struct.pack_into('>I',prefix,0x40+(0x50 if 'banner' in row['file']else 0x4c),row['uncompressed_size'])
    return bytes(prefix)+outer.compact(),records

def korean_save_banner(data):
    """Redraw the English title of saveBannerData/voteBannerUS.tpl (RGB5A3 192x64)."""
    load_library();from PIL import ImageDraw
    from collections import Counter
    r=texture_records(data)[0]
    if(r['width'],r['height'],r['format'])!=(192,64,5):raise ValueError('Unexpected save banner texture')
    image=tpl.decode(data,0).convert('RGBA');px=image.load()
    # Each row of the title area takes its own most common (background) colour.
    for y in range(2,48):
        row=[px[x,y]for x in range(37,189)if min(px[x,y][:3])<200]
        # Old letter outlines are darker than the bar: keep the brighter half.
        lum=sorted(sum(c[:3])for c in row);mid=lum[len(lum)//2]
        fill=Counter(c for c in row if sum(c[:3])>=mid).most_common(1)[0][0]
        for x in range(37,189):px[x,y]=fill
    draw=ImageDraw.Draw(image)
    for text,top,size in[('모두의',4,19),('투표 채널',25,19)]:
        font=_font(size);l,t,_,_=draw.textbbox((0,0),text,font=font,stroke_width=2)
        draw.text((40-l,top-t),text,font=font,fill=(255,255,255,255),stroke_width=2,stroke_fill=(24,131,139,255))
    return tpl.encode(data,0,image),image

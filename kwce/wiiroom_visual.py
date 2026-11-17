"""Korean Wii Room text textures in content 2 layouts.

Each listed texture keeps its size and GX format and is redrawn with the
Korean shared Round Gothic font. 'label' textures (IA4 menu captions) are
black text with a white outline on transparency; 'mask' textures blend the
original background and ink values (measured from the texture itself) through
the Korean text coverage; 'shadow' does the same through a blurred coverage.
Changed layouts are recompressed with the optimal LZ11 parse, and further
layouts are recompressed only while the archive still exceeds the original
content size. Help screenshots, logos and genre/kana glyphs are not listed.
"""
import io
from .channels import ChannelArchive,load_library
from .channel_texture import texture_records
from .wiiroom_formats import decompress_lz11,compress_lz11_optimal
from . import tpl

FONT_ENTRY='Wii-kr_Round Gothic B.ttf'

L='label';M='mask';SH='shadow'
TEXTURES={
 'Move_Btn/Move_Btn_Guest_Btn':[('Move_Btn_Text_Guest.tpl','손님',L)],
 'Move_Btn/Move_Btn_Help_Btn':[('Move_Btn_Text_Help.tpl','도움말',L)],
 'Move_Btn/Move_Btn_Ironna_Btn':[('Move_Btn_Text_Ironna.tpl','여러 방',L)],
 'Move_Btn/Move_Btn_Message_Btn':[('Move_Btn_Text_Message.tpl','게시판',L)],
 'Move_Btn/Move_Btn_Message_Send_Btn':[('Move_Btn_Text_Message_Send.tpl','메시지\n보내기',L)],
 'Move_Btn/Move_Btn_Option_Btn':[('Move_Btn_Text_Option.tpl','설정',L)],
 'Move_Btn/Move_Btn_Other':[('Move_Btn_Text_Other.tpl','기타',L)],
 'Move_Btn/Move_Btn_Shopping_Btn':[('Move_Btn_Text_Shopping.tpl','쇼핑',L)],
 'Move_Btn/Move_Btn_Theater_Btn':[('Move_Btn_Text_Theater.tpl','극장',L)],
 'Move_Btn/Move_Btn_Tv_Btn':[('Move_Btn_Text_Tv.tpl','프로그램',L)],
 'Theater_Room/Theater_Room_AfterBuy_Btn':[('Theater_AfterBuy_Text.tpl','구입한 작품',L)],
 'Theater_Room/Theater_Room_Search_Btn':[('Theater_Search_Text.tpl','작품 찾기',L)],
 'Theater_Room/Theater_Room_WiiPoint_Btn':[('Theater_WiiPoint_Texttga.tpl','Wii 포인트',L)],
 'Shopping_Load/Shopping_Load_Scene':[('Shopping_Load_Logo.tpl','Wii의 방 쇼핑',M)],
 'PayMovie/PayMovie_All_Btn':[('Tv_Manzoku_Font_Minna.tpl','전체',L)],
 'Opening_Date/Opening_Date':[('Week_01.tpl','월',M),('Week_01_Shadow.tpl','월',SH),('Week_04.tpl','목',M),
                              ('Week_05.tpl','금',M),('Week_05_Shadow.tpl','금',SH),('Week_07.tpl','일',M),('Week_07_Shadow.tpl','일',SH)],
}
AGES=['~9세','10대','20대','30대','40대','50대','60대','70세~']
AGE_NAMES=['To9','10','20','30','40','50','60','From70']
for n,(text,name) in enumerate(zip(AGES,AGE_NAMES),1):
    TEXTURES[f'PayMovie/PayMovie_Age_Btn_{n:02d}']=[(f'Tv_Manzoku_Font_Age_{name}.tpl',text,M)]

EXTENDED_TEXTURES={
 'Help/Help_Room':[('Room_Etc_Btn.tpl','기타','button'),('Room_SS_IronnaBtn.tpl','여러 방','button'),('Room_SS_TheaterBtn.tpl','극장','button')],
 'Help/Help_Theater':[('Theater_Bought_Btn_V3.tpl','구입한\n작품','button'),('Theater_Play_Btn.tpl','재생','button'),('Theater_Rental_Btn.tpl','작품 안내','button'),('Theater_WiiPoint_Btn.tpl','Wii\n포인트','button')],
 'PayMovie/PayMovie_Motto_Genre_Btn':[('PayMovie_Motto_Genre.tpl','장르',M)],
 'PayMovie/PayMovie_Motto_Keyword_Btn':[('PayMovie_Motto_Keyword.tpl','검색어',M)],
}
for kana,label in zip(['A','Ka','Sa','Ta','Na','Ha','Ma','Ya','Ra','Wa'],['아','카','사','타','나','하','마','야','라','와']):
    EXTENDED_TEXTURES[f'PayMovie/PayMovie_Bought_{kana}_Btn']=[(f'PayMovie_Bought_{kana}.tpl',label,M)]
for n,(source,label) in enumerate([(5,'진실'),(1,'재미'),(2,'감동'),(3,'취향'),(4,'지식')],1):
    EXTENDED_TEXTURES[f'Mii_Detail/Mii_Detail_Thumb_{n:02d}']=[(f'Tv_Genre_moji_{source:02d}.tpl',label,M)]
BRAND_TEXTURES={
 'Title/Title_Scene':[('Title_Logo_W.tpl','Wii','white'),('Title_Logo_No.tpl','의','white'),('Title_Logo_Ma.tpl','방','white'),('Title_Logo_I.tpl','','blank')],
 'Wipe/Fade_White_Logo':[('Title_Logo.tpl','Wii의 방','white')],
}

def _font(size):
    load_library();from PIL import ImageFont
    from .opera_font import KOREAN_SHARED
    return ImageFont.truetype(io.BytesIO(ChannelArchive(KOREAN_SHARED.read_bytes()).get(FONT_ENTRY)),size)

def _coverage(size,text,stroke,box):
    """Largest rendering of text (with stroke) fitting box, centred on it; returns (fill, outline) masks."""
    from PIL import Image,ImageDraw
    x0,y0,x1,y1=box;bw,bh=x1-x0,y1-y0;probe=ImageDraw.Draw(Image.new('L',(1,1)))
    for px in range(max(bh,8)+4,5,-1):
        font=_font(px);gap=max(1,px//4)
        l,t,r,b=probe.multiline_textbbox((0,0),text,font=font,stroke_width=stroke,spacing=gap,align='center')
        if r-l<=bw and b-t<=bh:break
    else:raise ValueError(f'Korean texture text does not fit: {text!r}')
    x=x0+(bw-(r-l))/2-l;y=y0+(bh-(b-t))/2-t
    fill=Image.new('L',size,0);ImageDraw.Draw(fill).multiline_text((x,y),text,font=font,fill=255,spacing=gap,align='center')
    outline=Image.new('L',size,0)
    if stroke:ImageDraw.Draw(outline).multiline_text((x,y),text,font=font,fill=255,stroke_width=stroke,stroke_fill=255,spacing=gap,align='center')
    return fill,outline

def _ink_box(image,bg=None,pad=0):
    """Bounding box of the original lettering (alpha, or difference from the background)."""
    from PIL import Image,ImageChops
    if bg is None:mask=image.getchannel('A')
    else:mask=ImageChops.difference(image.convert('L'),Image.new('L',image.size,bg[0])).point(lambda v:255 if v>24 else 0)
    box=mask.getbbox()
    if not box:raise ValueError('Texture has no lettering')
    w,h=image.size;x0,y0,x1,y1=box
    return(max(0,x0-pad),max(0,y0-pad),min(w,x1+pad),min(h,y1+pad))

def _measure(image):
    """Background = most common pixel; ink = most common pixel far from it."""
    from collections import Counter
    counts=Counter(image.getdata());bg=counts.most_common(1)[0][0]
    far=[(n,c)for c,n in counts.items()if abs(c[0]-bg[0])+abs(c[3]-bg[3])>=160]
    if not far:raise ValueError('Texture has no ink to measure')
    return bg,max(far)[1]

def _widen(box,w):
    """Keep the lettering centre but allow the full texture width around it."""
    x0,y0,x1,y1=box;cx=(x0+x1)/2;half=min(cx,w-cx)-1
    return(int(cx-half),y0,int(cx+half),y1)

def redraw(original,text,style,main_box=None):
    load_library();from PIL import Image,ImageFilter
    w,h=original.size
    if style=='button2':
        from collections import Counter
        # The source can have transparent white margins. Sample opaque colour
        # inside the button, and clip the repaint to its original alpha shape.
        coloured=[p for p in original.getdata()if p[3]>200 and max(p[:3])-min(p[:3])>30]
        opaque=[p for p in original.getdata()if p[3]>200]
        bg=Counter(coloured or opaque).most_common(1)[0][0]
        neutral=max(bg[:3])-min(bg[:3])<30
        if neutral:box=(2,int(h*.55),w-2,h-4)
        elif w<45:box=(2,int(h*.35),w-2,h-2)
        else:box=(w//4+1,3,w-3,h-3)
        image=original.copy();coverage=Image.new('L',(w,h));from PIL import ImageDraw,ImageChops
        ImageDraw.Draw(coverage).rectangle((box[0],box[1],box[2]-1,box[3]-1),fill=255)
        coverage=ImageChops.multiply(coverage,original.getchannel('A'));image.paste(bg,(0,0),coverage)
        fill,_=_coverage((w,h),text,0,box);image.paste((40,40,40,255)if neutral else(255,255,255,255),(0,0),fill)
        return image
    if style in('white','blank'):
        image=Image.new('RGBA',(w,h))
        if style=='white':
            fill,_=_coverage((w,h),text,0,(1,1,w-1,h-1));image.paste((255,255,255,255),(0,0),fill)
        return image
    if style=='button':
        # Keep rounded corners and any icon. Replace only the caption region.
        from PIL import ImageDraw
        box=(max(1,w//4),2,w-2,h-2);image=original.copy()
        bg=original.getpixel((min(w-1,box[0]),min(h-1,3)))
        ImageDraw.Draw(image).rectangle((box[0],box[1],box[2]-1,box[3]-1),fill=bg)
        fill,_=_coverage((w,h),text,0,box);image.paste((255,255,255,255),(0,0),fill)
        return image
    if style=='label':
        fill,outline=_coverage((w,h),text,2,_widen(_ink_box(original,pad=1),w))
        image=Image.new('RGBA',(w,h),(0,0,0,0))
        image.paste((255,255,255,255),(0,0),outline);image.paste((0,0,0,255),(0,0),fill);return image
    if style=='shadow':
        # Blurred copy of the main glyph, drawn in the main texture's lettering box.
        from collections import Counter
        bg=Counter(original.getdata()).most_common(1)[0][0];ink=max(original.getdata(),key=lambda c:abs(c[0]-bg[0]))
        _,fill=_coverage((w,h),text,1,main_box);fill=fill.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(3))
    else:
        # A thin stroke in the ink colour matches the heavier original lettering.
        bg,ink=_measure(original);_,fill=_coverage((w,h),text,1,_ink_box(original,bg))
    # Blend every channel: I4/I8 textures keep only the intensity.
    return Image.composite(Image.new('RGBA',(w,h),ink),Image.new('RGBA',(w,h),bg),fill)

def korean_textures(content,*,extended=False,branding=False,refined_help=False,native_wordmark=False):
    """Return (content bytes, record) with the listed textures redrawn in Korean."""
    archive=ChannelArchive(content);record=[];changed=set()
    targets={k:list(v)for k,v in TEXTURES.items()}
    if extended:
        for layout,items in EXTENDED_TEXTURES.items():targets.setdefault(layout,[]).extend(items)
    if branding:
        for layout,items in BRAND_TEXTURES.items():targets.setdefault(layout,[]).extend(items)
    if native_wordmark and branding:
        # Retain the animated W and two shared i panes of the native Wii logo.
        targets['Title/Title_Scene']=[(n,t,s)for n,t,s in targets['Title/Title_Scene']if n not in('Title_Logo_W.tpl','Title_Logo_I.tpl')]
    if refined_help:
        targets={k:[(n,t,'button2'if s=='button'else s)for n,t,s in v]for k,v in targets.items()}
    for layout,items in targets.items():
        path=f'layout/{layout}.lex';raw=archive.get(path)
        if raw[:1]!=b'\x11':raise ValueError(f'{path}: expected LZ11 layout')
        inner=ChannelArchive(decompress_lz11(raw))
        for name,text,style in items:
            found=[p for p in inner.files if p.endswith('/timg/'+name)]
            if len(found)!=1:raise ValueError(f'{layout}: texture {name} not unique')
            data=inner.get(found[0])
            if len(texture_records(data))!=1:raise ValueError(f'{name}: expected one image')
            main_box=None
            if style==SH:
                main=tpl.decode(inner.get(found[0].replace('_Shadow.tpl','.tpl')),0);main_box=_ink_box(main,_measure(main)[0])
            new=tpl.encode(data,0,redraw(tpl.decode(data,0),text,style,main_box))
            if len(new)!=len(data):raise ValueError(f'{name}: size changed')
            inner=ChannelArchive(inner.replace(found[0],new));record.append(dict(layout=layout,texture=name,text=text,style=style))
        packed=compress_lz11_optimal(inner.compact())
        archive=ChannelArchive(archive.replace(path,packed));changed.add(path)
    out=archive.compact();extra=[]
    if len(out)>len(content):
        # Free space by recompressing untouched layouts, largest first.
        for path in sorted((p for p in archive.files if p.startswith('layout/')and p not in changed and archive.get(p)[:1]==b'\x11'),key=lambda p:-len(archive.get(p))):
            raw=archive.get(path);candidate=compress_lz11_optimal(decompress_lz11(raw))
            if len(candidate)<len(raw):archive=ChannelArchive(archive.replace(path,candidate));extra.append(path)
            out=archive.compact()
            if len(out)<=len(content):break
    if len(out)>len(content):raise ValueError('Main archive capacity exceeded by Korean textures')
    return out+bytes(len(content)-len(out)),dict(textures=record,recompressed_layouts=sorted(changed)+extra)

def fit_archive_capacity(content,capacity,already_recompressed):
    """Recompress untouched layouts losslessly after adding the HOME guide."""
    archive=ChannelArchive(content);out=archive.compact();extra=[]
    if len(out)>capacity:
        paths=[p for p in archive.files if p.startswith('layout/')and p not in already_recompressed and archive.get(p)[:1]==b'\x11']
        for path in sorted(paths,key=lambda p:-len(archive.get(p))):
            raw=archive.get(path);decoded=decompress_lz11(raw);packed=compress_lz11_optimal(decoded)
            if len(packed)>=len(raw):continue
            if decompress_lz11(packed)!=decoded:raise ValueError('Layout recompression roundtrip')
            archive=ChannelArchive(archive.replace(path,packed));extra.append(path);out=archive.compact()
            if len(out)<=capacity:break
    if len(out)>capacity:raise ValueError('Room guide archive capacity')
    return out+bytes(capacity-len(out)),extra

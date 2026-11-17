"""Korean help screenshots, using fictional titles in the native UI geometry.

Only example-screen textures change. Original pane layouts, cursor/remote art,
animations and the user's real screenshots/data are never touched.
"""
from .channels import ChannelArchive, load_library
from .wiiroom_formats import decompress_lz11, compress_lz11_optimal
from .wiiroom_visual import _font
from . import tpl

def _text(im, box, text, colour='white', maximum=10, background=None):
    from PIL import ImageDraw
    d=ImageDraw.Draw(im);x,y,r,b=box
    if background is not None:d.rectangle((x,y,r-1,b-1),fill=background)
    for px in range(maximum,3,-1):
        f=_font(px);bounds=d.multiline_textbbox((0,0),text,font=f,spacing=1,align='center')
        if bounds[2]-bounds[0]<=r-x and bounds[3]-bounds[1]<=b-y:break
    else:raise ValueError('Help example caption cannot fit')
    d.multiline_text((x+(r-x-bounds[2]+bounds[0])/2-bounds[0],y+(b-y-bounds[3]+bounds[1])/2-bounds[1]),text,font=f,fill=colour,spacing=1,align='center')

def _poster(im,box,title,n=0):
    from PIL import ImageDraw
    d=ImageDraw.Draw(im);x,y,r,b=box;palette=[(62,91,154,255),(194,107,57,255),(53,128,112,255),(154,100,151,255)]
    d.rectangle((x,y,r-1,b-1),fill=palette[n%4],outline=(245,245,245,255))
    w,h=r-x,b-y;d.ellipse((x+w*.25,y+h*.26,x+w*.75,y+h*.59),fill=(232,205,148,255))
    d.polygon([(x+2,b-3),(x+w*.55,y+h*.54),(r-3,b-3)],fill=(174,208,182,255))
    _text(im,(x+1,y+2,r-1,y+max(9,h//4)),title,maximum=8)

def redraw(original,name):
    from PIL import ImageDraw
    im=original.convert('RGBA').copy();w,h=im.size;d=ImageDraw.Draw(im)
    blue=(32,124,162,255);dark=(30,55,75,255);white=(246,247,246,255)
    if name in ('Room_SS_001.tpl','Room_SS_002.tpl'):
        _poster(im,(31,18,67,75),'한국어\n영상',0)
        d.rectangle((67,18,119,75),fill=(246,222,123,255))
        _text(im,(69,21,117,72),'Wii의 방\n프로그램 안내\n재생할 작품을\n선택해 주세요.',(55,55,55,255),8)
        _text(im,(4,96,66,114),'십자 버튼으로\n이동',maximum=7,background=dark)
        if name.endswith('002.tpl'):_text(im,(35,104,159,120),'프로그램  쇼핑  여러 방  설정',(30,45,55,255),6,white)
    elif name in ('Room_SS_003.tpl','Room_SS_009.tpl','Room_SS_010.tpl','Room_SS_011.tpl','Room_SS_012.tpl'):
        label={'Room_SS_003.tpl':'쇼핑','Room_SS_009.tpl':'메시지\n보내기','Room_SS_010.tpl':'게시판','Room_SS_011.tpl':'설정','Room_SS_012.tpl':'도움말'}[name]
        _text(im,(0,h//2,w,h),label,maximum=8,background=(26,181,223,255))
    elif name in ('Room_SS_008.tpl','Room_SS_015.tpl'):
        d.rectangle((0,0,w-1,h-1),fill=white)
        for i,label in enumerate(['기타','메시지\n보내기','게시판','도움말','설정','등록 변경']):
            y=i*20;d.rounded_rectangle((1,y+1,w-2,min(h-1,y+18)),radius=2,fill=(220,230,233,255))
            _text(im,(2,y+2,w-2,min(h,y+18)),label,(45,55,60,255),7)
    elif name in ('Room_SS_004.tpl','Theater_SS_Poster_Menu.tpl','Theater_SS_Poster_Menu_02.tpl','Theater_SS_Poster_Menu_03.tpl'):
        d.rectangle((0,0,w-1,h-1),fill=dark);_poster(im,(3,5,79,116),'한국어 영상',0)
        _text(im,(83,4,158,21),'한국어 영상\n예시 프로그램',maximum=8)
        _text(im,(83,25,158,64),'Wii의 방에서\n볼 수 있는 작품\n안내 예시입니다.',maximum=8,background=blue)
        for box,label,col in [((83,68,158,86),'작품 안내',blue),((83,89,158,106),'재생',blue),((83,108,158,119),'돌아가기',dark)]:_text(im,box,label,maximum=8,background=col)
    elif name=='Room_SS_IronnaParade.tpl':
        _text(im,(112,99,156,117),'목록 보기',(55,55,55,255),8,white)
    elif name in ('Room_SS_PopUp.tpl','Room_SS_PopUp02.tpl','Room_SS_PosterPopUp.tpl','Theater_SS_PopUp.tpl'):
        label='오늘의 작품' if name=='Room_SS_PosterPopUp.tpl' else '대여 / 구입'
        _text(im,(13,1,w-2,h-1),label,(45,55,60,255),7,white)
    elif name in ('Theater_SS_00.tpl','Theater_SS_01.tpl'):
        _poster(im,(45,26,122,78),'한국어 영상',2)
        _text(im,(3,81,77,99),'작품을 선택하고\n확인해 주세요.',maximum=7,background=dark)
        _text(im,(32,104,159,120),'Wii 포인트   구입한 작품   작품 찾기',(40,45,50,255),6,white)
        if name=='Theater_SS_00.tpl':_text(im,(112,0,160,11),'오늘의 작품',(45,55,60,255),6,white)
    elif name=='Theater_SS_02.tpl':
        d.rectangle((0,0,w-1,h-1),fill=(214,229,235,255))
        d.rounded_rectangle((11,4,151,99),radius=5,fill=white)
        _text(im,(17,10,145,80),'극장에서는 Wii 포인트로\n작품을 대여하거나 구입합니다.\n\nWii 쇼핑 채널로 이동하여\n포인트를 추가할 수 있습니다.\n\n현재 Wii 포인트: 200',(40,45,50,255),7)
        _text(im,(14,102,76,117),'돌아가기',(40,45,50,255),7,white)
        _text(im,(80,102,151,117),'Wii 쇼핑 채널',(40,45,50,255),7,white)
    elif name=='Theater_SS_Bar.tpl':_text(im,(20,1,w-1,h-1),'Wii의 방\n작품 안내',maximum=7,background=(221,157,21,255))
    elif name in ('Theater_SS_Bought.tpl','Theater_SS_UI.tpl','Theater_SS_UI_V3.tpl'):
        _text(im,(20,0,142,12),'구입한 작품' if 'Bought' in name else '작품 목록',maximum=8,background=blue)
        for i,label in enumerate(['한국어','자연','여행','요리','음악','동물','문화','생활']):
            x=27+(i%4)*28;y=14+(i//4)*40;_poster(im,(x,y,x+27,y+39),label,i)
        if 'Bought' in name:_text(im,(48,102,157,119),'전체 작품   가나다순',(40,45,50,255),7,white)
    elif name=='Theater_SS_Movie.tpl':
        d.rectangle((0,0,w-1,h-1),fill=(0,0,0,0))
        for box,title,n in [((31,1,100,54),'한국어 영상',0),((1,35,70,88),'자연의 풍경',2),((68,51,134,96),'여행 이야기',1)]:
            _poster(im,box,title,n);x,y,r,b=box;d.rectangle((x+1,b-11,r-2,b-2),fill=white);_text(im,(x+2,b-11,r-2,b-2),'◀  Ⅱ  ▶',(45,55,60,255),7)
    elif name=='Theater_SS_Play.tpl':
        d.rectangle((0,0,w-1,h-1),fill=(62,91,154,255));_poster(im,(7,8,153,116),'한국어 영상',0)
        _text(im,(57,3,123,20),'한국어 영상',(35,45,55,255),8,white)
        d.rectangle((5,82,155,119),fill=white);_text(im,(10,84,150,99),'00:03 / 00:10',(35,45,55,255),8)
        _text(im,(7,103,154,118),'종료   ◀◀    Ⅱ    ▶▶   버튼 안내',(35,45,55,255),7)
    elif name=='Theater_SS_Poster.tpl':
        _poster(im,(45,5,111,98),'자연의 풍경',1)
        _text(im,(41,104,159,119),'포스터를 선택해 작품 안내',maximum=6,background=dark)
    elif name=='Theater_SS_Wind_Btn.tpl':_text(im,(1,1,w-1,h-1),'전체 작품',(45,55,60,255),9,white)
    else:return None
    return im

def korean_help_examples(content,refined=False,polished=False):
    load_library();archive=ChannelArchive(content);records=[];changed=[]
    layouts=['Help/Help_Room','Help/Help_Theater']
    if refined:layouts.extend(['Help/Help_Guide_Liv_Btn','Help/Help_Guide_Pay_Btn','Help/Help_Guide_Tv_Btn'])
    for layout in layouts:
        path='layout/'+layout+'.lex';inner=ChannelArchive(decompress_lz11(archive.get(path)))
        for p in inner.files:
            if not p.endswith('.tpl'):continue
            name=p.split('/')[-1];data=inner.get(p);before=tpl.decode(data,0);after=redraw(before,name)
            if refined:
                from PIL import Image,ImageDraw
                if name in ('Room_SS_001.tpl','Room_SS_002.tpl'):
                    ImageDraw.Draw(after).rectangle((0,89,159,119),fill=(246,247,246,255))
                    _text(after,(2,90,68,108),'십자 버튼으로 이동',maximum=7,background=(30,55,75,255))
                    _text(after,(1,109,159,120),'프로그램  쇼핑  여러 방  설정',(40,45,50,255),7)
                if name.startswith('Help_Btn_Guide_'):
                    sample=before.resize((160,120))
                    if name=='Help_Btn_Guide_Tv.tpl':
                        after=sample.copy();ImageDraw.Draw(after).rectangle((48,2,159,119),fill=(235,245,250,255))
                        for j,text in enumerate(['한국어 영상','자연의 풍경','여행 이야기','생활 이야기']):
                            _text(after,(50,4+j*24,158,25+j*24),text,(35,75,100,255),9,background=(211,235,245,255))
                        _text(after,(1,102,159,119),'프로그램을 선택해 주세요.',(40,45,50,255),8,(246,247,246,255))
                    else:
                        after=redraw(sample,'Room_SS_002.tpl'if name=='Help_Btn_Guide_Liv.tpl'else'Theater_SS_01.tpl')
                        ImageDraw.Draw(after).rectangle((0,89,159,119),fill=(246,247,246,255))
                        _text(after,(2,90,158,119),'Wii의 방'if name=='Help_Btn_Guide_Liv.tpl'else'Wii 포인트  구입한 작품  작품 찾기',(40,45,50,255),8)
                    after=after.resize(before.size)
            if polished and name in ('Room_SS_001.tpl','Room_SS_002.tpl'):
                from PIL import ImageDraw
                d=ImageDraw.Draw(after)
                d.rectangle((67,18,128,76),fill=(246,222,123,255))
                _text(after,(69,21,127,72),'Wii의 방\n프로그램 안내\n재생할 작품을\n선택해 주세요.',(55,55,55,255),8)
                if name=='Room_SS_002.tpl':
                    _text(after,(0,0,25,25),'손님',(40,45,50,255),7,(246,247,246,255))
                    _text(after,(133,0,160,28),'기타',(40,45,50,255),7,(246,247,246,255))
            if after is None:continue
            encoded=tpl.encode(data,0,after)
            if len(encoded)!=len(data):raise ValueError('Help example format/size changed')
            inner=ChannelArchive(inner.replace(p,encoded));records.append(dict(layout=layout,texture=name,width=before.width,height=before.height))
        archive=ChannelArchive(archive.replace(path,compress_lz11_optimal(inner.compact())));changed.append(path)
    if len(records)!=(33 if refined else 30):raise ValueError('Unexpected help screenshot replacement coverage')
    return archive.compact(),dict(textures=records,changed_layouts=changed,fictional_examples=True,layouts_animations_preserved=True)

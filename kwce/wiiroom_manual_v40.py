"""Preserve grayscale antialiasing in I8 guide textures and localize its exit prompt."""
import hashlib,io,re
from .channels import ChannelArchive,load_library,compress_lz10
from .wiiroom_visual import _font
from . import tpl

LABELS=[((5,0,550,24),'Wii의 방은 Wii 리모컨으로 조작합니다.'),
        ((7,28,83,54),'포인터'),((87,28,274,54),'화면에서 이동'),((308,28,547,54),'선택한 항목 결정'),
        ((37,58,274,85),'위아래로 이동'),((308,58,547,85),'이전 화면으로'),
        ((37,88,274,115),'좌우로 이동'),((358,88,547,115),'Mii 잡기'),
        ((5,146,550,170),'동영상을 시청할 때'),((38,175,274,202),'재생 / 일시정지')]
CHROME={'it_btn_01.tpl':'자세한 설명 보기',
        'it_net_wrd.tpl':'※ Wii 쇼핑 채널에서 자세한 설명을 볼 수 있습니다.',
        'it_ttl_wrd_a.tpl':'Wii 리모컨 사용 방법'}
PROMPT='자세한 설명을 보기 위해\r\nWii의 방을 종료하시겠습니까?\r\n(저장하지 않은 내용은 사라집니다.)'

def smooth_mask(size,text,box):
    """Rasterize at four times the target grid, then retain 8-bit coverage."""
    load_library();from PIL import Image,ImageDraw
    w,h=size;x0,y0,x1,y1=box;scale=4;probe=ImageDraw.Draw(Image.new('L',(1,1)))
    for px in range(max(y1-y0,8)+4,5,-1):
        font=_font(px*scale);gap=max(1,px//4)*scale
        l,t,r,b=probe.multiline_textbbox((0,0),text,font=font,spacing=gap,align='center')
        if r-l<=(x1-x0)*scale and b-t<=(y1-y0)*scale:break
    else:raise ValueError('Smooth guide label cannot fit')
    image=Image.new('L',(w*scale,h*scale))
    ImageDraw.Draw(image).multiline_text((x0*scale+((x1-x0)*scale-(r-l))/2-l,
        y0*scale+((y1-y0)*scale-(b-t))/2-t),text,font=font,fill=255,spacing=gap,align='center')
    return image.resize(size,Image.Resampling.LANCZOS)

def localized_network_csv(raw):
    if not raw.startswith(b'\xfe\xff'):raise ValueError('Guide exit prompt encoding')
    text=raw[2:].decode('utf-16-be');cells=list(re.finditer(r'"([^"]*)"',text))
    if len(cells)!=7 or not cells[0].group(1).startswith('ゲームを終了します。')or not cells[1].group(1).startswith('This will quit the game.'):raise ValueError('Guide exit prompt identity')
    for item in reversed(cells):
        lo,hi=item.span(1);text=text[:lo]+PROMPT+text[hi:]
    if len(re.findall(r'"([^"]*)"',text))!=7:raise ValueError('Guide exit prompt ABI changed')
    return b'\xfe\xff'+text.encode('utf-16-be')

def korean_manual_smooth(content,controller_content):
    load_library();from PIL import Image
    from libWiiPy.archive import decompress_lz77
    a=ChannelArchive(content);image=Image.open(io.BytesIO(a.get('hbm/manual.jpg'))).convert('RGB')
    if image.size!=(554,256):raise ValueError('Room controller page dimensions')
    for box,text in LABELS:
        mask=smooth_mask(image.size,text,box);image.paste((6,0,0),box);image.paste((255,255,255),(0,0),mask)
    # Baseline JPEG quality 93 fits the original archive budget, including
    # the translated CSV, without changing the page grid or decoder path.
    output=io.BytesIO();image.save(output,'JPEG',quality=93,subsampling=0,optimize=True,progressive=False)
    a=ChannelArchive(a.replace('hbm/manual.jpg',output.getvalue()))
    path='hbm/HomeButton3/network.csv';a=ChannelArchive(a.replace(path,localized_network_csv(a.get(path))))
    controller=ChannelArchive(controller_content);records=[];edges=[]
    for name in controller.files:
        if 'LZ77_homeBtn_nwm_'not in name:continue
        before=ChannelArchive(decompress_lz77(controller.get(name)));language=before
        for basename,text in CHROME.items():
            paths=[p for p in language.files if p.endswith('/'+basename)]
            if len(paths)!=1:raise ValueError('Controller chrome identity')
            path=paths[0];raw=language.get(path);r=tpl.texture_records(raw)[0]
            if r['format']!=1:raise ValueError('Controller chrome must use I8 coverage')
            mask=smooth_mask((r['width'],r['height']),text,(1,1,r['width']-1,r['height']-1))
            # I8 stores RGB intensity, not RGBA alpha. Pasting straight white
            # with an alpha mask loses all edge coverage when encoded as I8.
            coverage=Image.merge('RGBA',(mask,mask,mask,mask));new=tpl.encode(raw,0,coverage)
            histogram=tpl.decode(new,0).getchannel('R').histogram();tones=sum(n>0 for n in histogram[1:255])
            if tones<32 or len(new)!=len(raw):raise ValueError('Guide antialiasing/texture size regression')
            language=ChannelArchive(language.replace(path,new));edges.append(dict(archive=name,texture=basename,intermediate_tones=tones))
        if any(language.get(p)!=before.get(p)for p in before.files if p.rsplit('/',1)[-1]not in CHROME):raise ValueError('Unrelated controller resource changed')
        envelope=b'LZ77'if controller.get(name).startswith(b'LZ77')else b''
        controller=ChannelArchive(controller.replace(name,envelope+compress_lz10(language.compact())));records.append(name)
    if len(records)!=7:raise ValueError('Expected seven guide language archives')
    return a.compact(),controller.compact(),dict(controller_page_translated=True,button_icons_preserved=True,
        chrome_languages=7,chrome_textures_per_language=3,grayscale_antialiasing_preserved=True,supersample=4,
        jpeg_quality=93,jpeg_dimensions=[554,256],network_prompt_columns=7,network_prompt_korean=True,
        edge_coverage=edges,manual_sha256=hashlib.sha256(output.getvalue()).hexdigest())

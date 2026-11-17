"""Translate the embedded one-page controller guide and its three chrome textures."""
import io,hashlib
from .channels import ChannelArchive,load_library,compress_lz10
from .wiiroom_visual import _coverage,redraw
from .tpl import decode,encode

def korean_manual(content,controller_content,*,legacy_wrapper=False,smooth=False):
    if smooth:
        from .wiiroom_manual_v40 import korean_manual_smooth
        return korean_manual_smooth(content,controller_content)
    load_library();from PIL import Image
    from libWiiPy.archive import decompress_lz77
    archive=ChannelArchive(content);raw=archive.get('hbm/manual.jpg');image=Image.open(io.BytesIO(raw)).convert('RGB')
    if image.size!=(554,256):raise ValueError('Room controller guide size')
    labels=[((5,0,550,24),'Wii의 방은 Wii 리모컨으로 조작합니다.'),
            ((7,28,83,54),'포인터'),((87,28,274,54),'화면에서 이동'),((308,28,547,54),'선택한 항목 결정'),
            ((37,58,274,85),'위아래로 이동'),((308,58,547,85),'이전 화면으로'),
            ((37,88,274,115),'좌우로 이동'),((358,88,547,115),'Mii 잡기'),
            ((5,146,550,170),'동영상을 시청할 때'),((38,175,274,202),'재생 / 일시정지')]
    for box,text in labels:
        fill,_=_coverage(image.size,text,0,box)
        image.paste((6,0,0),box);image.paste((255,255,255),(0,0),fill)
    output=io.BytesIO();image.save(output,'JPEG',quality=90,subsampling=0)
    archive=ChannelArchive(archive.replace('hbm/manual.jpg',output.getvalue()))
    controller=ChannelArchive(controller_content);records=[]
    mapping={'it_btn_01.tpl':'자세한 설명 보기','it_net_wrd.tpl':'※ Wii 쇼핑 채널에서 자세한 설명을 볼 수 있습니다.','it_ttl_wrd_a.tpl':'Wii 리모컨 사용 방법'}
    for name in controller.files:
        if 'LZ77_homeBtn_nwm_'not in name:continue
        language=ChannelArchive(decompress_lz77(controller.get(name)));before=language
        for basename,text in mapping.items():
            paths=[p for p in language.files if p.endswith('/'+basename)]
            if len(paths)!=1:raise ValueError('Room guide chrome identity')
            path=paths[0];texture=language.get(path);language=ChannelArchive(language.replace(path,encode(texture,0,redraw(decode(texture,0),text,'white'))))
        if any(language.get(p)!=before.get(p)for p in before.files if p.endswith(('.brlyt','.brlan'))):raise ValueError('Guide layout/animation changed')
        envelope=b'LZ77'if legacy_wrapper or controller.get(name).startswith(b'LZ77')else b''
        controller=ChannelArchive(controller.replace(name,envelope+compress_lz10(language.compact())))
        records.append(name)
    return archive.compact(),controller.compact(),dict(controller_page_translated=True,button_icons_preserved=True,chrome_languages=len(records),chrome_textures_per_language=3,manual_sha256=hashlib.sha256(output.getvalue()).hexdigest())

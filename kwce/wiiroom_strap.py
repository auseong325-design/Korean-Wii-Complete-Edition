"""Translate the two built-in wrist-strap images; retain Nintendo safety art."""
from .channels import ChannelArchive,load_library
from .wiiroom_formats import decompress_lz11,compress_lz11_optimal
from .wiiroom_visual import _font
from . import tpl

def korean_strap(content):
    load_library()
    from PIL import ImageDraw
    archive=ChannelArchive(content);source=decompress_lz11(archive.get('strapImage_En_LZ.bin'));edited=source
    instructions=['주위에 사람이나 물건이 없는지\n확인하고 플레이해 주세요.',
                  'Wii 리모컨에 다른 컨트롤러를\n연결할 때에는 손목 스트랩을\n커넥터의 고리에 통과시켜 주세요.']
    bottom='손목 스트랩을 손목에 끼우고 꼭 조여 주세요.\nWii 리모컨을 단단히 잡고 손에서 놓치지 마세요.\nWii 리모컨 재킷을 사용해 주세요.'
    for i,message in enumerate(instructions):
        im=tpl.decode(source,i).convert('RGBA')
        if im.size!=(640,480):raise ValueError('Unexpected wrist-strap image dimensions')
        d=ImageDraw.Draw(im);d.rectangle((270,217,634,333),fill='white');d.rectangle((36,357,635,446),fill='white')
        d.multiline_text((277,224),message,font=_font(20),fill=(96,96,96),spacing=7)
        d.multiline_text((41,362),bottom,font=_font(21),fill=(0,174,213),spacing=6)
        edited=tpl.encode(edited,i,im)
    if len(edited)!=len(source):raise ValueError('Wrist-strap texture length changed')
    packed=compress_lz11_optimal(edited)
    if decompress_lz11(packed)!=edited:raise ValueError('Wrist-strap compression roundtrip')
    targets=[p for p in archive.files if p.startswith('strapImage_')and p.endswith('_LZ.bin')]
    if len(targets)!=7:raise ValueError('Unexpected strap resource coverage')
    for p in targets:archive=ChannelArchive(archive.replace(p,packed))
    return archive.compact(),dict(resources=len(targets),images_per_resource=2,art_preserved=True,source_language='En',korean_text=True)

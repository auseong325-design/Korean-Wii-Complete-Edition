"""Apply the native Korean Mario Kart strap art; only uniform scaling is used."""
import hashlib,json
from pathlib import Path
from .channels import ChannelArchive,load_library
from .wiiroom_formats import decompress_lz11,compress_lz11_optimal
from . import tpl

def korean_kart_strap(content):
    root=Path(__file__).resolve().parents[1];cfg=json.loads((root/'configs/wiiroom-strap-kart-v1.lock.json').read_text())
    if not cfg['native_korean']or cfg['redrawn']or cfg['title_id']!='00010004524d434b':raise ValueError('Native Korean strap scope differs')
    load_library();from PIL import Image
    a=ChannelArchive(content);raw=decompress_lz11(a.get('strapImage_En_LZ.bin'));edited=raw
    for i,row in enumerate(cfg['files']):
        b=(root/row['path']).read_bytes()
        if hashlib.sha256(b).hexdigest()!=row['sha256']:raise ValueError('Native Korean strap reference differs')
        im=tpl.decode(b,0)
        if im.size!=(608,456):raise ValueError('Native Korean strap dimensions')
        im=im.resize((640,480),Image.Resampling.LANCZOS);edited=tpl.encode(edited,i,im)
    packed=compress_lz11_optimal(edited)
    if decompress_lz11(packed)!=edited:raise ValueError('Native Korean strap roundtrip')
    targets=[p for p in a.files if p.startswith('strapImage_')and p.endswith('_LZ.bin')]
    if len(targets)!=7:raise ValueError('Unexpected strap resource coverage')
    for p in targets:a=ChannelArchive(a.replace(p,packed))
    return a.compact(),dict(resources=7,images_per_resource=2,native_korean_source='Mario Kart Channel Korea',
        native_ui_reference='wiiroom-strap-kart-v1.lock.json',text_redrawn=False,uniform_scale='20/19',source_dimensions=[608,456],target_dimensions=[640,480])

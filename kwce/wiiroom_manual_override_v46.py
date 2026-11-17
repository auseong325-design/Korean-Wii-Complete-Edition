"""NWM's language archive shadows HOME's font; localize those overrides too."""
from .channels import ChannelArchive,load_library,compress_lz10
from .channel_font import font_data
from .wiiroom_manual_v40 import PROMPT

def korean_nwm_font_overrides(controller,home,prompt=PROMPT):
    load_library();from libWiiPy.archive import decompress_lz77
    home=ChannelArchive(home);source=ChannelArchive(decompress_lz77(home.get('HomeButton3/LZ77_homeBtn.arc')))
    path='arc/font/RevoIpl_UtrilloProGrecoStd_M_32_I4.brfnt';font=source.get(path);_,coverage,_=font_data(font)
    needed={ord(c)for c in prompt if ord(c)>=32}
    if not needed<=coverage.keys():raise ValueError('Korean NWM source lacks prompt characters')
    archive=ChannelArchive(controller);records=[]
    for name in archive.files:
        before=ChannelArchive(decompress_lz77(archive.get(name)));fonts=[p for p in before.files if p.endswith('.brfnt')]
        if not fonts:continue # English/German/Spanish already inherit HOME's font.
        if fonts!=[path]:raise ValueError('Unreviewed NWM shadow font')
        _,mapping,_=font_data(before.get(path));after=ChannelArchive(before.replace(path,font))
        if any(before.get(p)!=after.get(p)for p in before.files if p!=path):raise ValueError('NWM nonfont resource changed')
        envelope=b'LZ77'if archive.get(name).startswith(b'LZ77')else b''
        archive=ChannelArchive(archive.replace(name,envelope+compress_lz10(after.compact())))
        records.append(dict(archive=name,old_glyph_count=len(mapping),new_glyph_count=len(coverage),all_prompt_glyphs_verified=True))
    if len(records)!=4:raise ValueError('Expected four NWM language font overrides')
    return archive.compact(),records

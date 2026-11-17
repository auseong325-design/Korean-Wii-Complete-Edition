"""Resolve the user's verified 43K shared font locally; never export bytes."""
import struct
from .channels import ROOT,ChannelArchive,sha256
from .channel_font import font_data
EXPECTED='c80f828638e109170269924f4d8f3859419b8ed87afcc606d52f1aa1db44c0e1'

def korean_shared_fonts():
    wii=ROOT/'workspace/sandbox/gc-v6/user/Wii';tmd=(wii/'title/00000001/00000002/content/title.tmd').read_bytes()
    expected=None
    for i in range(int.from_bytes(tmd[0x1de:0x1e0],'big')):
        at=0x1e4+i*36
        if int.from_bytes(tmd[at+4:at+6],'big')==5:expected=tmd[at+16:at+36]
    if expected is None:raise ValueError('43K shared font record missing')
    content_map=(wii/'shared1/content.map').read_bytes()
    if len(content_map)%28:raise ValueError('Shared font map bounds')
    matches=[content_map[i:i+8].decode('ascii')for i in range(0,len(content_map),28)if content_map[i+8:i+28]==expected]
    if len(matches)!=1 or any(c not in'0123456789abcdef'for c in matches[0]):raise ValueError('Shared font map identity')
    data=(wii/'shared1'/f'{matches[0]}.app').read_bytes()
    if sha256(data)!=EXPECTED:raise ValueError('Only the verified local 43K shared fonts supported')
    archive=ChannelArchive(data);records=[]
    if set(archive.files)!={'wbf1.brfna','wbf2.brfna'}:raise ValueError('Unexpected shared font contents')
    for name in archive.files:
        font=archive.get(name)
        if font[:4]!=b'RFNA':raise ValueError('Expected local font archive')
        # RFNA shares the raw CMAP block layout. This read-only parsing view
        # never rewrites/pretends the RFNA resource is an RFNT at runtime.
        _,mapping,_=font_data(b'RFNT'+font[4:]);coverage=sum(0xac00<=c<=0xd7a3 for c in mapping)
        if coverage!=11172:raise ValueError('Incomplete local Korean font coverage')
        records.append(dict(font=name,sha256=sha256(font),hangul_syllables=coverage))
    return data,dict(source='verified local 43K menu shared content index 5',source_sha256=EXPECTED,fonts=records)

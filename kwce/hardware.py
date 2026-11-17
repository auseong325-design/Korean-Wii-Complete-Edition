"""Checks for WADs that leave the emulator for the user's own console.

A hardware WAD must be a normal channel (00010001/00010002, never a system
title or IOS), must not carry the Dolphin-only local service redirects
(127.0.0.x / localhost counts equal to its WiiLink original), and is
fakesigned for an IOS with the signature-check patch. Counts are taken over
every content with nested Yaz0/LZ77/LZ10/LZ11/U8 decoded.
"""
from .channels import ChannelArchive,load_library

CHANNEL_TYPES={'00010001','00010002'}
# Hidden CHANNEL titles (type 00010008) that may be packaged, by exact title id only.
# Set Personal Data (HCCJ) is the address channel Food/Photo Prints read; it is a
# channel, not a system title or IOS. Every other 00010008 title stays refused.
HIDDEN_CHANNELS={'000100084843434a'}
LOCAL=(b'127.0.0',b'localhost')

def channel_title(tid):
    tid=tid.lower()
    return tid[:8]in CHANNEL_TYPES or tid in HIDDEN_CHANNELS

def _decoders():
    load_library()
    from libWiiPy.archive import decompress_lz77
    from .votes_resources import decode_yaz0
    from .wiiroom_formats import decompress_lz11
    return decompress_lz77,decode_yaz0,decompress_lz11

def local_reference_counts(title):
    lz77,yaz0,lz11=_decoders();counts=dict.fromkeys(LOCAL,0)
    def walk(data,depth):
        if depth>5:return
        if data[:4]==b'Yaz0':
            try:return walk(yaz0(data),depth+1)
            except Exception:return
        if data[:4]==b'LZ77' or(data[:1]==b'\x10'and len(data)>8):
            try:return walk(lz77(data),depth+1)
            except Exception:
                if data[:4]==b'LZ77':return
        if data[:1]==b'\x11'and len(data)>8:
            try:return walk(lz11(data),depth+1)
            except Exception:pass
        for key in LOCAL:counts[key]+=data.count(key)+data.count(key.decode().encode('utf-16-be'))
        if data[:4]==b'U\xaa8-':
            try:
                archive=ChannelArchive(data)
                for name in archive.files:walk(archive.get(name),depth+1)
            except Exception:pass
    for index in range(len(title.tmd.content_records)):
        content=title.get_content_by_index(index);walk(content,0)
        at=content.find(b'U\xaa8-')
        if 0<at<0x700:walk(content[at:],0)  # IMET banner header before the archive
    return {k.decode():v for k,v in counts.items()}

def hardware_wad(korean_bytes,original_bytes):
    """Return (fakesigned WAD bytes, record) after the hardware checks."""
    lib=load_library();title=lib.title.Title();title.load_wad(korean_bytes)
    original=lib.title.Title();original.load_wad(original_bytes)
    tid=title.tmd.title_id.lower()
    if not channel_title(tid):raise ValueError('Only channel titles may be packaged')
    if tid!=original.tmd.title_id.lower():raise ValueError('Original WAD is a different title')
    korean_counts=local_reference_counts(title);original_counts=local_reference_counts(original)
    if korean_counts!=original_counts:raise ValueError(f'{tid}: local test address references differ from the original')
    title.fakesign()
    if not title.get_is_fakesigned():raise ValueError('Fakesign failed')
    wad=title.dump_wad();check=lib.title.Title();check.load_wad(wad)
    if any(check.get_content_by_index(i)!=title.get_content_by_index(i)for i in range(len(title.tmd.content_records))):raise ValueError('Content roundtrip')
    return wad,dict(title_id=tid,version=title.tmd.title_version,ios=title.tmd.ios_tid,contents=len(title.tmd.content_records),local_reference_counts=korean_counts)

def fakesigned(wad_bytes):
    lib=load_library();title=lib.title.Title();title.load_wad(wad_bytes)
    if not channel_title(title.tmd.title_id):raise ValueError('Only channel titles may be packaged')
    if not title.get_is_fakesigned():title.fakesign()
    return title.dump_wad(),dict(title_id=title.tmd.title_id.lower(),version=title.tmd.title_version,ios=title.tmd.ios_tid)

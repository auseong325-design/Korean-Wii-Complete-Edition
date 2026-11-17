"""Korean overlay for public WiiLink News files (news.bin.HH, version 512).

Layout follows WiiLink24/NewsChannel@daccc47 (header.go, articles.go, topics.go,
sources.go, locations.go, headlines.go). Translated UTF-16 strings are appended
after the original payload and only their offset/size fields are repointed;
numbers, timestamps, pictures and table order are unchanged. Filesize and the
header CRC are recomputed. The public RSA envelope is not re-signed.
"""
import struct,zlib

def _u32(d,at):return struct.unpack_from('>I',d,at)[0]

def _header(d):
    if len(d)<88 or _u32(d,0)!=512 or _u32(d,4)!=len(d):raise ValueError('News header bounds')
    if zlib.crc32(d[12:])&0xffffffff!=_u32(d,8):raise ValueError('News CRC mismatch')
    names=['message','topics','topic_table','articles','article_table','sources','source_table','locations','location_table','images','image_table']
    h=dict(zip(names,struct.unpack_from('>11I',d,48)));h['headlines'],h['headline_table']=struct.unpack_from('>II',d,96)
    return h

def _terminated(d,at):
    end=at
    while d[end:end+2]!=b'\0\0':
        end+=2
        if end-at>65536 or end>=len(d):raise ValueError('Unterminated News string')
    return d[at:end].decode('utf-16-be')

def strings(d):
    """Yield (kind, offset_field, size_field_or_None, text) for every text reference."""
    h=_header(d);out=[]
    def sized(kind,off_at,size_at):
        at,size=_u32(d,off_at),_u32(d,size_at)
        if size and at:out.append((kind,off_at,size_at,d[at:at+size].decode('utf-16-be')))
    for i in range(h['articles']):
        base=h['article_table']+44*i;sized('headline',base+32,base+28);sized('article',base+40,base+36)
    for i in range(h['topics']):
        off_at=h['topic_table']+12*i;at=_u32(d,off_at)
        if at:out.append(('topic',off_at,None,_terminated(d,at)))
    for i in range(h['sources']):
        base=h['source_table']+28*i;sized('source',base+16,base+12);sized('copyright',base+24,base+20)
    for i in range(h['locations']):
        off_at=h['location_table']+16*i;at=_u32(d,off_at)
        if at:out.append(('location',off_at,None,_terminated(d,at)))
    for i in range(h['images']):
        base=h['image_table']+24*i;sized('credit',base+4,base)
        # WiiLink writes CaptionSize as half the UTF-16 unit count; read to the terminator.
        at=_u32(d,base+12)
        if at:out.append(('caption',base+12,base+8,_terminated(d,at)))
    for i in range(h['headlines']):
        base=h['headline_table']+8*i;sized('wii_menu_headline',base+4,base)
    return out

def localize(d,mapping):
    """Return (data, record). `mapping` maps source text to Korean; all text must be covered."""
    refs=strings(d);missing=sorted({t for _,_,_,t in refs if t.strip() and t not in mapping})
    if missing:raise ValueError(f'{len(missing)} News strings lack Korean text')
    out=bytearray(d);placed={}
    for kind,off_at,size_at,text in refs:
        if not text.strip():continue
        target=mapping[text]
        if target not in placed:
            while len(out)%4:out+=b'\0'
            placed[target]=len(out);out+=target.encode('utf-16-be')+b'\0\0'
        struct.pack_into('>I',out,off_at,placed[target])
        units=len(target.encode('utf-16-be'))//2
        if size_at is not None:struct.pack_into('>I',out,size_at,units//2 if kind=='caption'else units*2)
    while len(out)%4:out+=b'\0'
    struct.pack_into('>I',out,4,len(out));struct.pack_into('>I',out,8,zlib.crc32(out[12:])&0xffffffff)
    return bytes(out),dict(strings=len(refs),unique_korean=len(placed),appended_bytes=len(out)-len(d),numbers_and_pictures_preserved=True,not_server_signed=True)

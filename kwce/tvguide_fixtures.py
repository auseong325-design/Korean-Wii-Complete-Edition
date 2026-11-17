"""Own synthetic TV Guide HDPK resources. No real programmes or console data."""
import struct

def pack_hdp(data,relocations,roots):
    data=bytes(data);relocations=tuple(relocations)
    if not data or len(data)%4 or len(data)>1024*1024:raise ValueError('HDPK data bounds')
    if tuple(sorted(set(relocations)))!=relocations:raise ValueError('HDPK relocation order')
    for at in relocations:
        if at%4 or not 0<=at<=len(data)-4 or not 0<=struct.unpack_from('>I',data,at)[0]<len(data):raise ValueError('HDPK relocation bounds')
    names=bytearray();table=bytearray()
    for name,at in roots.items():
        if not name.isascii() or not name.isidentifier() or not 0<=at<len(data):raise ValueError('HDPK root bounds')
        table+=struct.pack('>II',at,len(names));names+=name.encode()+b'\0'
    total=32+len(data)+4*len(relocations)+len(table)+len(names)
    return b'HDPK001B'+struct.pack('>6I',total,len(data),len(relocations),len(roots),len(names),0)+data+b''.join(struct.pack('>I',v)for v in relocations)+table+names

def unpack_hdp(raw):
    if len(raw)<32 or raw[:8]!=b'HDPK001B':raise ValueError('HDPK identity')
    total,size,nrel,nroot,namesize,reserved=struct.unpack_from('>6I',raw,8)
    if total!=len(raw)or total!=32+size+4*nrel+8*nroot+namesize or size>1024*1024 or nroot>128:raise ValueError('HDPK layout bounds')
    data=raw[32:32+size];rels=tuple(struct.unpack_from('>I',raw,32+size+i*4)[0]for i in range(nrel));base=32+size+4*nrel;names=raw[base+8*nroot:];roots={}
    for i in range(nroot):
        at,noff=struct.unpack_from('>II',raw,base+8*i)
        if not 0<=noff<len(names)or b'\0'not in names[noff:]:raise ValueError('HDPK root name bounds')
        name=names[noff:names.index(0,noff)].decode('ascii')
        if name in roots:raise ValueError('HDPK duplicate root')
        roots[name]=at
    if pack_hdp(data,rels,roots)!=raw:raise ValueError('HDPK noncanonical resource')
    return data,rels,roots

def header_fixture(schema=1):
    # Basic record: one own demonstration station, 47 selectable local areas.
    # All names/programmes are fabricated. Areas follow the original ID range.
    data=bytearray(0x78);rel=[]
    def reserve(size):
        at=len(data);data.extend(bytes(size));return at
    def pointer(at,value):struct.pack_into('>I',data,at,value);rel.append(at)
    def text(value):
        at=len(data);data.extend(value.encode('utf-16-be')+b'\0\0');data.extend(bytes(-len(data)%4));return at
    stations=reserve(12);areas=reserve(47*16);lineup=reserve(12)
    struct.pack_into('>I',data,0,1);struct.pack_into('>I',data,0x34,1);pointer(0x38,stations)
    struct.pack_into('>I',data,0x3c,47);pointer(0x40,areas)
    struct.pack_into('>I',data,stations,1);pointer(stations+4,text('시험 방송'));data[stations+8]=1
    struct.pack_into('>IHHB',data,lineup,1,1,1,1)
    for i in range(47):
        at=areas+16*i;struct.pack_into('>HBBI',data,at,i if schema>=3 else i+1,i+1,0,1)
        pointer(at+8,text('시험 지역 %02d'%(i+1)));pointer(at+12,lineup)
    if schema not in(1,2,3):raise ValueError('Unknown TV header schema')
    result=pack_hdp(data,sorted(rel),{'basi'if schema==1 else'main':0});unpack_hdp(result);return result

def compressed_header(schema=1):
    from .channels import compress_lz10,load_library
    raw=header_fixture(schema);packed=compress_lz10(raw);load_library()
    from libWiiPy.archive import decompress_lz77
    if decompress_lz77(packed)!=raw:raise ValueError('TV header compression roundtrip')
    return packed

def encrypted_header(game_module,schema=1):
    # This is the title's game-wide module, never a console identity/key.
    # Bytes are handled locally and never returned separately or logged.
    # The pinned Dolphin parses the envelope but does not verify its RSA field;
    # this fixture therefore establishes emulator parsing only, not authenticity.
    if len(game_module)!=544:raise ValueError('TV game module layout differs')
    from Crypto.Cipher import AES
    payload=compressed_header(schema);iv=bytes(16);cipher=AES.new(game_module[512:528],AES.MODE_OFB,iv=iv);encrypted=cipher.encrypt(payload)
    if AES.new(game_module[512:528],AES.MODE_OFB,iv=iv).decrypt(encrypted)!=payload:raise ValueError('TV envelope roundtrip')
    return b'WC24'+struct.pack('>II',1,0)+b'\x01'+bytes(35)+iv+bytes(256)+encrypted



# --- wave 3: synthetic EPG schedule / string resources ----------------------
# header.bin alone leaves the channel at the region-selection screen; the
# schedule state (DOL 0x8039cc4c / 0x8039cca4) then fetches epg.bin and str.bin.
# Both are HDPK blobs under the same 'main' root as header.bin and are validated
# by EpgValidate (0x803a2950) and StrValidate (0x803a2cac). EpgValidate cross-
# references the header station table, so every EPG station id must exist there.
# All programmes/stations are fabricated; no real broadcast schedule is used.

def epg_payload(station_ids=(1,)):
    """Own synthetic EPG HDPK: one programme list per (header) station id."""
    if not station_ids:raise ValueError('TV EPG needs at least one station')
    data=bytearray(0x2c);rel=[]
    def reserve(size):
        at=len(data);data.extend(bytes(size));return at
    def pointer(at,value):
        if not 0<value<len(data):raise ValueError('TV EPG pointer bounds')
        struct.pack_into('>I',data,at,value);rel.append(at)
    def text(value):
        at=len(data);data.extend(value.encode('utf-16-be')+b'\0\0');data.extend(bytes(-len(data)%4));return at
    # Station-programme table: stride 0xc records {id, count, programmes ptr}.
    table=reserve(0xc*len(station_ids))
    struct.pack_into('>I',data,0x1c,len(station_ids));pointer(0x20,table)
    struct.pack_into('>I',data,0x24,0)  # optional second table left empty (skipped)
    for i,sid in enumerate(station_ids):
        # One programme block; +0 start marker, +4 must be non-zero (title id),
        # +8 title pointer. Validator only requires +4 != 0.
        block=reserve(0x10);struct.pack_into('>II',data,block,0,1);pointer(block+8,text('시험 프로그램'))
        rec=table+0xc*i
        struct.pack_into('>II',data,rec,sid,1);pointer(rec+8,block)
    result=pack_hdp(data,sorted(rel),{'main':0});unpack_hdp(result);return result

def str_payload(strings=()):
    """Own synthetic string HDPK. count@0x18 / table@0x1c (stride 4 pointers)."""
    data=bytearray(0x20);rel=[]
    def pointer(at,value):struct.pack_into('>I',data,at,value);rel.append(at)
    def text(value):
        at=len(data);data.extend(value.encode('utf-16-be')+b'\0\0');data.extend(bytes(-len(data)%4));return at
    if strings:
        table=len(data);data.extend(bytes(4*len(strings)))
        struct.pack_into('>I',data,0x18,len(strings));pointer(0x1c,table)
        for i,s in enumerate(strings):pointer(table+4*i,text(s))
    # else: empty table (count 0) which StrValidate accepts.
    result=pack_hdp(data,sorted(rel),{'main':0});unpack_hdp(result);return result

def compressed_resource(raw):
    from .channels import compress_lz10,load_library
    packed=compress_lz10(raw);load_library()
    from libWiiPy.archive import decompress_lz77
    if decompress_lz77(packed)!=raw:raise ValueError('TV resource compression roundtrip')
    return packed

def encrypted_resource(game_module,raw):
    # Same WC24 envelope as encrypted_header, for any HDPK resource (epg/str).
    if len(game_module)!=544:raise ValueError('TV game module layout differs')
    from Crypto.Cipher import AES
    payload=compressed_resource(raw);iv=bytes(16);cipher=AES.new(game_module[512:528],AES.MODE_OFB,iv=iv);encrypted=cipher.encrypt(payload)
    if AES.new(game_module[512:528],AES.MODE_OFB,iv=iv).decrypt(encrypted)!=payload:raise ValueError('TV envelope roundtrip')
    return b'WC24'+struct.pack('>II',1,0)+b'\x01'+bytes(35)+iv+bytes(256)+encrypted

def feed_v7_resources(game_module,schema=3,station_ids=(1,)):
    """The three encrypted resources served by local-feed-v7 (header+epg+str)."""
    return dict(header=encrypted_header(game_module,schema=schema),
                epg=encrypted_resource(game_module,epg_payload(station_ids)),
                string=encrypted_resource(game_module,str_payload()))

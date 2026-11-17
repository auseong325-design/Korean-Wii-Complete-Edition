"""Bounded local weather UI fixtures. No network, credentials or signatures."""
import struct,zlib
from .channels import load_library,compress_lz10

SCENARIOS=('public','clock-pm','expired','no-service','missing-location')


def fixture(payload,kind,scenario,missing_key=None):
    if kind not in ('forecast','short') or scenario not in SCENARIOS:raise ValueError('Unknown UI fixture')
    load_library();from libWiiPy.archive import decompress_lz77
    data=bytearray(decompress_lz77(payload));minimum=88 if kind=='forecast'else 36
    if len(data)<minimum or struct.unpack_from('>II',data)!=(0,len(data))or data[20]!=136 or data[24]!=1:
        raise ValueError('Unexpected weather fixture identity')
    if zlib.crc32(data[12:])&0xffffffff!=struct.unpack_from('>I',data,8)[0]:raise ValueError('Fixture CRC')
    shift=720 if scenario=='clock-pm'else 0
    if shift:
        for at in (12,16):struct.pack_into('>I',data,at,struct.unpack_from('>I',data,at)[0]+shift)
    count,offset=struct.unpack_from('>II',data,32 if kind=='forecast'else 28)
    stride=128 if kind=='forecast'else 24
    if not 0<count<10000 or offset<minimum or offset+count*stride>len(data):raise ValueError('Fixture table bounds')
    for i in range(count):
        at=offset+i*stride
        if shift:
            for field in (4,8):struct.pack_into('>I',data,at+field,struct.unpack_from('>I',data,at+field)[0]+shift)
        if scenario=='no-service':
            fields=[16,18,20,22,24,44,46,48,50,52,*range(72,128,8)]if kind=='forecast'else[12]
            for field in fields:struct.pack_into('>H',data,at+field,0xffff)
            if kind=='forecast':data[at+41]=data[at+69]=231
    if scenario=='missing-location':
        if missing_key is None or len(missing_key)!=4:raise ValueError('Explicit public city key required')
        rows=[bytes(data[offset+i*stride:offset+(i+1)*stride])for i in range(count)]
        kept=[r for r in rows if r[:4]!=missing_key]
        if len(kept)!=len(rows)-1:raise ValueError('Expected one public city record')
        data[offset:offset+count*stride]=b''.join(kept)+bytes(stride)
        struct.pack_into('>I',data,32 if kind=='forecast'else 28,count-1)
    struct.pack_into('>I',data,8,zlib.crc32(data[12:])&0xffffffff)
    return compress_lz10(bytes(data))


def public_city_key(payload,name='울산'):
    load_library();from libWiiPy.archive import decompress_lz77
    data=decompress_lz77(payload);count,offset=struct.unpack_from('>II',data,80)
    if count>10000 or offset<88 or offset+count*24>len(data):raise ValueError('Public location bounds')
    hits=[]
    for i in range(count):
        at=offset+i*24;pos=struct.unpack_from('>I',data,at+4)[0]
        if not 88<=pos<len(data)-2 or pos%2:raise ValueError('Public city string bounds')
        end=pos
        while end+2<=len(data) and data[end:end+2]!=b'\0\0'and end-pos<256:end+=2
        if data[pos:end].decode('utf-16-be')==name:hits.append(data[at:at+4])
    if len(hits)!=1:raise ValueError('Expected unique public review city')
    return hits[0]

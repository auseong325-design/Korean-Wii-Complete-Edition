"""Local Korean overlay for public WiiLink Forecast payloads, never raw WADs.

Edits only bounded UTF-16 string slots referenced by the official location
and condition tables. Numeric forecasts, coordinates and all offsets stay
unchanged. The public WC24 download is preserved separately, not re-signed.
"""
import hashlib,struct,zlib
from .channels import compress_lz10,load_library

def localize_forecast(compressed,mapping):
    load_library();from libWiiPy.archive import decompress_lz77
    data=decompress_lz77(compressed)
    if len(data)<88 or len(data)>4*1024*1024 or struct.unpack_from('>II',data,0)!=(0,len(data)):raise ValueError('Forecast header bounds')
    if data[20]!=136 or data[24]!=1 or(zlib.crc32(data[12:])&0xffffffff)!=struct.unpack_from('>I',data,8)[0]:raise ValueError('Forecast country/language/CRC mismatch')
    positions=set()
    for count_at,offset_at,stride,fields in [(48,52,8,[4]),(56,60,8,[4]),(80,84,24,[4,8,12])]:
        count=struct.unpack_from('>I',data,count_at)[0];offset=struct.unpack_from('>I',data,offset_at)[0]
        if count==0 and offset==0:continue
        if count>10000 or offset<88 or offset+count*stride>len(data):raise ValueError('Forecast table bounds')
        for index in range(count):
            for field in fields:positions.add(struct.unpack_from('>I',data,offset+index*stride+field)[0])
    result=bytearray(data);translated=0;modified=[]
    for at in sorted(positions):
        if at==0:continue  # Optional international region labels may be absent.
        if at<88 or at%2 or at>=len(data):raise ValueError('Forecast string pointer bounds')
        end=at
        while end+2<=len(data)and data[end:end+2]!=b'\0\0':
            end+=2
            if end-at>4096:raise ValueError('Forecast unterminated string')
        if end+2>len(data):raise ValueError('Forecast string outside payload')
        text=data[at:end].decode('utf-16-be');replacement=mapping.get(text)
        if replacement is None:continue
        encoded=replacement.encode('utf-16-be')
        if len(encoded)>end-at:raise ValueError('Korean overlay exceeds original string slot')
        result[at:end]=encoded+bytes(end-at-len(encoded));translated+=1;modified.append((at,end))
    struct.pack_into('>I',result,8,zlib.crc32(result[12:])&0xffffffff)
    # Every changed byte must be in an explicitly referenced string or CRC.
    if any(a!=b and not(8<=i<12 or any(lo<=i<hi for lo,hi in modified))for i,(a,b)in enumerate(zip(data,result))):raise ValueError('Forecast numeric data changed')
    return compress_lz10(bytes(result)),dict(translated_unique_strings=translated,numeric_data_and_offsets_preserved=True,CRC_valid=True,source_payload_sha256=hashlib.sha256(compressed).hexdigest(),localized=True,not_a_server_signed_download=True)

def forecast_mapping():
    """Dynamic UI strings plus the international place-name table."""
    import json
    from .channels import ROOT
    mapping=json.loads((ROOT/'configs/forecast-dynamic-ko.json').read_text(encoding='utf-8'))['strings']
    mapping.update(json.loads((ROOT/'configs/forecast-places-ko.json').read_text(encoding='utf-8'))['strings'])
    return mapping

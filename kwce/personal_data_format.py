"""pd.dat (Set Personal Data) plaintext layout and encryption, for tests only.

Layout follows WiiLink's kaitai description (source/pd-kaitai-struct/pd.ksy)
and the byte offsets SPD writes (source/channel/pd_info.cpp). The AES key/IV
templates are read from the pinned public WiiLink source at run time and are
never printed; callers pass a device ID explicitly (synthetic IDs in unit
tests, Dolphin's public default ID for the isolated test profile). Never pass
a real console's ID.
"""
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'workspace/channels/personal-data/references/set-personal-data-18fa5a7d'
LENGTH=0x4000
PATH='/title/00010008/4843434a/data/nocopy/pd.dat'
DOLPHIN_DEFAULT_DEVICE_ID=0x0403AC68  # Dolphin 2609a Source/Core/Core/IOS/IOSC.cpp DEFAULT_DEVICE_ID (public)
# name: (offset, bytes) -- UTF-16BE, NUL padded; offsets are odd by design.
FIELDS={
    'last_name':(207,64),'first_name':(271,64),'zip_code':(335,34),'state':(371,64),'city':(435,64),
    'home_address':(499,256),'apartment_number':(755,256),'phone_number':(1011,64),'email_address':(1075,256),
    'kana_last_name':(9723,64),'kana_first_name':(9787,64)}
PIN_MAGIC=(5,12);PIN=(25,8)
TEMPLATE_LENGTH=16368

def _array(text,name):
    body=text.split(name,1)[1].split('{',1)[1].split('}',1)[0]
    return bytes(int(x,16)for x in re.findall(r'0x([0-9A-Fa-f]{2})\b',body))

def key_iv(device_id,source=SOURCE):
    if not 0<=device_id<2**32:raise ValueError('Device ID range')
    text=(source/'source/channel/pd_data.h').read_text(encoding='latin-1')
    key=bytearray(_array(text,'PERSONAL_DATA_KEY[32]'));iv=bytearray(_array(text,'PERSONAL_DATA_IV[16]'))
    if len(key)!=32 or len(iv)!=16 or any(key[i]for i in(7,15,23,31))or any(iv[12:]):raise ValueError('Pinned PD key template differs')
    ident=device_id.to_bytes(4,'big')
    for slot,byte in zip((7,15,23,31),ident):key[slot]=byte
    iv[12:16]=ident
    return bytes(key),bytes(iv)

def encrypt(plain,device_id):
    from Crypto.Cipher import AES
    if len(plain)!=LENGTH:raise ValueError('pd.dat length')
    key,iv=key_iv(device_id);return AES.new(key,AES.MODE_CBC,iv).encrypt(plain)

def decrypt(data,device_id):
    from Crypto.Cipher import AES
    if len(data)!=LENGTH:raise ValueError('pd.dat length')
    key,iv=key_iv(device_id);return AES.new(key,AES.MODE_CBC,iv).decrypt(data)

def check(plain):
    """Raise unless the plaintext has the PDFF v2 / INFO / KANA structure."""
    if len(plain)!=LENGTH:raise ValueError('pd.dat length')
    if plain[:5]!=b'PDFF\x02':raise ValueError('PDFF header')
    if plain[128:132]!=b'INFO'or int.from_bytes(plain[132:136],'big')!=0x256F:raise ValueError('INFO block')
    if plain[9711:9715]!=b'KANA'or int.from_bytes(plain[9715:9719],'big')!=0x40C:raise ValueError('KANA block')
    return True

def fields(plain):
    check(plain);out={}
    for name,(at,size) in FIELDS.items():
        raw=plain[at:at+size];text=raw.decode('utf-16-be');out[name]=text.split('\0',1)[0]
    pin=plain[PIN[0]:PIN[0]+PIN[1]].decode('utf-16-be').split('\0',1)[0]
    out['pin_protected']=any(plain[PIN_MAGIC[0]:PIN_MAGIC[0]+PIN_MAGIC[1]]);out['pin_length']=len(pin)
    return out

def put(plain,name,value):
    at,size=FIELDS[name];raw=value.encode('utf-16-be')
    if len(raw)>=size:raise ValueError(name+' exceeds its field')
    out=bytearray(plain);out[at:at+size]=raw+bytes(size-len(raw));return bytes(out)

def korean_template(upstream):
    """Clear WiiLink's sample person/address values and pad to the file length.

    Upstream copies 0x4000 bytes from a 16,368-byte array (reads 16 bytes past
    it); the padded template makes those bytes zero. Header, block sizes,
    presets and timestamps are kept byte for byte.
    """
    if len(upstream)!=TEMPLATE_LENGTH or upstream[:5]!=b'PDFF\x02':raise ValueError('Pinned pd template differs')
    plain=upstream+bytes(LENGTH-TEMPLATE_LENGTH)
    for name in FIELDS:plain=put(plain,name,'')
    check(plain)
    changed=[(a,a+s)for a,s in FIELDS.values()]
    return plain,dict(cleared_fields=sorted(FIELDS),cleared_ranges=changed,padded_bytes=LENGTH-TEMPLATE_LENGTH)

FICTIONAL=dict(last_name='홍',first_name='길동',zip_code='00000',state='가상도',city='예시시',home_address='테스트로 1',
               apartment_number='101동 1001호',phone_number='0100000000',email_address='hong@example.com')

def fictional_sample(template):
    """Template filled with obviously fictional Korean values (no real person/address)."""
    plain=template
    for name,value in FICTIONAL.items():plain=put(plain,name,value)
    plain=put(plain,'kana_last_name',FICTIONAL['last_name']);plain=put(plain,'kana_first_name',FICTIONAL['first_name'])
    check(plain);return plain

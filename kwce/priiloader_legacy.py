"""Model the byte-token parser in official Priiloader 0.8.2, not a u32 parser.

Reference: DacoTaco/priiloader, tag 0.8.2, priiloader/source/hacks.cpp.
Its sscanf('%x')/size/fallthrough code drops leading zero bytes, including
ALL bytes of 0x00000000. A pair is counted only when both vectors are nonempty.
The installed version is unknown; its reported EOF matches this grammar.
"""
import re,struct


def token_bytes(value):
    if not re.fullmatch(r'0x[0-9a-fA-F]{1,8}',value):
        raise ValueError('Legacy Priiloader: invalid hexadecimal token')
    number=int(value,16)
    return number.to_bytes((number.bit_length()+7)//8,'big')


def parse(raw):
    if isinstance(raw,str):raw=raw.encode('ascii')
    if not raw or b'\0'in raw or raw.replace(b'\r\n',b'').find(b'\n')>=0:
        raise ValueError('Legacy Priiloader: expected nonempty CRLF text')
    text=raw.decode('ascii');lines=text.split('\r\n')
    if lines[-1]=='':lines.pop()
    entries=[];at=0
    def line():
        nonlocal at
        if at>=len(lines):raise ValueError(f'Legacy Priiloader: unexpected EOF @ line {at+1}')
        value=lines[at];at+=1;return value
    def setting(key):
        value=line()
        if not re.fullmatch(key+r'=[1-9][0-9]*',value):
            raise ValueError(f'Legacy Priiloader: expected {key} @ line {at}')
        return int(value.split('=')[1])
    while at<len(lines):
        name=line()
        if not re.fullmatch(r'\[[^\[\]\r\n]+\]',name):
            raise ValueError(f'Legacy Priiloader: expected section @ line {at}')
        maximum=setting('maxversion');minimum=setting('minversion');amount=setting('amount')
        pairs=[];hash_data=patch_data=b''
        while True:
            # Original parser finalizes a pair before handling the next line/EOF.
            if hash_data and patch_data:
                pairs.append((hash_data,patch_data));hash_data=patch_data=b''
            if len(pairs)==amount:break
            value=line()
            if value.startswith('hash=') and not hash_data:
                hash_data=b''.join(token_bytes(t)for t in value[5:].split(','))
            elif value.startswith('patch=') and hash_data and not patch_data:
                patch_data=b''.join(token_bytes(t)for t in value[6:].split(','))
            else:raise ValueError(f'Legacy Priiloader: expected hash/patch @ line {at}')
        entries.append(dict(name=name[1:-1],maximum=maximum,minimum=minimum,pairs=pairs))
    return entries


def apply(menu,entries):
    """Apply actual variable-width bytes without shrinking the executable."""
    out=bytearray(menu)
    for entry in entries:
        for needle,patch in entry['pairs']:
            at=out.find(needle)
            if at<0:raise ValueError('Legacy Priiloader: hash not found')
            if at+len(patch)>len(out):raise ValueError('Legacy Priiloader: patch exceeds executable')
            out[at:at+len(patch)]=patch
    return bytes(out)

def apply_streaming(menu,entries):
    """Model Priiloader's actual forward cursor, reset once per hack section.

    A missing match consumes the remainder of the binary in Priiloader; reject
    the profile instead of silently leaving that and later patches unapplied.
    """
    out=bytearray(menu)
    for entry in entries:
        cursor=0
        for number,(needle,patch) in enumerate(entry['pairs'],1):
            at=out.find(needle,cursor)
            if at<0:raise ValueError(f"Priiloader forward search failed: {entry['name']} pair {number}")
            if at+len(patch)>len(out):raise ValueError('Priiloader patch exceeds executable')
            out[at:at+len(patch)]=patch
            cursor=at
    return bytes(out)


def packed_tokens(data):
    """Encode bytes as <=4-byte hex tokens without a zero-leading token."""
    tokens=[];at=0
    while at<len(data):
        if data[at]==0:raise ValueError('Legacy parser cannot encode a zero-leading run')
        for count in range(min(4,len(data)-at),0,-1):
            if at+count==len(data) or data[at+count]!=0:break
        else:raise ValueError('Legacy parser cannot encode a long zero run')
        tokens.append(int.from_bytes(data[at:at+count],'big'));at+=count
    return tokens

def checked_ini(menu,entries,*,packed=False):
    """Refuse syntax errors AND byte loss before exporting a new SD package."""
    from .priiloader_hacks import ini,apply as word_apply
    encoded=entries
    if packed:
        encoded=[]
        for entry in entries:
            row=dict(entry);row['pairs']=[]
            for h,p in entry['pairs']:
                row['pairs'].append((packed_tokens(struct.pack(f'>{len(h)}I',*h)),packed_tokens(struct.pack(f'>{len(p)}I',*p))))
            encoded.append(row)
    raw=ini(encoded).replace('\n','\r\n').encode('ascii')
    decoded=parse(raw)
    # Check widths individually; a later overlapping patch must not mask loss.
    for source,actual in zip(entries,decoded):
        for (h,p),(hb,pb)in zip(source['pairs'],actual['pairs']):
            if hb!=struct.pack(f'>{len(h)}I',*h) or pb!=struct.pack(f'>{len(p)}I',*p):
                raise ValueError('Legacy Priiloader: hexadecimal tokens lose leading zero bytes')
    if apply(menu,decoded)!=word_apply(menu,entries):
        raise ValueError('Legacy Priiloader: actual patch bytes differ')
    return raw

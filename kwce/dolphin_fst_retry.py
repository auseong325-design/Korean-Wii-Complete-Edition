"""Bounded retry at exactly 2609a HostFileSystem::SaveFst's Rename call.

The final failure still reaches the original panic. No permission changes,
copies, delete fallback, warning suppression or generic rename interception.
Non-leaf x64 code has a proper PE runtime-function/unwind table entry.
"""
import hashlib,struct

BASE_SHA256='eebfe21a6a5704dfd26d71ad87a3c7b5f559b13158eadc8cb3123f6ff4384a93'
CALL=0x3e6a5c
RENAME=0xac8b80

def retry_thunk(address,rename,sleep_slot):
    code=bytearray(bytes.fromhex('5356574883ec204889ce4889d7bb03000000'))
    loop=len(code)
    code+=bytes.fromhex('4889f14889fae8')+struct.pack('<i',rename-(address+len(code)+11))
    code+=bytes.fromhex('84c07500ffcb7400b90a000000ff15')
    code+=struct.pack('<i',sleep_slot-(address+len(code)+4))
    code+=b'\xeb'+struct.pack('b',loop-(len(code)+2))
    end=len(code);code+=bytes.fromhex('4883c4205f5e5bc3')
    # jne success; je exhausted. Offsets are derived from fixed op shapes.
    first=loop+11+2;second=first+4
    code[first+1]=end-(first+2);code[second+1]=end-(second+2)
    return bytes(code)

def patch_fst_retry(data):
    if hashlib.sha256(data).hexdigest()!=BASE_SHA256:raise ValueError('Only locked v5 Dolphin derivative supported')
    pe=struct.unpack_from('<I',data,0x3c)[0];opt=pe+24;section_table=opt+struct.unpack_from('<H',data,pe+20)[0]
    segments=[]
    for i in range(struct.unpack_from('<H',data,pe+6)[0]):
        at=section_table+40*i;size,va,rawsize,raw=struct.unpack_from('<4I',data,at+8)
        segments.append(dict(header=at,size=size,va=va,rawsize=rawsize,raw=raw,name=data[at:at+8].rstrip(b'\0')))
    def offset(rva):
        for s in segments:
            if s['va']<=rva<s['va']+s['rawsize']:return s['raw']+rva-s['va']
        raise ValueError('Unmapped PE address')
    exception,exception_size=struct.unpack_from('<II',data,opt+112+3*8)
    functions=[struct.unpack_from('<III',data,offset(exception)+i)for i in range(0,exception_size,12)]
    if (0x3e6950,0x3e6c28)not in [(a,b)for a,b,c in functions]:raise ValueError('SaveFst function guard mismatch')
    expected=b'\xe8'+struct.pack('<i',RENAME-(CALL+5))+bytes.fromhex('84c00f85')+struct.pack('<i',0x3e6b30-(CALL+13))
    if data[offset(CALL):offset(CALL)+13]!=expected:raise ValueError('FST rename/panic branch guard mismatch')
    imports=struct.unpack_from('<I',data,opt+112+8)[0];sleep_slot=None
    for i in range(1000):
        descriptor=struct.unpack_from('<5I',data,offset(imports)+20*i)
        if not any(descriptor):break
        original,_,_,name,iat=descriptor
        if not original:raise ValueError('Import name table unavailable')
        for j in range(10000):
            value=struct.unpack_from('<Q',data,offset(original)+8*j)[0]
            if not value:break
            if value>>63:continue
            at=offset(value)+2;end=data.index(b'\0',at)
            if data[at:end]==b'Sleep':sleep_slot=iat+8*j
    if sleep_slot is None:raise ValueError('Pinned Sleep import missing')
    text=next(s for s in segments if s['name']==b'.text')
    length=len(retry_thunk(0,RENAME,sleep_slot));at=text['raw']+text['size'];cave=text['va']+text['size']
    if text['size']%16 or text['size']+length>text['rawsize'] or any(x not in [0,0xcc]for x in data[at:at+length]):raise ValueError('Executable tail padding unavailable')
    if any(a<cave+length and cave<b for a,b,c in functions):raise ValueError('Executable tail overlaps a function')
    code=retry_thunk(cave,RENAME,sleep_slot);result=bytearray(data)
    result[at:at+length]=code
    struct.pack_into('<I',result,text['header']+8,text['size']+length)
    result[offset(CALL):offset(CALL)+5]=b'\xe8'+struct.pack('<i',cave-(CALL+5))
    # Three nonvolatile pushes followed by 32-byte shadow space allocation.
    unwind=bytes.fromhex('010704000732037002600130')
    rdata=next(s for s in segments if s['name']==b'.rdata');u=rdata['size']
    if u%4 or u+len(unwind)>rdata['rawsize']:raise ValueError('Unwind padding unavailable')
    if data[rdata['raw']+u:rdata['raw']+u+len(unwind)]!=bytes(len(unwind)):raise ValueError('Unwind padding guard mismatch')
    result[rdata['raw']+u:rdata['raw']+u+len(unwind)]=unwind
    struct.pack_into('<I',result,rdata['header']+8,u+len(unwind))
    pdata=next(s for s in segments if s['name']==b'.pdata')
    if exception!=pdata['va'] or exception_size!=pdata['size'] or exception_size+12>pdata['rawsize']:raise ValueError('Exception table padding unavailable')
    if data[pdata['raw']+exception_size:pdata['raw']+exception_size+12]!=bytes(12):raise ValueError('Exception padding guard mismatch')
    functions.append((cave,cave+length,rdata['va']+u));functions.sort()
    entries=b''.join(struct.pack('<III',*f)for f in functions)
    result[pdata['raw']:pdata['raw']+len(entries)]=entries
    struct.pack_into('<I',result,pdata['header']+8,len(entries));struct.pack_into('<I',result,opt+112+3*8+4,len(entries))
    for s,added in [(text,length),(rdata,len(unwind)),(pdata,12)]:
        if (s['size']+4095)//4096!=(s['size']+added+4095)//4096:raise ValueError('Patch would change mapped section extent')
    return bytes(result),dict(base_sha256=BASE_SHA256,output_sha256=hashlib.sha256(result).hexdigest(),call_rva=hex(CALL),rename_rva=hex(RENAME),thunk_rva=hex(cave),thunk_size=length,sleep_iat_rva=hex(sleep_slot),attempts=3,delay_ms=10,unwind_info_rva=hex(rdata['va']+u),runtime_function_added=True,final_failure_reaches_original_panic=True,scope='HostFileSystem SaveFst only')

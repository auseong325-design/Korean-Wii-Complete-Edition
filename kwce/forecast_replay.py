"""Offline UI diagnostic only: acknowledge prevalidated public cache delivery.

Not a network/service compatibility fix. Only task slots 3/4 are replayed;
the launcher must verify their Forecast identity and VFF payload bytes first.
All other KDDownload calls continue through the original prologue.
"""
import hashlib,struct
BASE='a100419539a7ad5996f99ea39b5471d20beec722b5debae0f4462a9cfa276e05'
ENTRY=0x431240

def patch_cache_replay(data):
    if hashlib.sha256(data).hexdigest()!=BASE:raise ValueError('Only locked v6 runtime supports replay')
    pe=struct.unpack_from('<I',data,0x3c)[0];opt=pe+24;table=opt+struct.unpack_from('<H',data,pe+20)[0];sections=[]
    for i in range(struct.unpack_from('<H',data,pe+6)[0]):
        at=table+40*i;size,va,rs,raw=struct.unpack_from('<4I',data,at+8);sections.append((va,size,raw,rs,data[at:at+8].rstrip(b'\0')))
    def offset(rva):
        for va,size,raw,rs,name in sections:
            if va<=rva<va+min(size,rs):return raw+rva-va
        raise ValueError('Replay PE address outside section')
    exc,size=struct.unpack_from('<II',data,opt+112+24);functions=[struct.unpack_from('<III',data,offset(exc)+i)[:2]for i in range(0,size,12)]
    if(ENTRY,0x431fee)not in functions:raise ValueError('KDDownload function boundary mismatch')
    original=bytes.fromhex('488bc46644894018');at=offset(ENTRY)
    if data[at:at+len(original)]!=original:raise ValueError('KDDownload prologue guard mismatch')
    va,length,raw,rs,_=next(s for s in sections if s[4]==b'.text');cave=None
    for start in range(raw,raw+length-40):
        if data[start:start+40]!=b'\xcc'*40:continue
        rva=va+start-raw
        if not any(a<rva+40 and rva<b for a,b in functions):cave=rva;break
    extend_text=False
    if cave is None:
        cave=va+length;start=raw+length
        if length+40>rs or any(x not in[0,0xcc]for x in data[start:start+40])or(length+4095)//4096!=(length+40+4095)//4096:raise ValueError('Replay leaf padding unavailable')
        extend_text=True
    # cmp dx,3; je success; cmp dx,4; je success; original eight-byte
    # volatile/shadow-space prologue; jmp original+8; xor eax,eax; ret.
    code=bytearray(bytes.fromhex('6683fa0374116683fa04740b')+original+b'\xe9')
    code.extend(struct.pack('<i',ENTRY+8-(cave+len(code)+4)));code.extend(bytes.fromhex('31c0c3'))
    # Derive conditional branch destinations from the actual emitted size.
    success=len(code)-3;code[5]=success-6;code[11]=success-12
    result=bytearray(data)
    if not extend_text:result[offset(cave):offset(cave)+len(code)]=code
    if extend_text:
        # offset() intentionally rejects outside VirtualSize; raw padding is
        # already mapped in the same final page and explicitly guarded above.
        result[raw+length:raw+length+len(code)]=code
        for i in range(len(sections)):
            header=table+40*i
            if data[header:header+8].rstrip(b'\0')==b'.text':struct.pack_into('<I',result,header+8,length+len(code))
    result[at:at+8]=b'\xe9'+struct.pack('<i',cave-(ENTRY+5))+b'\x90'*3
    return bytes(result),dict(base_sha256=BASE,output_sha256=hashlib.sha256(result).hexdigest(),KDDownload_rva=hex(ENTRY),leaf_rva=hex(cave),replayed_task_slots=[3,4],other_tasks_use_original=True,diagnostic_only=True,network_success_verified=False)

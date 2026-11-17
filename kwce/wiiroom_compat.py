"""Title-local resource-language compatibility; system SYSCONF is untouched."""
from .channels import sha256
from .ppc_patch import to_file,assemble,sections

SOURCE='f7efaa12e3f2ef1f24fd9dbce91b7ac8c439bc9d7386f97124d1808aea29d351'
GETTER='342eb87887bb390df7918ef15528d49c0393e52358268d9590e2b717d32b9bac'

def patch_resource_language(raw):
    if sha256(raw)!=SOURCE:raise ValueError('Only pinned English Room executable supported')
    start=to_file(raw,0x80307f50,108);at=to_file(raw,0x80307fac)
    if sha256(raw[start:start+108])!=GETTER:raise ValueError('Resource language getter differs')
    result=bytearray(raw);result[at:at+4]=bytes.fromhex('38600000') # li r3,0: this Japan-only title's resource slot
    return bytes(result),dict(address='0x80307fac',scope='Wii Room executable only',resource_language_slot=0,system_language_unchanged=True,original_getter_sha256=GETTER)

def null_path_blocks(entry,caves,prologue):
    a,b,c=caves
    return {entry:assemble('b guard',entry,{'guard':a}),
            a:assemble('cmpwi r3,0\nbne valid\nb invalid',a,{'valid':b,'invalid':c}),
            b:prologue+assemble('b resume',b+4,{'resume':entry+4})+bytes(4),
            c:assemble('li r3,-101\nblr',c,{})+bytes(4)}

def patch_null_open_diagnostic(raw):
    """Rejected-path diagnostic only; returning -101 stopped client startup."""
    if sha256(raw)!=SOURCE:raise ValueError('Only pinned English Room executable supported')
    entry=0x80302cd0;caves=[0x802cfe64,0x802d0524,0x802d1304]
    at=to_file(raw,entry);prologue=raw[at:at+4]
    if prologue!=bytes.fromhex('9421ffa0'):raise ValueError('nandDelete prologue changed')
    for address in caves:
        offset=to_file(raw,address,12)
        if raw[offset-4:offset]!=bytes.fromhex('4e800020')or raw[offset:offset+12]!=bytes(12):raise ValueError('Alignment padding changed')
        if address.to_bytes(4,'big')in raw:raise ValueError('Padding has an absolute reference')
    # No existing direct branch may land in the proposed padding.
    for index,off,va,size in sections(raw):
        if index>=7:continue
        for pos in range(off,off+size,4):
            word=int.from_bytes(raw[pos:pos+4],'big');opcode=word>>26
            if opcode not in(16,18):continue
            mask,sign=(0xfffc,0x8000)if opcode==16 else(0x3fffffc,0x2000000)
            delta=word&mask
            if delta&sign:delta-=2*sign
            target=delta if word&2 else va+pos-off+delta
            if any(address<=target<address+12 for address in caves):raise ValueError('Padding has a branch reference')
    result=bytearray(raw)
    for address,payload in null_path_blocks(entry,caves,prologue).items():
        at=to_file(raw,address,len(payload));result[at:at+len(payload)]=payload
    return bytes(result),dict(entry=hex(entry),padding=[hex(a)for a in caves],null_result=-101,nonnull_path_unchanged=True,observed_null_call_stack=['80304ab0','80302d44','80302f58','8038a970','802adda8','801bfce4','801c0df8','80006470'])

def normalize_null_path_blocks(entry,caves,prologue):
    blocks=null_path_blocks(entry,caves,prologue);a,b,c=caves
    # The existing path normalizer treats an empty string as the current
    # title directory. Express that fallback as a valid terminated string,
    # rather than relying on Dolphin's invalid read from address zero.
    empty=b+8;hi=(empty+0x8000)>>16;lo=empty&65535;lo=lo-65536 if lo&0x8000 else lo
    blocks[c]=assemble(f'lis r3,{hi}\naddi r3,r3,{lo}\nb valid',c,{'valid':b})
    return blocks

def patch_null_path_compat(raw):
    checked,record=patch_null_open_diagnostic(raw)
    entry=0x80302cd0;caves=[0x802cfe64,0x802d0524,0x802d1304];result=bytearray(raw)
    for address,payload in normalize_null_path_blocks(entry,caves,raw[to_file(raw,entry):to_file(raw,entry)+4]).items():
        at=to_file(raw,address,len(payload));result[at:at+len(payload)]=payload
    record.pop('null_result');record.update(null_path='valid empty string for existing current-title-directory fallback',filesystem_result_unchanged=True,diagnostic_reject_failed=True)
    return bytes(result),record

def patch_null_open_missing(raw):
    """Reject NULL NANDOpen input as missing; no path substitution or IO.

    The reviewed routine takes an open mode and calls strlen(path) before IOS.
    Older notes called this entry nandDelete; its instructions show an open.
    Non-NULL inputs keep the exact original prologue and filesystem behavior.
    """
    checked,record=patch_null_open_diagnostic(raw)
    entry=0x80302cd0;caves=[0x802cfe64,0x802d0524,0x802d1304]
    result=bytearray(checked);payload=assemble('li r3,-12\nblr',caves[2],{})+bytes(4)
    at=to_file(raw,caves[2],len(payload));result[at:at+len(payload)]=payload
    record.update(null_result=-12,function='NAND open common',null_path='missing file; return before strlen/IOS',
                  nonnull_path_unchanged=True,filesystem_io_on_null=False,hardware_verified=False)
    return bytes(result),record

def patch_korean_area(raw):
    """KOR area6 -> JPN0 inside this Japan-only title, at SCGetArea return.

    The SPD initializer supports only JPN/USA/EUR paths and passes NULL for6.
    This keeps its native asynchronous open/callback, without replacing paths,
    altering NAND results or modifying any console setting/personal data.
    """
    _,review=patch_null_open_diagnostic(raw) # identity/unused-padding review only
    entry=0x803087bc;resume=entry+4;a,b,c=[0x802cfe64,0x802d0524,0x802d1304]
    at=to_file(raw,entry)
    if raw[at:at+4]!=bytes.fromhex('80010024'):raise ValueError('SCGetArea epilogue changed')
    blocks={entry:assemble('b guard',entry,{'guard':a}),
        a:assemble('cmpwi r3,6\nbeq korean\nb restore',a,{'korean':b,'restore':c}),
        b:assemble('li r3,0\nb restore',b,{'restore':c})+bytes(4),
        c:raw[at:at+4]+assemble('b resume',c+4,{'resume':resume})+bytes(4)}
    result=bytearray(raw)
    for address,payload in blocks.items():
        pos=to_file(raw,address,len(payload));result[pos:pos+len(payload)]=payload
    return bytes(result),dict(entry=hex(entry),function='SCGetArea return, Wii Room only',
        source_area=6,resource_area=0,other_areas_unchanged=True,
        native_nand_code_preserved=True,personal_data_bytes_unchanged=True,
        console_region_language_country_unchanged=True,padding=review['padding'],hardware_verified=False)

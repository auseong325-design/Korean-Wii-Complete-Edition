"""2609a-only offline derivative for MIOS loading and Wii IPC callbacks.

WII_IPC.cpp calls GetIOS()->UpdateIPC() while MIOS construction runs with
System::GetIOS()==nullptr. A leaf thunk returns for nullptr and tail-jumps
to the original method otherwise. ElfReader also compares a virtual address
against the physical MEM1 size, skipping every MIOS PPC segment. Its physical
address branch now clears bit 31 instead of setting it. CopyToEmu/Memset accept
both aliases; the MEM1 check then excludes ARM/MEM2 correctly. Upstream stays intact.
"""
import hashlib,struct

BASE_SHA256='17b01a8629d865378a45e58d5fcebf9dcc3f7919c719130a4ffdd1ca2b27b635'
CALLS=(0x3d1b9e,0x3d1c10,0x3d1cef)
TARGET=0x3423d0
ELF_ADDRESS=0x41bd64
VI_REGION=0x3aaf65

def patch_mios_ipc(data):
    if hashlib.sha256(data).hexdigest()!=BASE_SHA256:raise ValueError('Only frozen Dolphin 2609a x64 supported')
    pe=struct.unpack_from('<I',data,0x3c)[0];opt=pe+24;sections=opt+struct.unpack_from('<H',data,pe+20)[0]
    spans=[]
    for i in range(struct.unpack_from('<H',data,pe+6)[0]):
        at=sections+40*i;size,va,rawsize,raw=struct.unpack_from('<4I',data,at+8)
        spans.append((va,size,raw,rawsize,data[at:at+8].rstrip(b'\0')))
    def offset(rva):
        for va,size,raw,rawsize,name in spans:
            if va<=rva<va+min(size,rawsize):return raw+rva-va
        raise ValueError('Unmapped PE RVA')
    exception_rva,exception_size=struct.unpack_from('<II',data,opt+112+3*8)
    exc=offset(exception_rva)
    functions=[struct.unpack_from('<III',data,exc+i)[:2] for i in range(0,exception_size,12)]
    text=next(s for s in spans if s[4]==b'.text');va,size,raw,rawsize,_=text
    used=[]
    def find_cave(length):
        start=0
        while True:
            at=data.find(b'\xcc'*length,raw+start,raw+rawsize)
            if at<0:raise ValueError('No guarded executable alignment padding')
            rva=va+at-raw
            if not any(a<rva+length and rva<b for a,b in functions+used):
                used.append((rva,rva+length));return rva
            start=at-raw+1
    cave=find_cave(11)
    result=bytearray(data)
    # test rcx,rcx; je ret; jmp UpdateIPC; ret
    stub=b'\x48\x85\xc9\x74\x05\xe9'+struct.pack('<i',TARGET-(cave+10))+b'\xc3'
    result[offset(cave):offset(cave)+11]=stub
    for call in CALLS:
        off=offset(call)
        expected=b'\xe8'+struct.pack('<i',TARGET-(call+5))
        if data[off:off+5]!=expected:raise ValueError('Wii IPC call guard mismatch')
        result[off:off+5]=b'\xe8'+struct.pack('<i',cave-(call+5))
    off=offset(ELF_ADDRESS)
    expected=bytes.fromhex('0fbaeb1feb048b5c3e084584ff740a413b5e500f83da000000')
    if data[off:off+len(expected)]!=expected:raise ValueError('ELF physical address branch guard mismatch')
    # bts ebx,31 -> btr ebx,31. The copied bytes and physical destination agree.
    result[off:off+4]=bytes.fromhex('0fbaf31f')
    # NTSC-K falls back to NTSC-J for GameCube (DiscIO/Enums.h). Preset's
    # NTSC-J cable bit otherwise stays false across the Wii -> MIOS transition,
    # making the GC SDK reject valid Shift-JIS cards. Preserve Wii locale data.
    off=offset(VI_REGION)
    if data[off:off+11]!=bytes.fromhex('8bce85ff7505b902000000'):raise ValueError('VI region branch guard mismatch')
    vi_cave=find_cave(15)
    stub=bytes.fromhex('33c983e7fb0f94c901c9')+b'\xe9'+struct.pack('<i',(VI_REGION+11)-(vi_cave+15))
    result[offset(vi_cave):offset(vi_cave)+15]=stub
    result[off:off+6]=b'\xe9'+struct.pack('<i',vi_cave-(VI_REGION+5))+b'\x90'
    return bytes(result),dict(base_sha256=BASE_SHA256,output_sha256=hashlib.sha256(result).hexdigest(),guarded_calls=[hex(x) for x in CALLS],thunk_rva=hex(cave),elf_physical_address_rva=hex(ELF_ADDRESS),elf_address_mask='0x7fffffff',vi_region_rva=hex(VI_REGION),vi_thunk_rva=hex(vi_cave),gc_japanese_region_fallback=[0,4],reason='physical MEM1 range check, null IOS guard, NTSC-K GC font/card encoding fallback',upstream_binary_unchanged=True)

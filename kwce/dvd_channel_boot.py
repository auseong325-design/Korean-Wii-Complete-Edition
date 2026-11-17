"""Adapt a standalone homebrew DOL to ES's fixed 0x80003400 channel entry."""
import hashlib,struct

ENTRY=0x80003400

def channel_boot(dol):
    if len(dol)<0x100:raise ValueError('DOL header missing')
    target=struct.unpack_from('>I',dol,0xe0)[0];free=None
    if target==ENTRY:return bytes(dol),dict(required=False,source_sha256=hashlib.sha256(dol).hexdigest())
    for i in range(18):
        off=struct.unpack_from('>I',dol,4*i)[0];addr=struct.unpack_from('>I',dol,0x48+4*i)[0];size=struct.unpack_from('>I',dol,0x90+4*i)[0]
        if size and (off<0x100 or off+size>len(dol)):raise ValueError('DOL section bounds')
        if size and addr<ENTRY+32 and addr+size>ENTRY:raise ValueError('Channel entry overlaps an existing DOL section')
        if i<7 and not size and free is None:free=i
    bss,size=struct.unpack_from('>II',dol,0xd8)
    if size and bss<ENTRY+32 and bss+size>ENTRY:raise ValueError('Channel entry overlaps DOL BSS')
    if free is None or not -0x2000000<=target-ENTRY<0x2000000 or target%4:raise ValueError('DOL cannot use bounded channel entry branch')
    # A non-linking relative branch retains the title launcher's register state.
    branch=0x48000000|((target-ENTRY)&0x03fffffc)
    offset=(len(dol)+31)&~31;out=bytearray(dol);out.extend(bytes(offset-len(out)))
    out+=struct.pack('>8I',branch,*([0x60000000]*7))
    struct.pack_into('>I',out,4*free,offset);struct.pack_into('>I',out,0x48+4*free,ENTRY);struct.pack_into('>I',out,0x90+4*free,32)
    struct.pack_into('>I',out,0xe0,ENTRY)
    return bytes(out),dict(required=True,entry=hex(ENTRY),target=hex(target),section=free,bytes=32,source_sha256=hashlib.sha256(dol).hexdigest(),channel_dol_sha256=hashlib.sha256(out).hexdigest())

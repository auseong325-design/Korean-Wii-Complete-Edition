"""Channel entry check for the Korean Set Personal Data DOL.

IOS (and Dolphin's ReleasePPC: "NAND titles start with address translation
off at 0x3400") starts a NAND title's boot DOL at physical 0x3400 and ignores
the DOL header entry. devkitPPC r51's crt0 links `_start` at 0x80003f00 and no
longer emits the old 0x80003400 real-mode stub that WiiLink's shipped SPD DOL
still has (0x140 bytes), so build-v1 had nothing mapped there. From revision 2
the build adds kwce/dvd_channel_boot.py's 32-byte stub (used read-only here):
a relative non-linking branch, valid in real mode, to the linked `_start`,
whose `bl __InitBATS` switches to translated mode itself.
"""
import struct
ENTRY=0x80003400

def sections(dol):
    """[(index, file offset, address, size)] of non-empty DOL sections; 0-6 are text."""
    if len(dol)<0x100:raise ValueError('DOL header missing')
    rows=[]
    for i in range(18):
        off=struct.unpack_from('>I',dol,4*i)[0];addr=struct.unpack_from('>I',dol,0x48+4*i)[0];size=struct.unpack_from('>I',dol,0x90+4*i)[0]
        if not size:continue
        if off<0x100 or off+size>len(dol):raise ValueError('DOL section bounds')
        rows.append((i,off,addr,size))
    return rows

def header_entry(dol):return struct.unpack_from('>I',dol,0xe0)[0]

def channel_entry(dol):
    """Describe the code at 0x80003400; raise ValueError unless it is a branch into the program text."""
    rows=sections(dol)
    text=[r for r in rows if r[0]<7 and r[2]<=ENTRY<r[2]+r[3]]
    if not text:raise ValueError('No DOL text section covers the 0x80003400 channel entry')
    index,off,addr,size=text[0]
    if ENTRY+4>addr+size:raise ValueError('Channel entry section too short')
    word=struct.unpack_from('>I',dol,off+ENTRY-addr)[0]
    if word>>26!=18 or word&3:raise ValueError('Channel entry is not a relative non-linking branch')
    disp=word&0x03fffffc
    if disp&0x02000000:disp-=0x04000000
    target=(ENTRY+disp)&0xffffffff
    owner=[r for r in rows if r[0]<7 and r[2]<=target<r[2]+r[3]and r[0]!=index]
    if not owner:raise ValueError('Channel entry branch does not reach another text section')
    return dict(address=hex(ENTRY),section=index,section_bytes=size,instruction=f'{word:08x}',branch_target=hex(target),
                target_section=owner[0][0],header_entry=hex(header_entry(dol)))

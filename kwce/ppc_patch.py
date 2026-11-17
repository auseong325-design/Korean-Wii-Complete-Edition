"""Small PowerPC DOL patch helpers using the pinned local devkitPPC binutils.

Patches are assembled at their final virtual address, so relative branches to
original functions are resolved by the linker instead of hand encoding.
"""
import struct,subprocess,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
from .toolchain import BIN, tool

def sections(dol):
    off=struct.unpack_from('>18I',dol,0);addr=struct.unpack_from('>18I',dol,0x48);size=struct.unpack_from('>18I',dol,0x90)
    return [(i,off[i],addr[i],size[i])for i in range(18)if size[i]]

def to_file(dol,va,length=4):
    for _,o,a,s in sections(dol):
        if a<=va and va+length<=a+s:return o+va-a
    raise ValueError('Address outside DOL sections')

def assemble(source,address,symbols):
    """Return raw bytes of `source` linked at `address`; symbols map names to absolute addresses."""
    # Symbols are resolved by the linker so branches become PC-relative.
    defs=[f'--defsym={k}={v:#x}'for k,v in symbols.items()]
    with tempfile.TemporaryDirectory()as tmp:
        tmp=Path(tmp);(tmp/'p.s').write_text('.text\n'+source+'\n',encoding='ascii')
        def run(*a):
            r=subprocess.run([str(tool(a[0])),*a[1:]],cwd=tmp,capture_output=True,text=True)
            if r.returncode:raise ValueError(a[0]+": "+r.stderr.strip())
        run('powerpc-eabi-as.exe','-mregnames','-mgekko','-o','p.o','p.s')
        run('powerpc-eabi-ld.exe',*defs,'-Ttext',f'{address:#x}','-e',f'{address:#x}','-o','p.elf','p.o')
        run('powerpc-eabi-objcopy.exe','-O','binary','-j','.text','p.elf','p.bin')
        return (tmp/'p.bin').read_bytes()

def write_code(dol,address,code,region_end,expected_sha256=None):
    """Replace [address, region_end) with code padded by nops; verify the original bytes first."""
    import hashlib
    at=to_file(dol,address,region_end-address);original=bytes(dol[at:at+region_end-address])
    if expected_sha256 and hashlib.sha256(original).hexdigest()!=expected_sha256:raise ValueError(f'Unexpected original code at {address:#x}')
    if len(code)>region_end-address or len(code)%4:raise ValueError(f'Patch too large at {address:#x}')
    dol[at:at+region_end-address]=code+b'\x60\x00\x00\x00'*((region_end-address-len(code))//4)
    return hashlib.sha256(original).hexdigest()

def add_text_section(dol,address,code):
    """Append code as a new DOL text section in the first unused slot."""
    for i,o,a,s in sections(dol):
        if i<7 and not(address+len(code)<=a or a+s<=address):raise ValueError('Text section overlap')
        if i>=7 and not(address+len(code)<=a or a+s<=address):raise ValueError('Data section overlap')
    sizes=struct.unpack_from('>7I',dol,0x90)
    slot=next(i for i in range(7)if sizes[i]==0)
    offset=(len(dol)+31)&~31;dol.extend(bytes(offset-len(dol)));dol.extend(code);dol.extend(bytes((-len(code))%32))
    struct.pack_into('>I',dol,4*slot,offset);struct.pack_into('>I',dol,0x48+4*slot,address);struct.pack_into('>I',dol,0x90+4*slot,(len(code)+31)&~31)
    return slot

def utf16_slots(executable,rows):
    """Replace UTF-16 strings at fixed virtual addresses inside their zero-padded slots.

    rows: (address, expected English, Korean). The original text must match and
    the Korean text plus terminator must fit before the next string.
    """
    out=bytearray(executable);done=[]
    for va,expected,target in rows:
        at=to_file(out,va,2);end=at
        while out[end:end+2]!=b'\0\0':end+=2
        slot=end
        while out[slot:slot+2]==b'\0\0'and slot-at<1024:slot+=2
        if expected is not None and out[at:end].decode('utf-16-be')!=expected:raise ValueError(f'Unexpected string at {va:#x}')
        if expected is None and not out[at:end]:raise ValueError(f'Empty string slot at {va:#x}')
        data=target.encode('utf-16-be')+b'\0\0'
        if len(data)>slot-at:raise ValueError(f'Korean string exceeds slot at {va:#x}: {target}')
        out[at:slot]=data+bytes(slot-at-len(data));done.append(dict(address=hex(va),target=target))
    return bytes(out),done

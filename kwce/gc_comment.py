"""Build a bounded adapter for 43K's existing PrFILE2 CP932 converter.

43K dummies ENC's Japanese map. Its disabled decoder returns -2 before its
conversion loop. Preserve parameter checks, the map check and its epilogue;
reuse only the unreachable loop body for the GC-only adapter. The existing
PrFILE2 converter and its tables remain intact. Original files stay intact.
"""
from pathlib import Path
import hashlib,json,subprocess,sys,tempfile

ADDRESS=0x815458d8

def build_decoder(root):
    root=Path(root)
    from .toolchain import BIN as tools, tool
    gcc=tool('powerpc-eabi-gcc.exe', tools);objcopy=tool('powerpc-eabi-objcopy.exe', tools)
    lock=root/('configs/gc-comment.lock.json' if sys.platform == 'win32' else 'configs/gc-comment-linux.lock.json')
    expected=json.loads(lock.read_text())
    for key,p in [('compiler_sha256',gcc),('objcopy_sha256',objcopy),('source_sha256',root/'kwce/gc_comment.c')]:
        if hashlib.sha256(p.read_bytes()).hexdigest()!=expected[key]:raise ValueError('GC comment input lock mismatch')
    out=root/'workspace/experiments/gc-comment-code'
    if sys.platform != 'win32':
        cache=root/'workspace/private/linux-setup';cache.mkdir(parents=True,exist_ok=True)
        temporary=tempfile.TemporaryDirectory(prefix='gc-comment-',dir=cache)
        out=Path(temporary.name)
    out.mkdir(parents=True,exist_ok=True)
    (out/'link.ld').write_text('ENTRY(gc_comment)\nSECTIONS { . = 0x815458d8; .text : { *(.entry) *(.text*) } .rodata : { *(.rodata*) } /DISCARD/ : { *(.comment) *(.eh_frame*) } }\n',encoding='ascii')
    subprocess.run([str(gcc),'-O2','-mcpu=750','-meabi','-m32','-mbig-endian','-msdata=none','-ffreestanding','-fno-builtin','-fno-stack-protector','-nostdlib','-I',str(out),str(root/'kwce/gc_comment.c'),'-Wl,-T,'+str(out/'link.ld'),'-o',str(out/'decoder.elf')],check=True,capture_output=True)
    subprocess.run([str(objcopy),'-O','binary',str(out/'decoder.elf'),str(out/'decoder.bin')],check=True,capture_output=True)
    blob=(out/'decoder.bin').read_bytes()
    if not 100<len(blob)<=0x200:raise ValueError('Unexpected decoder size')
    record=dict(address=hex(ADDRESS),size=len(blob),sha256=hashlib.sha256(blob).hexdigest(),converter='0x815bd2c0',compiler_sha256=hashlib.sha256(gcc.read_bytes()).hexdigest(),objcopy_sha256=hashlib.sha256(objcopy.read_bytes()).hexdigest(),source_sha256=hashlib.sha256((root/'kwce/gc_comment.c').read_bytes()).hexdigest())
    if expected!=record:raise ValueError('GC comment build lock mismatch')
    if sys.platform != 'win32':temporary.cleanup()
    return blob,record

"""43K DVD integration through native group animators and normal call sites.

The old R21 launch hook is preserved. New code uses the unused Kitayama
auto-test worker code area; the entire original range and both call sites are
verified. No menu resources or console data are written by the runtime code.
"""
import hashlib,struct,subprocess,tempfile
from pathlib import Path
from .toolchain import tool
from . import dvd_disc_hook as old
from .ppc_patch import BIN,to_file

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'homebrew/kwce-disc-menu/r12/menu.c'
CAVE=0x813BDFB0
END=0x813BEAFC  # only Kitayama auto-test process_save_test (0xB4C bytes)
SITES={0x813B3ED0:(0x813B78B0,'kwce_bind'),0x813B4154:(0x813B7A00,'kwce_update')}

def compile_hook():
    with tempfile.TemporaryDirectory()as tmp:
        tmp=Path(tmp)
        script='SECTIONS { . = '+hex(CAVE)+'; .kwce : { *(.text.stub) *(.text*) *(.rodata*) *(.data*) *(.sdata*) *(.bss*) *(COMMON) FILL(0x60000000) . = ALIGN(4); } /DISCARD/ : { *(.comment) *(.eh_frame*) *(.gnu.attributes) } }'
        (tmp/'link.ld').write_text(script,encoding='ascii')
        def run(*args):
            r=subprocess.run([str(tool(args[0])),*args[1:]],cwd=tmp,capture_output=True,text=True)
            if r.returncode:raise ValueError('Native DVD compile: '+r.stderr.strip())
            if 'warning:'in r.stderr:raise ValueError('Native DVD compile warning: '+r.stderr.strip())
            return r.stdout
        run('powerpc-eabi-gcc.exe','-O2','-mcpu=750','-mhard-float','-meabi','-msdata=none','-fno-pic','-fno-common',
            '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
            '-std=c99','-Wall','-Wextra','-Werror','-c',str(SOURCE),'-o','menu.o')
        run('powerpc-eabi-ld.exe','--no-undefined','--defsym=kwce_find_dvd='+hex(old.CAVE+8),'-T','link.ld','menu.o','-o','menu.elf')
        run('powerpc-eabi-objcopy.exe','-O','binary','-j','.kwce','menu.elf','menu.bin')
        symbols={s.split()[-1]:int(s.split()[0],16)for s in run('powerpc-eabi-nm.exe','-S','menu.elf').splitlines()if len(s.split())==4}
        code=(tmp/'menu.bin').read_bytes()
        if len(code)>END-CAVE:raise ValueError('Native DVD code exceeds reviewed debug area')
        if symbols['kwce_unused_debug']!=CAVE or code[:8]!=bytes.fromhex('386000004e800020'):raise ValueError('Native DVD debug entry must return zero')
        if len(code)%4 or any(int.from_bytes(code[i:i+4],'big')<0x1000000 for i in range(0,len(code),4)):raise ValueError('Native DVD code contains a word old Priiloader truncates')
        return code,symbols

def patch_dvd_banner_hook(menu):
    reference=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    before=to_file(menu,CAVE,END-CAVE);original=reference[to_file(reference,CAVE,END-CAVE):to_file(reference,CAVE,END-CAVE)+END-CAVE]
    if menu[before:before+END-CAVE]!=original:raise ValueError('Native DVD auto-test code cave differs')
    for address,(native,_)in SITES.items():
        if menu[to_file(menu,address):to_file(menu,address)+4]!=old._branch(address,native,True):raise ValueError('Native DVD call site differs')
    data,record=old.patch_dvd_hook(menu);out=bytearray(data);code,symbols=compile_hook()
    out[before:before+len(code)]=code
    for address,(_,name)in SITES.items():out[to_file(menu,address):to_file(menu,address)+4]=old._branch(address,symbols[name],True)
    record.update(hook_revision=12,feature='native DVD group animations, floor insertion, asynchronous KDVD banner',
                  native_code_bytes=len(code),native_cave=hex(CAVE),native_cave_capacity=END-CAVE,
                  native_cave_original_sha256=hashlib.sha256(original).hexdigest(),
                  native_source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                  sites=[*record['sites'],*(hex(s)for s in SITES)],pane_transform_copy=False,
                  original_update_entry_preserved=True,nand_writes=False)
    return bytes(out),record

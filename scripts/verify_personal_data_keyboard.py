"""Differential test of the device Hangul keyboard code against the Python model.

Compiles kwce_hangul.c exactly as kwce/personal_data_fork.py writes it, as a
freestanding PowerPC image with the project devkitPPC, runs it under the
unicorn CPU emulator and compares every step with kwce/personal_data_hangul.py.
unicorn is not a project dependency: install it outside the project, e.g.
  .venv\\Scripts\\python.exe -m pip install --target %KIROCREW_SCRATCH%\\pylibs unicorn==2.1.1
and pass --pylibs <that folder>. Writes only into --work (default: a temp dir).
"""
import argparse,random,struct,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce import personal_data_fork as fork
from kwce import personal_data_hangul as H
BIN=ROOT/'tools/devkitpro-root/opt/devkitpro/devkitPPC/bin'
LINK='''ENTRY(kwce_hangul_key)
SECTIONS {
  . = 0x00100000;
  .text : { *(.text*) }
  .rodata : { *(.rodata*) *(.sdata2*) *(.sbss2*) }
  .data : { *(.data*) *(.sdata*) *(.sbss*) *(.bss*) *(COMMON) }
  /DISCARD/ : { *(.comment) *(.eh_frame*) *(.gnu.attributes) }
}
'''
HARNESS='#include <stddef.h>\n#include <wchar.h>\nsize_t wcslen(const wchar_t *s) { size_t n = 0; while (s[n]) n++; return n; }\n#include "kwce_hangul.c"\n'

def build(work):
    (work/'kwce_hangul.h').write_text(fork.HANGUL_H);(work/'kwce_hangul.c').write_text(fork.HANGUL_C)
    (work/'kwce_hangul_tables.h').write_text(fork.tables_header(),encoding='utf-8');(work/'harness.c').write_text(HARNESS);(work/'link.ld').write_text(LINK)
    subprocess.run([str(BIN/'powerpc-eabi-gcc.exe'),'-O3','-Wall','-Werror','-mcpu=750','-meabi','-mhard-float','-msdata=none','-ffreestanding','-fno-builtin','-nostdlib',
                    '-Wl,-T,'+str(work/'link.ld'),'-o',str(work/'harness.elf'),str(work/'harness.c')],check=True)
    subprocess.run([str(BIN/'powerpc-eabi-objcopy.exe'),'-O','binary',str(work/'harness.elf'),str(work/'harness.bin')],check=True)
    nm=subprocess.run([str(BIN/'powerpc-eabi-nm.exe'),str(work/'harness.elf')],capture_output=True,text=True,check=True).stdout
    return (work/'harness.bin').read_bytes(),{l.split()[2]:int(l.split()[0],16)for l in nm.splitlines()if len(l.split())==3}

def run(image,sym,sequences,seed):
    from unicorn import Uc,UC_ARCH_PPC,UC_MODE_PPC32,UC_MODE_BIG_ENDIAN
    from unicorn.ppc_const import UC_PPC_REG_1,UC_PPC_REG_3,UC_PPC_REG_4,UC_PPC_REG_5,UC_PPC_REG_6,UC_PPC_REG_LR
    uc=Uc(UC_ARCH_PPC,UC_MODE_PPC32|UC_MODE_BIG_ENDIAN);BASE,TEXT,COMP,STACK,STOP=0x100000,0x200000,0x201000,0x300000,0x400000
    uc.mem_map(BASE,0x10000);uc.mem_write(BASE,image);uc.mem_map(TEXT,0x2000);uc.mem_map(STACK-0x10000,0x10000);uc.mem_map(STOP,0x1000)
    def call(name,*args):
        uc.reg_write(UC_PPC_REG_1,STACK-0x100);uc.reg_write(UC_PPC_REG_LR,STOP)
        for reg,val in zip([UC_PPC_REG_3,UC_PPC_REG_4,UC_PPC_REG_5,UC_PPC_REG_6],args):uc.reg_write(reg,val&0xffffffff)
        uc.emu_start(sym[name],STOP,count=200000);return uc.reg_read(UC_PPC_REG_3)
    def put(text,comp):uc.mem_write(TEXT,b''.join(struct.pack('>I',ord(c))for c in text)+bytes(4*(256-len(text))));uc.mem_write(COMP,struct.pack('>i',int(comp)))
    def get():
        raw=bytes(uc.mem_read(TEXT,1024));chars=[]
        for i in range(256):
            v=struct.unpack_from('>I',raw,4*i)[0]
            if not v:break
            chars.append(chr(v))
        return ''.join(chars),struct.unpack('>i',bytes(uc.mem_read(COMP,4)))[0]!=0
    keys=0
    for row in range(5):
        for col in range(12):
            for sh in(0,1):
                c=call('kwce_hangul_key',row,col,sh)
                if(chr(c)if c else None)!=H.key(row,col,bool(sh)):raise SystemExit(f'Key table differs at {row},{col},{sh}')
                keys+=1
    rng=random.Random(seed);jamo=[(r,c)for r in(1,2,3)for c in range(len(H.LAYOUT[r]))];steps=0
    for seq in range(sequences):
        maxlen=rng.randint(3,14);text=''.join(rng.choice('가나다ab 한')for _ in range(rng.randint(0,maxlen-2)));comp=False
        for _ in range(rng.randint(1,40)):
            kind=rng.random()
            if kind<0.75:
                r,c=rng.choice(jamo);j=H.key(r,c,rng.random()<0.2);put(text,comp);call('kwce_hangul_type',TEXT,COMP,ord(j),maxlen);dev=get()
                model=H.type_jamo(text,comp,j,maxlen)
            elif kind<0.93:
                put(text,comp);call('kwce_hangul_backspace',TEXT,COMP);dev=get();model=H.backspace(text,comp)
            else:
                text=text+rng.choice(' a1.')if len(text)<maxlen-1 else text;comp=False;continue
            model=(''.join(model[0]),model[1])
            if dev!=model:raise SystemExit(f'Device code differs from model at sequence {seq}: {dev!r} vs {model!r}')
            text,comp=model;steps+=1
    return keys,steps

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pylibs');ap.add_argument('--work');ap.add_argument('--sequences',type=int,default=3000);ap.add_argument('--seed',type=int,default=20261028)
    args=ap.parse_args()
    if args.pylibs:sys.path.insert(0,args.pylibs)
    try:import unicorn  # noqa: F401
    except ImportError:print('SKIP: unicorn not importable; see module docstring');return 0
    with tempfile.TemporaryDirectory()as tmp:
        work=Path(args.work or tmp);work.mkdir(parents=True,exist_ok=True)
        image,sym=build(work);keys,steps=run(image,sym,args.sequences,args.seed)
    print(f'PASS: PowerPC kwce_hangul.c == Python model ({keys} key lookups, {args.sequences} sequences, {steps} composition steps)')
if __name__=='__main__':sys.exit(main())

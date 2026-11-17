"""Pinned 43K menu service, packed into previously reviewed debug code caves.

No NAND installer. Hardware packaging requires separate readiness evidence.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from .toolchain import tool
from .ppc_patch import to_file
from .dvd_disc_hook import _branch
from .dvd_native_hook import ORIGINAL, BANNER, BANNER_END, CAVE, END, SITES
from .dvd_native_relocate import compile_relocator, validate_payload, validate_ash_mapping

ROOT=Path(__file__).resolve().parents[1]
SOURCE_REVISION=37
SOURCE=ROOT/f'homebrew/kwce-disc-menu/native-v{SOURCE_REVISION}'
# Only Kitayama's developer test scene and its private destructive auto-test
# worker are repurposed. Constructor/destructor/base-vtable hooks stay intact;
# callable scene methods become harmless returns. No normal UI/SDK code space.
# First 64 bytes of calcNormal hold the debug return and displaced-entry stubs.
DEBUG_GUARDS={0x813BD48C:bytes.fromhex('4e800020'),  # create: no worker created
              0x813BD530:bytes.fromhex('4e800020'),  # destroy: no worker to free
              0x813BDD08:bytes.fromhex('386000004e800020'),
              0x813BDD5C:bytes.fromhex('4e800020')}
REGIONS=[(0x813BD490,0x813BD530),(0x813BD534,0x813BD5C4),
         (ORIGINAL+64,0x813BDD08),(0x813BDD10,0x813BDD5C),
         (0x813BDD60,0x813BDD80),(0x813BDD98,END)]
ENTRY_SITES={0x8138E4A0:'kwce_board_calc',0x8138E94C:'kwce_board_destroy',
             0x813AA694:'kwce_select_destroy'}


def call_site(menu, start, size, target):
    from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN
    at=to_file(menu,start,size)
    hits=[i.address for i in Cs(CS_ARCH_PPC,CS_MODE_32|CS_MODE_BIG_ENDIAN).disasm(
        menu[at:at+size],start) if i.mnemonic=='bl' and i.op_str==hex(target)]
    if len(hits)!=1:raise ValueError('Expected exactly one original SDK call')
    return hits[0]


def sites(menu):
    return {**SITES,0x813A9FBC:'kwce_select_update',**ENTRY_SITES,
            call_site(menu,0x8138E364,0x13c,0x8133F624):'kwce_start_sd',
            call_site(menu,0x8138E4A0,0x3ac,0x81395338):'kwce_board_update',
            call_site(menu,0x8135E4D0,0x2c0,0x8135ECCC):'kwce_sd_wait'}


def compile_integrated(player,module,banner,icon,*,source_revision=SOURCE_REVISION):
    source=ROOT/f'homebrew/kwce-disc-menu/native-v{source_revision}'
    if source_revision not in (34,35,36,37,38):raise ValueError('Unreviewed source revision')
    validate_payload(player);validate_ash_mapping(player)
    from .formats import ash_decompress
    if source_revision==38:
        from .dvd_lzma_stage import unpack, compile_relocator as compile_lzma_relocator
        expanded=unpack(module)
        relocator=compile_lzma_relocator(len(module))
    else:
        expanded=ash_decompress(module)
        relocator=compile_relocator(ash=True)
    if expanded!=player:raise ValueError('Module does not match reviewed player')
    sizes=[len(module),len(banner),len(icon)]
    stage=(sizes[0]+31)&~31;stack=65536
    offsets=[0,stage+stack,stage+stack+((sizes[1]+31)&~31)]
    total=offsets[2]+((sizes[2]+31)&~31)
    with tempfile.TemporaryDirectory() as temp:
        tmp=Path(temp)
        def run(name,*args):
            r=subprocess.run([str(tool(name)),*args],cwd=tmp,capture_output=True,text=True)
            if r.returncode or 'warning:' in r.stderr:raise ValueError(r.stderr)
            return r.stdout
        size_header=''.join(f'#define {k} {v}u\n' for k,v in dict(
            PLAYER_SIZE=sizes[0],BANNER_SIZE=sizes[1],ICON_SIZE=sizes[2],
            STAGE_SIZE=stage,STACK_SIZE=stack,BANNER_OFFSET=offsets[1],
            ICON_OFFSET=offsets[2],BUNDLE_SIZE=total).items())
        (tmp/'sizes.h').write_text(size_header)
        def encoded(data):return ','.join(str(b^0xa5) for b in data)
        (tmp/'service-payload.h').write_text('#include "sizes.h"\n'+
            'static const unsigned char asset_hash[3][20]={'+','.join(
                '{'+encoded(hashlib.sha1(data).digest())+'}' for data in (module,banner,icon))+'};\n'+
            'static const unsigned char relocator[]={'+encoded(relocator)+'};\n')
        objects=[];sections=[]
        for name in ('loader','banner','banner_io','service'):
            obj=name+'.o';objects.append(obj)
            run('powerpc-eabi-gcc.exe','-Oz','-mcpu=750','-meabi','-msdata=none',
                '-fno-pic','-fno-common','-ffreestanding','-fno-builtin','-fno-stack-protector',
                '-fno-unwind-tables','-fno-asynchronous-unwind-tables',
                '-ffunction-sections','-fdata-sections','-std=c99','-Wall','-Wextra','-Werror',
                '-I',str(tmp),'-c',str(source/(name+'.c')),'-o',obj)
        libgcc=run('powerpc-eabi-gcc.exe','-print-libgcc-file-name').strip()
        run('powerpc-eabi-ar.exe','x',libgcc,'crtresxgpr.o');objects.append('crtresxgpr.o')
        for obj in objects:
            listing=run('powerpc-eabi-objdump.exe','-h',obj)
            for section,size,alignment in re.findall(
                r'^\s*\d+\s+(\S+)\s+([0-9a-f]+)\s+[0-9a-f]+\s+[0-9a-f]+\s+[0-9a-f]+\s+2\*\*(\d+)',listing,re.M):
                n=int(size,16)
                if not n or section in ('.comment','.gnu.attributes'):continue
                if source_revision>=36 and section.startswith(('.debug','.zdebug')):continue
                if source_revision>=37 and section.startswith('.eh_frame'):continue
                if section.startswith(('.bss','.sbss')):raise ValueError('Implicit zero-state forbidden')
                # libgcc's hand-written restore helper declares alignment 1;
                # PPC branch targets still require 4-byte instruction alignment.
                sections.append((n,max(4,1<<int(alignment)),obj,section))
        # Deterministic descending-size placement, checked again by the linker.
        bins=[[] for _ in REGIONS];positions=[a for a,b in REGIONS]
        for n,align,obj,section in sorted(sections,key=lambda row:(-row[0],row[2],row[3])):
            choices=[(end-(((positions[i]+align-1)&-align)+n),i)
                     for i,(start,end) in enumerate(REGIONS)
                     if ((positions[i]+align-1)&-align)+n<=end]
            if not choices:raise ValueError(f'Integrated code does not fit existing caves: {sum(s[0] for s in sections)} bytes')
            _,i=min(choices);bins[i].append((obj,section,align));positions[i]=((positions[i]+align-1)&-align)+n
        script='SECTIONS {\n'
        for i,((start,end),items) in enumerate(zip(REGIONS,bins)):
            script+=f'.part{i} {start:#x} : {{ FILL(0xffffffff)\n'
            for obj,section,align in items:script+=f'. = ALIGN({align}); {obj}({section})\n'
            script+=' . = ALIGN(4); }\n'
        script+='/DISCARD/ : { *(.comment) *(.gnu.attributes) '+('*(.debug*) *(.zdebug*) ' if source_revision>=36 else '')+('*(.eh_frame*) ' if source_revision>=37 else '')+'}\n}'
        (tmp/'link.ld').write_text(script)
        names=['kwce_enable_original','kwce_reserve_original','kwce_fade_original',
               'kwce_board_calc_original','kwce_board_destroy_original','kwce_select_destroy_original']
        defs={name:ORIGINAL+8+8*i for i,name in enumerate(names)}
        run('powerpc-eabi-ld.exe','--no-undefined',*[f'--defsym={k}={v}' for k,v in defs.items()],
            '-T','link.ld',*objects,'-o','hook.elf')
        syms={p[-1]:int(p[0],16) for line in run('powerpc-eabi-nm.exe','-S','hook.elf').splitlines()
              if len(p:=line.split())==4}
        blobs={}
        for i,(start,end) in enumerate(REGIONS):
            run('powerpc-eabi-objcopy.exe','-O','binary','-j',f'.part{i}','hook.elf',f'part{i}.bin')
            data=(tmp/f'part{i}.bin').read_bytes()
            if len(data)>end-start:raise ValueError('Linker exceeded reviewed cave')
            blobs[start]=data
        return blobs,syms,dict(sizes=sizes,offsets=offsets,bundle_size=total,
                               code_bytes=sum(len(b) for b in blobs.values()))


def patch(menu,player,module,banner,icon,*,source_revision=SOURCE_REVISION):
    original=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    blobs,syms,record=compile_integrated(player,module,banner,icon,source_revision=source_revision)
    out=bytearray(menu)
    for start,end in [(0x813BD48C,END)]:
        at=to_file(menu,start,end-start)
        if menu[at:at+end-start]!=original[at:at+end-start]:raise ValueError('Code cave already patched')
    stub=bytearray(bytes.fromhex('386000004e800020'))
    for address in (0x813B8D9C,0x813B8844,0x813B45AC,*ENTRY_SITES):
        at=to_file(original,address);instruction=original[at:at+4]
        if address in ENTRY_SITES and int.from_bytes(instruction,'big')>>16!=0x9421:
            raise ValueError('Entry trampoline requires stack allocation prologue')
        here=ORIGINAL+len(stub);stub+=instruction+_branch(here+4,address+4)
    for start,data in {ORIGINAL:bytes(stub),**DEBUG_GUARDS,**blobs}.items():
        at=to_file(menu,start,len(data));out[at:at+len(data)]=data
    for address,name in sites(original).items():
        at=to_file(menu,address)
        if menu[at:at+4]!=original[at:at+4]:raise ValueError('Call site already patched')
        link=address not in ENTRY_SITES and address not in (0x813B8D9C,0x813B8844,0x813B45AC)
        out[at:at+4]=_branch(address,syms[name],link)
    record.update(symbols=syms,source_revision=source_revision,sd_worker_service=True,
                  sd_attach_hook=False,menu_lifetime_cache=source_revision==34,
                  board_lifetime_cache=source_revision>=35,
                  player_sha256=hashlib.sha256(player).hexdigest(),
                  module_sha256=hashlib.sha256(module).hexdigest(),
                  icon_sha256=hashlib.sha256(icon).hexdigest(),
                  banner_sha256=hashlib.sha256(banner).hexdigest(),
                  sites={hex(k):v for k,v in sites(original).items()},
                  experimental=True,nand_writes=False)
    return bytes(out),record

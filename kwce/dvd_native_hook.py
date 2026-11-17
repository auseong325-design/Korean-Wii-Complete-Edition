"""Experimental 43K channel-independent DVD module loader; no SD deployment."""
import hashlib
import struct
import subprocess
import tempfile
from pathlib import Path
from .toolchain import tool
from .ppc_patch import BIN, assemble, to_file
from .dvd_disc_hook import _branch
from .dvd_native_relocate import compile_relocator, validate_payload,validate_ash_mapping

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'homebrew/kwce-disc-menu/native-v1'
CAVE=0x813BEC04
END=0x813BF6A8
BANNER=0x813BDFB0
BANNER_END=0x813BEAFC
ORIGINAL=0x813BD5C8
BANNER_IO=ORIGINAL+0x300
SITES={0x813B8D9C:'kwce_enable',0x813B8844:'kwce_reserve',0x813B45AC:'kwce_fade',
       0x813B3ED0:'kwce_bind',0x813B4154:'kwce_update'}


def compile_hook(player,module=None,banner=None,source=SOURCE):
    validate_payload(player)
    compressed=module is not None
    if compressed:
        from .formats import ash_decompress
        if ash_decompress(module)!=player:raise ValueError('ASH module differs from reviewed DOL')
        validate_ash_mapping(player)
    else:module=player
    if banner is None:banner=(ROOT/'workspace/experiments/dvd-native-banner-v1/menu.arc').read_bytes()
    relocator=compile_relocator(ash=compressed)
    def array(name,data):
        return 'static const unsigned char '+name+'[] __attribute__((section(".payload")))={'+','.join(str(b^0xa5) for b in data)+'};\n'
    with tempfile.TemporaryDirectory() as temp:
        tmp=Path(temp)
        (tmp/'payload.h').write_text('#define PLAYER_SIZE '+str(len(module))+'u\n'+
            '#define STAGE_SIZE '+str((len(module)+31)&~31)+'u\n#define STACK_SIZE 65536u\n'+
            array('player_header',module[:256])+array('player_sha1',hashlib.sha1(module).digest())+
            array('relocator',relocator)+array('path_template',b'?:/kwce/dvd/boot.ash\0'),encoding='ascii')
        (tmp/'banner-payload.h').write_text('#define BANNER_SIZE '+str(len(banner))+'u\n'+
            array('banner_sha1',hashlib.sha1(banner).digest()).replace('.payload','.bpayload'),encoding='ascii')
        if Path(source).name in ('native-v6','native-v7','native-v8','native-v9','native-v10','native-v11','native-v12','native-v13','native-v14','native-v15','native-v16','native-v18','native-v19','native-v20','native-v21','native-v22','native-v23','native-v24','native-v25','native-v26','native-v27','native-v28','native-v29','native-v30','native-v31','native-v32','native-v33'):
            icon=(ROOT/'workspace/experiments/dvd-native-icon-v1/icon.arc').read_bytes()
            (tmp/'icon-payload.h').write_text('#define ICON_SIZE '+str(len(icon))+'u\n'+array('icon_sha1',hashlib.sha1(icon).digest()).replace('.payload','.rodata'),encoding='ascii')
        def run(name,*args):
            r=subprocess.run([str(tool(name)),*args],cwd=tmp,capture_output=True,text=True)
            if r.returncode or 'warning:' in r.stderr:raise ValueError(r.stderr)
            return r.stdout
        for name in ('loader','banner','banner_io'):
            opt='-Os' if (Path(source).name=='native-v5' and name=='banner') or (Path(source).name in ('native-v6','native-v7','native-v8','native-v9','native-v10','native-v11','native-v12','native-v13','native-v14','native-v15','native-v16','native-v18','native-v19','native-v20','native-v21','native-v22','native-v23','native-v24','native-v25','native-v26','native-v27','native-v28','native-v29','native-v30','native-v31','native-v32','native-v33') and name in ('banner','loader')) else '-O2'
            if Path(source).name in ('native-v27','native-v28','native-v29','native-v30','native-v31','native-v32','native-v33'):opt='-Os'
            run('powerpc-eabi-gcc.exe',opt,'-mcpu=750','-meabi','-msdata=none','-fno-pic','-fno-common',
                '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables',
                '-fno-asynchronous-unwind-tables','-std=c99','-Wall','-Wextra','-Werror','-I',str(tmp),
                '-c',str(source/f'{name}.c'),'-o',name+'.o')
        helpers=''
        if Path(source).name in ('native-v5','native-v6','native-v7','native-v8','native-v9','native-v10','native-v11','native-v12','native-v13','native-v14','native-v15','native-v16','native-v18','native-v19','native-v20','native-v21','native-v22','native-v23','native-v24','native-v25','native-v26','native-v27','native-v28','native-v29','native-v30','native-v31','native-v32','native-v33'):
            libgcc=run('powerpc-eabi-gcc.exe','-print-libgcc-file-name').strip()
            run('powerpc-eabi-ar.exe','x',libgcc,'crtresxgpr.o')
            helpers='crtresxgpr.o'
        helper_section=helpers+'(.text*)' if helpers else ''
        script=f'''SECTIONS {{
          . = {ORIGINAL+32:#x}; .payload : {{ FILL(0x60000000) loader.o(.payload) loader.o(.panevis) banner_io.o(.bpayload) banner_io.o(.panevis) banner.o(.aux) }}
          . = {BANNER_IO:#x}; .bannerio : {{ FILL(0x60000000) banner_io.o(.text*) banner_io.o(.rodata*) banner_io.o(.data*) }}
          . = {BANNER:#x}; .banner : {{ FILL(0x60000000) banner.o(.text.stub) banner.o(.text*) banner.o(.rodata*) banner.o(.data*) {helper_section} }}
          . = {CAVE:#x}; .native : {{ FILL(0x60000000) loader.o(.text.stub) loader.o(.text*) loader.o(.rodata*) loader.o(.data*) banner.o(.auxnative) }}
          /DISCARD/ : {{ *(.comment) *(.eh_frame*) *(.gnu.attributes) }}
        }}'''
        (tmp/'link.ld').write_text(script,encoding='ascii')
        defs={'kwce_enable_original':ORIGINAL+8,'kwce_reserve_original':ORIGINAL+16,'kwce_fade_original':ORIGINAL+24}
        run('powerpc-eabi-ld.exe','--no-undefined',*[f'--defsym={k}={v}' for k,v in defs.items()],
            '-T','link.ld','banner.o','loader.o','banner_io.o',*([helpers] if helpers else []),'-o','hook.elf')
        symbols={s.split()[-1]:int(s.split()[0],16) for s in run('powerpc-eabi-nm.exe','-S','hook.elf').splitlines() if len(s.split())==4}
        blobs={}
        for name,begin,end in [('payload',ORIGINAL+32,BANNER_IO),('bannerio',BANNER_IO,ORIGINAL+0x740),('banner',BANNER,BANNER_END),('native',CAVE,END)]:
            run('powerpc-eabi-objcopy.exe','-O','binary','-j','.'+name,'hook.elf',name+'.bin')
            data=(tmp/(name+'.bin')).read_bytes()
            if len(data)>end-begin:raise ValueError(f'{name} code exceeds reviewed cave ({len(data)}/{end-begin})')
            blobs[name]=data
        return blobs,symbols


def patch(menu,player,module=None,banner=None,source=SOURCE,*,thumbnail=True):
    reference=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    blobs,symbols=compile_hook(player,module,banner,source=source)
    out=bytearray(menu)
    for name,begin,end in [('banner',BANNER,BANNER_END),('native',CAVE,END),('payload',ORIGINAL+32,BANNER_IO),('bannerio',BANNER_IO,ORIGINAL+0x740),('stub',ORIGINAL,ORIGINAL+32)]:
        at=to_file(menu,begin,end-begin)
        if menu[at:at+end-begin]!=reference[at:at+end-begin]:raise ValueError('Native cave differs from original')
        if name!='stub':out[at:at+len(blobs[name])]=blobs[name]
    stub=bytearray(bytes.fromhex('386000004e800020'))
    for address in (0x813B8D9C,0x813B8844,0x813B45AC):
        at=to_file(reference,address)
        here=ORIGINAL+len(stub)
        stub+=reference[at:at+4]+_branch(here+4,address+4)
    at=to_file(menu,ORIGINAL);out[at:at+len(stub)]=stub
    sites=dict(SITES)
    if thumbnail and Path(source).name in ('native-v6','native-v7','native-v8','native-v9','native-v10','native-v11','native-v12','native-v13','native-v14','native-v15','native-v16','native-v18','native-v19','native-v20','native-v21','native-v22','native-v23','native-v24','native-v25','native-v26','native-v27','native-v28','native-v29','native-v30','native-v31','native-v32','native-v33'):sites[0x813A9FBC]='kwce_select_update'
    if Path(source).name in ("native-v28","native-v29","native-v30","native-v31","native-v32"):sites[0x8135E820]="kwce_sd_attach"
    for address,name in sites.items():
        at=to_file(menu,address)
        if menu[at:at+4]!=reference[at:at+4]:raise ValueError('Native call site differs')
        out[at:at+4]=_branch(address,symbols[name],address in (0x813B3ED0,0x813B4154,0x813A9FBC,0x8135E820))
    return bytes(out),dict(schema=1,feature='channel-independent DVD module',
                          player_sha256=hashlib.sha256(player).hexdigest(),
                          module_sha256=hashlib.sha256(module if module is not None else player).hexdigest(),
                          module_format='ash' if module is not None else 'dol',
                          native_bytes=len(blobs['native']),banner_bytes=len(blobs['banner']),
                          symbols=symbols,nand_writes=False,experimental=True)

"""Run the real PPC rectangle emitter against inherited GUI/movie GX state.

Stubs model only the documented vertex descriptor/format calls. The bytes
written to the hardware FIFO are captured from the compiled function itself.
"""
import struct,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'workspace/private/unicorn-2.1.1'))
from kwce.ppc_patch import BIN
from kwce.dvd_player_fork import patches

class RectangleFifoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(ROOT/'external/other-tools/wiimc/source/video.cpp').read_text()
        start=source.index('void Menu_DrawRectangle(')
        end=source.index('\nbool safe_gc;',start)
        original=source[start:end].strip()
        cls.variants={}
        for revision in (43,46):
            function=original
            for name,a,b in patches(revision):
                if name=='source/video.cpp' and a in function:
                    if function.count(a)!=1:raise ValueError('Ambiguous rectangle patch')
                    function=function.replace(a,b)
            with tempfile.TemporaryDirectory() as directory:
                tmp=Path(directory)
                (tmp/'test.cpp').write_text('#include <gccore.h>\n'+function+'''
extern "C" void *memset(void *p,int v,unsigned n) {
  volatile unsigned char *d=(volatile unsigned char *)p;
  while(n--)*d++=(unsigned char)v;
  return p;
}
WGPipe* const wgPipe=(WGPipe*)0xcc008000;
extern "C" void run_rect(int filled) {
  Menu_DrawRectangle(0,0,640,480,(GXColor){1,2,3,4},filled);
}
extern "C" const unsigned facts[]={GX_VA_POS,GX_VA_CLR0,GX_VA_TEX0,
 GX_DIRECT,GX_NONE,GX_INDEX8,GX_POS_XYZ,GX_F32,GX_CLR_RGBA,GX_RGBA8};
''',encoding='utf-8')
                include=ROOT/'tools/devkitpro-root/opt/devkitpro/libogc2/wii/include'
                def run(name,*args):
                    r=subprocess.run([str(BIN/name),*args],cwd=tmp,capture_output=True,text=True)
                    if r.returncode:raise ValueError(r.stderr)
                    return r.stdout
                run('powerpc-eabi-g++.exe','-O2','-mcpu=750','-meabi','-msdata=none','-ffreestanding',
                    '-fno-exceptions','-fno-rtti','-I',str(include),'-c','test.cpp','-o','test.o')
                stubs={name:0x80010000+i*16 for i,name in enumerate(('GX_ClearVtxDesc','GX_SetVtxDesc','GX_SetVtxAttrFmt','GX_SetTevOp','GX_Begin','GX_SetBlendMode'))}
                (tmp/'link.ld').write_text('SECTIONS {. = 0x80004000; .all : {*(.text*) *(.rodata*) *(.data*)} /DISCARD/ : {*(.comment) *(.eh_frame*)}}')
                run('powerpc-eabi-ld.exe','-T','link.ld',*[f'--defsym={n}={a}'for n,a in stubs.items()],'-o','test.elf','test.o')
                run('powerpc-eabi-objcopy.exe','-O','binary','-j','.all','test.elf','test.bin')
                symbols={x.split()[-1]:int(x.split()[0],16)for x in run('powerpc-eabi-nm.exe','-S','test.elf').splitlines()if len(x.split())==4}
                code=(tmp/'test.bin').read_bytes();at=symbols['facts']-0x80004000
                cls.variants[revision]=(code,symbols,stubs,struct.unpack('>10I',code[at:at+40]))

    def emit(self,revision,initial,filled=1):
        from unicorn import Uc,UC_ARCH_PPC,UC_MODE_32,UC_MODE_BIG_ENDIAN,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
        from unicorn.ppc_const import UC_PPC_REG_1,UC_PPC_REG_3,UC_PPC_REG_4,UC_PPC_REG_5,UC_PPC_REG_6,UC_PPC_REG_LR,UC_PPC_REG_PC,UC_PPC_REG_MSR
        code,symbols,stubs,facts=self.variants[revision]
        pos,clr,tex,direct,none,index8,xyz,f32,rgba,rgba8=facts
        desc={pos:direct,clr:direct}
        if initial=='home':desc[tex]=direct
        if initial=='movie':desc={pos:index8,clr:index8,tex:index8,tex+1:index8,tex+2:index8}
        fmt={pos:(xyz,f32),clr:(rgba,rgba8)}
        u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN);u.mem_map(0x80000000,0x20000);u.mem_map(0xcc008000,0x1000);u.mem_write(0x80004000,code)
        u.reg_write(UC_PPC_REG_1,0x8001f000);u.reg_write(UC_PPC_REG_3,filled);u.reg_write(UC_PPC_REG_LR,0x80001000);u.reg_write(UC_PPC_REG_MSR,1<<13)
        output=[];draws=[]
        def hook(uc,address,size,_):
            a=uc.reg_read(UC_PPC_REG_3);b=uc.reg_read(UC_PPC_REG_4)
            if address==stubs['GX_ClearVtxDesc']:desc.clear()
            elif address==stubs['GX_SetVtxDesc']:desc[a]=b
            elif address==stubs['GX_SetVtxAttrFmt']:fmt[b]=(uc.reg_read(UC_PPC_REG_5),uc.reg_read(UC_PPC_REG_6))
            elif address in (stubs['GX_SetTevOp'],stubs['GX_SetBlendMode']):pass
            elif address==stubs['GX_Begin']:
                total=0
                for attribute,kind in desc.items():
                    if kind==none:continue
                    if kind==index8:total+=1
                    elif attribute==pos:total+=12 if fmt[pos]==(xyz,f32)else 0
                    elif attribute==clr:total+=4
                    else:total+=8
                draws.append((uc.reg_read(UC_PPC_REG_5),total))
            else:return
            uc.reg_write(UC_PPC_REG_PC,uc.reg_read(UC_PPC_REG_LR))
        u.hook_add(UC_HOOK_CODE,hook)
        u.hook_add(UC_HOOK_MEM_WRITE,lambda uc,access,address,size,value,data:output.append(size),begin=0xcc008000,end=0xcc008fff)
        u.emu_start(symbols['run_rect'],0x80001000,count=100000)
        self.assertEqual(len(draws),1)
        count,width=draws[0]
        return sum(output),count*width

    def test_original_textured_backdrop_exposes_missing_coordinates(self):
        actual,declared=self.emit(43,'home')
        self.assertEqual((actual,declared),(64,96))

    def test_original_plain_gui_control(self):
        self.assertEqual(self.emit(43,'gui'),(64,64))

    def test_fixed_rectangle_matches_inherited_home_and_movie(self):
        for state in ('home','movie','gui'):
            with self.subTest(state=state):self.assertEqual(self.emit(46,state),(64,64))

    def test_outline_keeps_all_five_vertices(self):
        self.assertEqual(self.emit(46,'home',0),(80,80))

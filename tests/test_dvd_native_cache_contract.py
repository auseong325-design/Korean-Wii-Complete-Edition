"""Execute the pinned libdi archive, not a reimplementation of its cache."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from kwce.toolchain import tool

ROOT=Path(__file__).resolve().parents[1]

class LibdiCacheContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        w=Path(cls.tmp.name)
        archive=ROOT/'tools/linux/dvd-player-sdk-r2490/opt/devkitpro/libogc2/wii/lib/libdi.a'
        probe=ROOT/'tools/linux/dvd-probe-sdk-r2490/opt/devkitpro/libogc2/wii/lib/libdi.a'
        if archive.read_bytes()!=probe.read_bytes():raise AssertionError('Probe/player libdi differs')
        cls.archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest()
        subprocess.run([str(tool('powerpc-eabi-ar')),'x',str(archive)],cwd=w,check=True)
        objects=list(w.glob('*.o'))
        obj=next(p for p in objects if ' DI_ReadDVD\n' in subprocess.check_output([str(tool('powerpc-eabi-nm')),str(p)],text=True))
        subprocess.run([str(tool('powerpc-eabi-objcopy')),'--globalize-symbol=DI_ReadDVDptr',str(obj)],check=True)
        (w/'test.c').write_text(r'''
typedef unsigned int u32;
extern int DI_Init(void), DI_ReadDVD(void *,u32,u32);
extern void DI_UseCache(int);
extern int (*DI_ReadDVDptr)(void *,u32,u32);
static unsigned char page[64], cache[26*2048] __attribute__((aligned(32)));
static unsigned char out[2048] __attribute__((aligned(32)));
static int count, sectors, fault, locks, unlocks;
void *malloc(u32 n) { return page; }
void *memalign(u32 a,u32 n) { return cache; }
void free(void *p) {}
void *memset(void *p,int c,u32 n) {unsigned char *q=p;while(n--)*q++=c;return p;}
void *memcpy(void *d,const void*s,u32 n) {unsigned char*q=d;const unsigned char*p=s;while(n--)*q++=*p++;return d;}
int IOS_Open(const char*p,int mode) {return 7;}
int LWP_MutexInit(u32*m,int r) {*m=1;return 0;}
int LWP_MutexLock(u32 m) {++locks;return 0;}
int LWP_MutexUnlock(u32 m) {++unlocks;return 0;}
static int read_device(void*p,u32 n,u32 lba) {++count;sectors=n;if(fault)return 1;memset(p,0x5a,n*2048);return 0;}
int run(int which) {
 if(which==1 || which==4) DI_UseCache(0);
 if(DI_Init()!=0)return 10;
 if(which==2) DI_UseCache(0); /* Too late: allocated cache survives. */
 DI_ReadDVDptr=read_device;
 fault=which>=3;
 memset(out,0xa5,sizeof out);
 int ret=DI_ReadDVD(out,1,256);
 if(count!=1 || locks!=1 || unlocks!=1)return 11;
 if(sectors!=((which==1 || which==4)?1:26))return 12;
 if(ret!=(fault?1:0))return 13;
 if(fault && which==3 && out[0]!=0xa5)return 14;
 if(!fault && (out[0]!=0x5a || out[2047]!=0x5a))return 15;
 return 1;
}
''')
        subprocess.run([str(tool('powerpc-eabi-gcc')),'-Os','-ffreestanding','-fno-builtin','-msdata=none','-nostdlib',
                        '-Wl,-Ttext=0x80004000,-e,run,--gc-sections',str(w/'test.c'),str(obj),'-o',str(w/'test.elf'),'-lgcc'],check=True,capture_output=True)
        nm=subprocess.check_output([str(tool("powerpc-eabi-nm")),str(w/"test.elf")],text=True)
        cls.symbols={x.split()[2]:int(x.split()[0],16) for x in nm.splitlines() if len(x.split())==3}
        import struct
        data=(w/'test.elf').read_bytes()
        assert data[:6]==b'\x7fELF\x01\x02'
        cls.entry=struct.unpack_from('>I',data,24)[0]
        phoff=struct.unpack_from('>I',data,28)[0]
        phsize,phnum=struct.unpack_from('>HH',data,42)
        cls.segments=[]
        for i in range(phnum):
            kind,offset,addr,physical,size,memsize,flags,align=struct.unpack_from('>8I',data,phoff+i*phsize)
            if kind==1:cls.segments.append((addr,data[offset:offset+size]))
        # The archive uses EABI small data; the bare test link omits CRT setup.
        init=cls.symbols['DI_Init']
        code=next(buf[init-at:init-at+4] for at,buf in cls.segments if at<=init<at+len(buf))
        word=int.from_bytes(code,'big')
        assert word>>26==32 and (word>>16)&31==13
        displacement=struct.unpack('>h',code[2:])[0]
        cls.sda=cls.symbols['di_fd']-displacement

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_archive_cache_expansion_and_preinit_policy(self):
        from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN
        from unicorn.ppc_const import UC_PPC_REG_1, UC_PPC_REG_3, UC_PPC_REG_LR, UC_PPC_REG_PC, UC_PPC_REG_13, UC_PPC_REG_2
        for case in range(5):
            with self.subTest(case=case):
                u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN)
                u.mem_map(0x80000000,0x400000);u.mem_map(0xcd800000,0x1000)
                for at,data in self.segments:u.mem_write(at,data)
                u.reg_write(UC_PPC_REG_13,self.sda)
                u.reg_write(UC_PPC_REG_2,self.symbols.get("_SDA2_BASE_",0))
                u.mem_write(0xcd800064,b'\xff'*4)
                u.reg_write(UC_PPC_REG_1,0x803ff000);u.reg_write(UC_PPC_REG_3,case);u.reg_write(UC_PPC_REG_LR,0x80001000)
                u.emu_start(self.entry,0x80001000,count=2000000)
                self.assertEqual(u.reg_read(UC_PPC_REG_PC),0x80001000)
                self.assertEqual(u.reg_read(UC_PPC_REG_3),1)

if __name__=='__main__':unittest.main()

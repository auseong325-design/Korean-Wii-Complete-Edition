"""Run patched DVD read/error paths as PPC with synthetic device responses."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'workspace/private/unicorn-2.1.1'))
from kwce.dvd_player_fork import patches
from kwce.toolchain import tool


def patched(name, revision=51):
    text = (ROOT / 'external/other-tools/wiimc' / name).read_text()
    for path, old, new in patches(revision):
        if path == name:
            if text.count(old) != 1:
                raise AssertionError(f'Non-unique patch in {name}')
            text = text.replace(old, new)
    return text


class PlayerReadTests(unittest.TestCase):
    revision = 51

    @classmethod
    def setUpClass(cls):
        device = patched('source/mplayer/libdvdcss/device.c', cls.revision)
        start = device.index('static unsigned kwce_di_trace_count;' if cls.revision>=52 else 'static int di_read(dvdcss_t')
        end = device.index('\n#ifdef GEKKO\n#define BUFFER_SECTOR_SIZE', start)
        reads = device[start:end]
        ifo = patched('source/mplayer/libdvdread4/ifo_read.c', cls.revision)
        start = ifo.index('ifo_handle_t *ifoOpenVMGI(')
        end = ifo.index('ifo_handle_t *ifoOpenVTSI(', start)
        source = r'''
typedef unsigned int uint32_t;
typedef unsigned int size_t;
#define NULL ((void*)0)
#define DVDCSS_BLOCK_SIZE 2048
#define DVD_READ_INFO_FILE 0
#define DVD_READ_INFO_BACKUP_FILE 1
#define print_debug(...) ((void)0)
#define fprintf(...) ((void)0)
struct dvdcss_s { int i_pos; };
typedef struct dvdcss_s *dvdcss_t;
struct iovec { void *iov_base; size_t iov_len; };
typedef int dvd_reader_t;
typedef struct { void *file; } ifo_handle_t;
static unsigned char scratch[4096], output[4096];
static ifo_handle_t handle;
static int result, frees, copies, mode, opens, closes, current, parses;
static int trace_count, boundary, order_error, hang;
void *memalign(int a, int n) { return scratch; }
void *malloc(int n) { return &handle; }
void free(void *p) { ++frees; }
void *memset(void *p, int c, size_t n) {
    unsigned char *q=p; while(n--) *q++=c; return p;
}
void *memcpy(void *d, const void *s, size_t n) {
    unsigned char *a=d; const unsigned char *b=s;
    ++copies; while(n--) *a++=*b++; return d;
}
int DI_ReadDVD(void *p, int n, int pos) {
    if(hang==1) while(1) __asm__ volatile("");
    return result;
}
int DI_GetError(uint32_t *e) {
    if(hang==2) while(1) __asm__ volatile("");
    if(trace_count && boundary!=3) order_error=1;
    *e=0; return 0;
}
int DI_GetStatus(void) { return 1; }
int eq(const char *a, const char *b) {
    while(*a && *a==*b) { ++a; ++b; }
    return *a==*b;
}
void KwceDvdTrace(const char *s, int a, int b) {
    if(eq(s,"di-begin")) { boundary=1; ++trace_count; }
    if(eq(s,"di-end")) { if(boundary!=1) order_error=1; boundary=2; ++trace_count; }
    if(eq(s,"di-error-begin")) { if(boundary!=2) order_error=1; boundary=3; }
}
void *DVDOpenFile(dvd_reader_t *d, int title, int kind) {
    ++opens; current=kind;
    if(mode==3 || (mode==2 && kind==0)) return NULL;
    return (void*)(kind+1);
}
void DVDCloseFile(void *p) { if(p) ++closes; }
int ifoRead_VMG(ifo_handle_t *h) {
    ++parses; return mode==0 || ((mode==1 || mode==2) && current==1);
}
void ifoClose(ifo_handle_t *h) { DVDCloseFile(h->file); free(h); }
'''+reads+ifo[start:end]+r'''
int run(int test) {
    frees=copies=opens=closes=parses=0;
    if(test<6) {
        struct dvdcss_s d={7};
        struct iovec v={output,2048};
        result=(test%3==0)?0:(test%3==1)?1:-5;
        int r=test<3?di_read(&d,output,1):di_readv(&d,&v,1);
        if(result==0) return r==(test<3?1:2048) && d.i_pos==8 && copies==1 && frees==1;
        return r==-1 && d.i_pos==7 && copies==0 && frees==1;
    }
    mode=test-6;
    ifo_handle_t *h=ifoOpenVMGI(NULL);
    if(mode==0) return h && opens==1 && parses==1 && closes==0 && frees==0;
    if(mode==1) return h && opens==2 && parses==2 && closes==1 && frees==0;
    if(mode==2) return h && opens==2 && parses==1 && closes==0 && frees==0;
    if(mode==3) return !h && opens==2 && parses==0 && closes==0 && frees==1;
    return !h && opens==2 && parses==2 && closes==2 && frees==1;
}
'''
        if cls.revision>=52:
            source += r'''
int trace_test(int test) {
    struct dvdcss_s d={7};
    struct iovec v={output,2048};
    kwce_di_trace_count=trace_count=boundary=order_error=hang=0;
    result=0;
    if(test==0) {
        for(int i=0;i<40;++i) {
            if(di_read(&d,output,1)!=1) return 0;
        }
        return trace_count==64 && kwce_di_trace_count==32 && !order_error;
    }
    if(test==1) {
        result=1;
        return di_readv(&d,&v,1)==-1 && boundary==3 && !order_error;
    }
    hang=test==2?1:2;
    result=1;
    if(test==4) return di_readv(&d,&v,1);
    return di_read(&d,output,1);
}
'''
        cls.tmp = tempfile.TemporaryDirectory(dir=ROOT/'workspace/private')
        work = Path(cls.tmp.name)
        (work/'test.c').write_text(source)
        subprocess.run([str(tool('powerpc-eabi-gcc.exe')), '-Os', '-ffreestanding',
                        '-fno-builtin', '-msdata=none', '-nostdlib',
                        '-Wl,-Ttext=0x80004000,-e,run', str(work/'test.c'),
                        '-o', str(work/'test.elf'), '-lgcc'], check=True, capture_output=True)
        subprocess.run([str(tool('powerpc-eabi-objcopy.exe')), '-O','binary',
                        str(work/'test.elf'),str(work/'test.bin')],check=True)
        nm=subprocess.check_output([str(tool('powerpc-eabi-nm.exe')),str(work/'test.elf')],text=True)
        cls.entry=int(next(x.split()[0] for x in nm.splitlines() if x.endswith(' T run')),16)
        cls.symbols={x.split()[2]:int(x.split()[0],16) for x in nm.splitlines() if len(x.split())==3}
        cls.code=(work/'test.bin').read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_device_results_and_ifo_backup(self):
        from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN
        from unicorn.ppc_const import UC_PPC_REG_1, UC_PPC_REG_3, UC_PPC_REG_LR
        for case in range(11):
            with self.subTest(case=case):
                u=Uc(UC_ARCH_PPC, UC_MODE_32|UC_MODE_BIG_ENDIAN)
                u.mem_map(0x80000000,0x200000)
                u.mem_write(0x80004000,self.code)
                u.reg_write(UC_PPC_REG_1,0x801ff000)
                u.reg_write(UC_PPC_REG_3,case)
                u.reg_write(UC_PPC_REG_LR,0x80001000)
                u.emu_start(self.entry,0x80001000,count=100000)
                self.assertEqual(u.reg_read(UC_PPC_REG_3),1)


class PlayerTraceTests(PlayerReadTests):
    revision = 53

    def test_bounded_trace_and_blocked_call_boundaries(self):
        from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN
        from unicorn.ppc_const import UC_PPC_REG_1, UC_PPC_REG_3, UC_PPC_REG_LR, UC_PPC_REG_PC
        for case in range(4):
            with self.subTest(case=case):
                u=Uc(UC_ARCH_PPC, UC_MODE_32|UC_MODE_BIG_ENDIAN)
                u.mem_map(0x80000000,0x200000)
                u.mem_write(0x80004000,self.code)
                u.reg_write(UC_PPC_REG_1,0x801ff000)
                u.reg_write(UC_PPC_REG_3,case)
                u.reg_write(UC_PPC_REG_LR,0x80001000)
                u.emu_start(self.symbols['trace_test'],0x80001000,count=1000000)
                if case<2:
                    self.assertEqual(u.reg_read(UC_PPC_REG_PC),0x80001000)
                    self.assertEqual(u.reg_read(UC_PPC_REG_3),1)
                else:
                    self.assertNotEqual(u.reg_read(UC_PPC_REG_PC),0x80001000)
                    last=int.from_bytes(u.mem_read(self.symbols['boundary'],4),'big')
                    self.assertEqual(last,1 if case==2 else 3)


class PlayerFailureReturnTests(PlayerReadTests):
    revision = 54

    def test_unresponsive_error_query_cannot_block_failed_read(self):
        self.check_unresponsive_query(3)
        self.check_unresponsive_query(4)

    def check_unresponsive_query(self,case):
        from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN
        from unicorn.ppc_const import UC_PPC_REG_1, UC_PPC_REG_3, UC_PPC_REG_LR, UC_PPC_REG_PC
        u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN)
        u.mem_map(0x80000000,0x200000);u.mem_write(0x80004000,self.code)
        u.reg_write(UC_PPC_REG_1,0x801ff000);u.reg_write(UC_PPC_REG_3,case)
        u.reg_write(UC_PPC_REG_LR,0x80001000)
        u.emu_start(self.symbols['trace_test'],0x80001000,count=100000)
        self.assertEqual(u.reg_read(UC_PPC_REG_PC),0x80001000)
        self.assertEqual(u.reg_read(UC_PPC_REG_3),0xffffffff)
        self.assertEqual(int.from_bytes(u.mem_read(self.symbols['boundary'],4),'big'),2)
        self.assertEqual(int.from_bytes(u.mem_read(self.symbols['copies'],4),'big'),0)
        self.assertEqual(int.from_bytes(u.mem_read(self.symbols['frees'],4),'big'),1)


class PlayerDvdVideoReadTests(PlayerFailureReturnTests):
    revision = 55


class PlayerExactReadTests(PlayerFailureReturnTests):
    revision = 56

    def test_cache_policy_precedes_only_di_initialization(self):
        source=patched('source/wiimc.cpp',56)
        self.assertEqual(source.count('DI_Init();'),1)
        self.assertIn('DI_UseCache(false);\n\tDI_Init();',source)
        self.assertNotIn('DI_UseCache(false)',patched('source/wiimc.cpp',55))
        device=patched('source/mplayer/libdvdcss/device.c',56)
        self.assertIn('KwceDvdTrace("di-size",kwceSeq,blocks)',device)
        self.assertIn('KwceDvdTrace("di-size",kwceSeq,len / DVDCSS_BLOCK_SIZE)',device)


class DvdVideoPermissionTests(unittest.TestCase):
    # Frozen R55 regression; its polarity is known wrong. R58 tests correct it.
    revision = 55
    disable_bit = False
    @classmethod
    def setUpClass(cls):
        source = patched('source/wiimc.cpp', cls.revision)
        start = source.index('static int kwceDvdVideoBefore')
        end = source.index('int main(int argc', start)
        helper = source[start:end]
        cls.source = source
        cls.tmp = tempfile.TemporaryDirectory()
        w = Path(cls.tmp.name)
        (w/'gate.c').write_text(helper + '\nint run(int restore) { if(restore) KwceRestoreDvdVideo(); else KwceEnableDvdVideo(); return kwceDvdVideoAfter; }')
        subprocess.run([str(tool('powerpc-eabi-gcc.exe')), '-Os', '-ffreestanding',
                        '-fno-builtin', '-msdata=none', '-nostdlib',
                        '-Wl,-Ttext=0x80004000,-e,run', str(w/'gate.c'),
                        '-o', str(w/'gate.elf')], check=True, capture_output=True)
        subprocess.run([str(tool('powerpc-eabi-objcopy.exe')), '-O','binary',str(w/'gate.elf'),str(w/'gate.bin')],check=True)
        nm=subprocess.check_output([str(tool('powerpc-eabi-nm.exe')),str(w/'gate.elf')],text=True)
        cls.entry=int(next(x.split()[0] for x in nm.splitlines() if x.endswith(' T run')),16)
        cls.code=(w/'gate.bin').read_bytes()

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_permission_bit_and_restore_preserve_unrelated_hardware_flags(self):
        from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ
        from unicorn.ppc_const import UC_PPC_REG_1, UC_PPC_REG_3, UC_PPC_REG_LR, UC_PPC_REG_PC
        for allowed in (False,True):
            for initial in (0, 0x00200000, 0xa5800017, 0xa5a00017):
                with self.subTest(allowed=allowed,initial=initial):
                    u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN)
                    u.mem_map(0x80000000,0x200000);u.mem_write(0x80004000,self.code)
                    u.mem_map(0xcd800000,0x1000)
                    u.mem_write(0xcd800064,(0xffffffff if allowed else 0).to_bytes(4,'big'))
                    u.mem_write(0xcd800180,initial.to_bytes(4,'big'))
                    accesses=[]
                    u.hook_add(UC_HOOK_MEM_WRITE|UC_HOOK_MEM_READ,lambda uc,access,addr,size,value,data: accesses.append((access,addr,size)),begin=0xcd800180,end=0xcd800183)
                    def call(restore):
                        u.reg_write(UC_PPC_REG_1,0x801ff000);u.reg_write(UC_PPC_REG_3,restore)
                        u.reg_write(UC_PPC_REG_LR,0x80001000)
                        u.emu_start(self.entry,0x80001000,count=10000)
                        self.assertEqual(u.reg_read(UC_PPC_REG_PC),0x80001000)
                    call(0)
                    expected=(initial & ~0x00200000 if self.disable_bit else initial | 0x00200000) if allowed else initial
                    self.assertEqual(int.from_bytes(u.mem_read(0xcd800180,4),'big'),expected)
                    # Another owner changes an unrelated bit before our cleanup.
                    changed=expected^0x10
                    u.mem_write(0xcd800180,changed.to_bytes(4,'big'))
                    call(1)
                    self.assertEqual(int.from_bytes(u.mem_read(0xcd800180,4),'big'),initial^0x10)
                    call(1)  # cleanup is idempotent
                    self.assertEqual(int.from_bytes(u.mem_read(0xcd800180,4),'big'),initial^0x10)
                    if not allowed: self.assertEqual(accesses,[])
                    else: self.assertTrue(all(a==0xcd800180 and n==4 for _,a,n in accesses))

    def test_gate_runs_after_ios_reload_and_before_drive_init(self):
        main=self.source[self.source.index('int main(int argc'):]
        self.assertLess(main.index('handleIOSreload();'),main.index('KwceEnableDvdVideo();'))
        self.assertLess(main.index('KwceEnableDvdVideo();'),main.index('DI_Init();'))
        self.assertIn('DI_Close();\n\tKwceDvdTrace("drive-close",1,0);\n\tKwceRestoreDvdVideo();',self.source)
        old=patched('source/wiimc.cpp',54)
        self.assertNotIn('KwceEnableDvdVideo',old)


if __name__ == '__main__':
    unittest.main()

class DvdDisablePolarityTests(DvdVideoPermissionTests):
    revision = 58
    disable_bit = True

    def test_hbc_clear_contract_and_unambiguous_trace(self):
        # Independent contract from HBC main.c: mask32(HW_DIFLAGS,1<<21,0).
        # This must reject the historical set-bit implementation.
        self.assertIn('*flags = old & ~0x00200000u;', self.source)
        self.assertNotIn('*flags = old | 0x00200000u;', self.source)
        self.assertIn('KwceDvdTrace("dvd-disable-bit",', self.source)
        self.assertNotIn('KwceDvdTrace("dvd-video-mode",', self.source)

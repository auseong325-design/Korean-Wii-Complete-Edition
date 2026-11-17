"""Run v2 C with injected DVD errors and a ninth-event SD sync failure."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('cc'), 'host C compiler required')
class ProbeV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir=ROOT/'workspace/private')
        root=Path(cls.temp.name)
        text=(ROOT/'homebrew/kwce-dvd-probe/r2/source/main.c').read_text()
        text=text[text.index('static FILE *report;'):text.index('\nint main(void)')]
        text=text.replace('*(vu32 *)0xcd800064 == 0xffffffff','fake_ahb')
        for addr in ['0xcd806000','0xcd80601c','0xcd806004']:
            text=text.replace('*(vu32 *)'+addr,'fake_register('+addr+')')
        prefix=r'''
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
typedef uint64_t u64;
typedef unsigned u32;
#define ATTRIBUTE_ALIGN(n) __attribute__((aligned(n)))
#define DVD_READY 1
#define DVD_INIT 2
#define usleep(n) ((void)0)
#define fatInitDefault() 1
#define IOS_GetVersion() 58
static int quiet_printf(const char *fmt, ...) {return 0;}
#define printf quiet_printf
static int fake_ahb=1,di_fd,result,reads,error_queries,closes,mmio,fail_sync,sync_calls;
static u64 ticks;
static u64 gettime(void) {return ticks+=10000;}
static unsigned ticks_to_millisecs(u64 t) {return t/1000;}
static unsigned fake_register(unsigned a) {++mmio;return a==0xcd806000?4:a==0xcd80601c?0:2;}
static void DI_UseCache(bool v) {}
static int DI_Init(void) {di_fd=0;return 0;}
static void DI_Mount(void) {}
static int DI_GetStatus(void) {return 1;}
static int DI_ReadDVD(void *p,unsigned count,unsigned lba) {++reads;memset(p,0x42,count*2048);return result;}
static int DI_GetError(uint32_t *p) {++error_queries;return -99;}
static void DI_Close(void) {++closes;}
static int fake_fsync(int fd) {if(++sync_calls==fail_sync){errno=EIO;return -1;}return 0;}
#define fsync fake_fsync
'''
        suffix=r'''
int run_case(const char *path,int read_result,int fail_at) {
    result=read_result;fail_sync=fail_at;
    sequence=ticks=reads=error_queries=closes=mmio=sync_calls=log_phase=log_errno=have_read=0;
    last_read_result=last_read_status=0;last_di_status=last_di_control=last_di_cover=0;log_ok=1;
    report=fopen(path,"w");if(!report)return -1;
    probe();show_summary();fclose(report);
    if(error_queries)return -2;
    if(fail_at)return reads==1 && closes==0 && mmio==3 && log_phase==3 && log_errno==EIO &&
        sequence==9 && last_read_result==1 && last_di_status==4 && last_di_control==0 && last_di_cover==2 &&
        !strcmp(ram_events[8].tag,"di-state");
    if(read_result)return reads==1 && closes==0 && mmio==3 && log_ok && last_read_result==read_result;
    return reads==6 && closes==1 && mmio==0 && log_ok;
}
'''
        (root/'probe.c').write_text(prefix+text+suffix)
        subprocess.run(['cc','-std=c11','-shared','-fPIC',str(root/'probe.c'),'-o',str(root/'probe.so')],capture_output=True,check=True)
        cls.lib=ctypes.CDLL(str(root/'probe.so'));cls.lib.run_case.argtypes=[ctypes.c_char_p,ctypes.c_int,ctypes.c_int]

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_first_positive_and_negative_failure_send_no_error_query_or_further_read(self):
        path=Path(self.temp.name)/'result.log'
        for result in (1,-5):
            self.assertEqual(self.lib.run_case(bytes(path),result,0),1)
            text=path.read_text()
            self.assertIn('halt-read',text);self.assertNotIn('complete',text)
            self.assertEqual(text.count('read-begin'),1)

    def test_ninth_event_fsync_failure_preserves_phase_errno_and_ram_registers(self):
        path=Path(self.temp.name)/'sync.log'
        self.assertEqual(self.lib.run_case(bytes(path),1,9),1)
        text=path.read_text();self.assertIn('9 di-state',text)
        self.assertNotIn('error-begin',text);self.assertNotIn('complete',text)

    def test_six_successful_reads_still_finish(self):
        path=Path(self.temp.name)/'success.log'
        self.assertEqual(self.lib.run_case(bytes(path),0,0),1)
        self.assertIn('complete',path.read_text())


if __name__=='__main__':unittest.main()

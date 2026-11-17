"""Exercise the actual C probe boundaries with synthetic drive responses."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from kwce.dvd_probe import PATHS, sd_files

ROOT = Path(__file__).resolve().parents[1]


class ProbePackageTests(unittest.TestCase):
    def test_payload_cannot_replace_existing_player_or_priiloader(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'workspace/private') as folder:
            root = Path(folder)
            rows = []
            for rel in PATHS:
                path = root/rel; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture')
                rows.append(dict(path=rel, bytes=7, sha256=hashlib.sha256(b'fixture').hexdigest()))
            meta = dict(kind='dvd-read-probe-v1', nand_write=False, network=False,
                        content_logging=False, ios_reload=False, sd_files=rows)
            def write():
                raw = json.dumps(meta).encode()
                (root/'package-manifest.json').write_bytes(raw)
                (root/'package-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest())
            write(); self.assertEqual(len(sd_files(root)[1]), 4)
            rows[0]['path'] = 'apps/Priiloader/hacks_hash.ini'
            write()
            with self.assertRaises(ValueError): sd_files(root)
            rows[0]['path'] = '../escape'
            write()
            with self.assertRaises(ValueError): sd_files(root)


@unittest.skipUnless(shutil.which('cc'), 'host C compiler required for SDK-mocked probe')
class ProbeExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(dir=ROOT/'workspace/private')
        folder = Path(cls.tmp.name)
        original = (ROOT/'homebrew/kwce-dvd-probe/source/main.c').read_text()
        core = original[original.index('static FILE *report;'):original.index('\nint main(void)')]
        core = core.replace('*(vu32 *)0xcd800064 == 0xffffffff', 'fake_ahb')
        core = core.replace('sd:/', 'sd/')  # host NTFS cannot create a colon directory
        prefix = r'''
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
#define ATTRIBUTE_ALIGN(n) __attribute__((aligned(n)))
#define DVD_READY 1
#define DVD_INIT 2
#define usleep(n) ((void)0)
#define fatInitDefault() 1
#define IOS_GetVersion() 58
static u64 clock_ticks;
static int di_fd, fake_ahb, fake_result, fake_mount, reads, commands, metadata_seen, protocol_error;
static int last_begin_index, last_begin_size, begin_seen, closed;
static u64 gettime(void) { return clock_ticks += 10000; }
static unsigned ticks_to_millisecs(u64 t) { return t / 1000; }
static void DI_UseCache(bool on) { if (on) protocol_error = 1; }
static int DI_Init(void) { ++commands; di_fd = 0; return 0; }
static void DI_Mount(void) { ++commands; }
static int DI_GetStatus(void) { return fake_mount ? DVD_READY : DVD_INIT; }
static int DI_ReadDVD(void *buf, unsigned size, unsigned lba) {
    static const unsigned expected[] = {0,16,256};
    if (!begin_seen || last_begin_index != reads % 3 || last_begin_size != (reads < 3 ? 1 : 26) ||
        size != (reads < 3 ? 1u : 26u) || lba != expected[reads % 3]) protocol_error = 1;
    begin_seen = 0; ++reads; ++commands;
    memset(buf, 0xa5, size * 2048); /* failure data must never become metadata */
    return fake_result;
}
static int DI_GetError(uint32_t *error) { *error = 123; ++commands; return 0; }
static void DI_Close(void) { ++closed; }
'''
        # Observe trace arguments while retaining the actual logger and flush gate.
        core = core.replace('static int trace(', 'static int actual_trace(')
        marker = 'static int new_report(void)'
        observer = r'''
static int trace(const char *tag, int a, int b, unsigned ms) {
    if (!strcmp(tag, "read-begin")) { begin_seen = 1; last_begin_index = a; last_begin_size = b; }
    if (!strcmp(tag, "metadata")) ++metadata_seen;
    return actual_trace(tag, a, b, ms);
}
'''
        core = core.replace(marker, observer + marker)
        harness = r'''
int run_case(const char *path, int result, int ahb, int mounted, int full) {
    clock_ticks=sequence=reads=commands=metadata_seen=protocol_error=closed=begin_seen=0;
    log_ok=1; di_fd=-1; fake_result=result; fake_ahb=ahb; fake_mount=mounted;
    report=fopen(full ? "/dev/full" : path,"w"); if(!report)return -1;
    probe(); fclose(report);
    if(protocol_error)return -2;
    if(full || !ahb)return commands==0;
    if(!mounted)return reads==0 && closed==0;
    return reads==6 && closed==1 && metadata_seen==(result==0 ? 6 : 0);
}
int new_report_case(void) {
    int ok=new_report(); if(ok) { fputs("new\n",report); fclose(report); } return ok;
}
int check_metadata(unsigned char *p,unsigned lba) { return metadata_kind(p,lba); }
'''
        (folder/'probe.c').write_text(prefix+core+harness)
        subprocess.run(['cc', '-std=c11', '-shared', '-fPIC', str(folder/'probe.c'),
                        '-o', str(folder/'probe.so')], capture_output=True, check=True)
        cls.lib = ctypes.CDLL(str(folder/'probe.so'))
        cls.lib.run_case.argtypes = [ctypes.c_char_p]+[ctypes.c_int]*4
        cls.lib.check_metadata.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint]

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_zero_positive_and_negative_results_with_durable_boundaries(self):
        output = Path(self.tmp.name)/'numeric.log'
        for result in (0, 1, -5):
            self.assertEqual(self.lib.run_case(bytes(output), result, 1, 1, 0), 1)
            text = output.read_text()
            self.assertEqual(text.count(' read-begin '), 6)
            self.assertEqual(text.count(' read-end '), 6)
            self.assertNotIn('a5a5', text)
            if result: self.assertNotIn(' metadata ', text)

    def test_no_ahb_mount_timeout_or_sd_failure_stops_reads(self):
        output = Path(self.tmp.name)/'gates.log'
        for args in ((0,0,1,0), (0,1,0,0), (0,1,1,1)):
            self.assertEqual(self.lib.run_case(bytes(output), *args), 1)

    def test_udf_anchor_rejects_bad_checksum_and_wrong_location(self):
        block = (ctypes.c_ubyte*2048)()
        block[0]=2; block[13]=1; block[4]=3
        self.assertEqual(self.lib.check_metadata(block,256),8)
        block[4]=4
        self.assertEqual(self.lib.check_metadata(block,256),0)
        block[13]=2; block[4]=4
        self.assertEqual(self.lib.check_metadata(block,256),0)

    def test_existing_report_is_never_overwritten(self):
        root = Path(self.tmp.name)/'fat-test'
        (root/'sd/kwce-rc').mkdir(parents=True)
        original = root/'sd/kwce-rc/dvd-probe-0001.txt'
        original.write_text('preserve\n')
        previous = Path.cwd()
        try:
            os.chdir(root)
            self.assertEqual(self.lib.new_report_case(), 1)
        finally:
            os.chdir(previous)
        self.assertEqual(original.read_text(), 'preserve\n')
        self.assertEqual((original.parent/'dvd-probe-0002.txt').read_text(), 'new\n')


if __name__ == '__main__': unittest.main()

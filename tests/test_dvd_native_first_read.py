"""Run the bounded startup reader with a synthetic device, no real media."""
import ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class FirstReadTests(unittest.TestCase):
    def test_success_and_each_failure_stop_without_retry(self):
        source=(ROOT/'homebrew/kwce-dvd/r57/source/kwce/kwce_read_probe.h').read_text()
        harness='''#include <stdbool.h>
#include <stdint.h>
static int calls, failure, tracecalls, bad;
void KwceDvdTrace(const char*s,int a,int b){++tracecalls;}
int DI_GetStatus(void){return calls?5:1;}
int DI_ReadDVD(void*p,unsigned n,unsigned pos){
 const unsigned expected[]={0,16,256};
 if(calls>=3 || n!=1 || pos!=expected[calls] || ((uintptr_t)p&31))bad=1;
 ++calls;return calls==failure?1:0;
}
'''+source+'''
int run(int f){calls=tracecalls=bad=0;failure=f;bool r=KwceProbeFirstReads();
int wanted=f?f:3;return !bad && calls==wanted && tracecalls==wanted*3 && r==(f==0);}
'''
        with tempfile.TemporaryDirectory()as tmp:
            p=Path(tmp);(p/'test.c').write_text(harness)
            subprocess.run(['cc','-std=c11','-shared','-fPIC','-Wall','-Werror',str(p/'test.c'),'-o',str(p/'test.so')],check=True,capture_output=True)
            lib=ctypes.CDLL(str(p/'test.so'));lib.run.argtypes=[ctypes.c_int]
            for f in range(4):self.assertEqual(lib.run(f),1)
if __name__=='__main__':unittest.main()

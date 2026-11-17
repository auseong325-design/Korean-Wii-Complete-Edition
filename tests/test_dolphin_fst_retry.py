"""Execute only our x64 thunk against synthetic callbacks, never Dolphin/NAND."""
import ctypes as C,json,struct,sys,unittest
from pathlib import Path
from kwce.dolphin_fst_retry import retry_thunk,patch_fst_retry

ROOT=Path(__file__).resolve().parents[1]

class FstRetryTests(unittest.TestCase):
    def test_wrong_binary_refused(self):
        with self.assertRaises(ValueError):patch_fst_retry(bytes(512))

    @unittest.skipUnless(sys.platform=='win32' and C.sizeof(C.c_void_p)==8,'Windows x64 only')
    def test_native_abi_arguments_bounded_attempts_success_and_failure(self):
        k=C.WinDLL('kernel32',use_last_error=True)
        k.VirtualAlloc.argtypes=[C.c_void_p,C.c_size_t,C.c_ulong,C.c_ulong];k.VirtualAlloc.restype=C.c_void_p
        k.VirtualProtect.argtypes=[C.c_void_p,C.c_size_t,C.c_ulong,C.POINTER(C.c_ulong)]
        k.VirtualFree.argtypes=[C.c_void_p,C.c_size_t,C.c_ulong]
        rename_type=C.WINFUNCTYPE(C.c_ubyte,C.c_void_p,C.c_void_p);sleep_type=C.WINFUNCTYPE(None,C.c_ulong)
        for answers,expected_calls,expected_sleeps in [([1],1,0),([0,1],2,1),([0,0,0],3,2)]:
            with self.subTest(answers=answers):
                calls=[];sleeps=[]
                def rename(a,b):
                    calls.append((a,b));return answers[min(len(calls)-1,len(answers)-1)]
                rc=rename_type(rename);sc=sleep_type(lambda ms:sleeps.append(ms))
                ptr=k.VirtualAlloc(None,4096,0x3000,4)
                if not ptr:raise C.WinError(C.get_last_error())
                try:
                    code=bytearray(4096);thunk=retry_thunk(ptr,ptr+256,ptr+384);code[:len(thunk)]=thunk
                    bridge=b'\x48\xb8'+struct.pack('<Q',C.cast(rc,C.c_void_p).value)+b'\xff\xe0'
                    code[256:256+len(bridge)]=bridge
                    struct.pack_into('<Q',code,384,C.cast(sc,C.c_void_p).value)
                    C.memmove(ptr,bytes(code),4096);old=C.c_ulong()
                    if not k.VirtualProtect(ptr,4096,0x20,C.byref(old)):raise C.WinError(C.get_last_error())
                    result=rename_type(ptr)(0x1234,0x5678)
                    self.assertEqual(bool(result),bool(answers[-1]))
                    self.assertEqual(calls,[(0x1234,0x5678)]*expected_calls)
                    self.assertEqual(sleeps,[10]*expected_sleeps)
                finally:k.VirtualFree(ptr,0,0x8000)

    @unittest.skipUnless((ROOT/'workspace/sandbox/gc-v5/Dolphin-x64/Dolphin.exe').exists(),'local pinned runtime required')
    def test_locked_output_and_runtime_unwind_entry(self):
        before=(ROOT/'workspace/sandbox/gc-v5/Dolphin-x64/Dolphin.exe').read_bytes()
        after,record=patch_fst_retry(before)
        self.assertEqual(record,json.loads((ROOT/'configs/gc-fst-runtime.lock.json').read_text()))
        self.assertEqual(len(after),len(before))
        p=struct.unpack_from('<I',after,0x3c)[0];opt=p+24
        self.assertEqual(struct.unpack_from('<I',after,opt+112+3*8+4)[0],struct.unpack_from('<I',before,opt+112+3*8+4)[0]+12)
        with self.assertRaises(ValueError):patch_fst_retry(after)

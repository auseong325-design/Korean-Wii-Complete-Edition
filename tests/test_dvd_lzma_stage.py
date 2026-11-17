"""Host decoder boundary tests, not a claim of PPC/hardware qualification."""
import ctypes
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from kwce.dvd_lzma_stage import BASE, ROOT, SOURCE, compile_decoder, pack, unpack, vendor


@unittest.skipUnless(shutil.which('cc'), 'host C compiler unavailable')
class LzmaStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        lib = Path(cls.temp.name) / 'decoder.so'
        src = vendor()
        subprocess.run(['cc', '-O2', '-shared', '-fPIC', '-DKWCE_HOST_TEST',
                        '-I', str(src), str(SOURCE), str(src / 'LzmaDec.c'),
                        '-o', str(lib)], check=True, capture_output=True)
        cls.lib = ctypes.CDLL(str(lib))
        cls.fn = cls.lib.kwce_decode
        cls.fn.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                          ctypes.c_void_p, ctypes.c_uint32]
        cls.fn.restype = ctypes.c_int
        cls.raw = bytes(range(256)) * 4096 + b'end'
        cls.package = pack(cls.raw, b'local-test-decoder')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def decode(self, data, capacity=None):
        cap = len(self.raw) if capacity is None else capacity
        src = ctypes.create_string_buffer(data)
        out = ctypes.create_string_buffer(b'\xa5' * (cap + 32), cap + 32)
        result = self.fn(src, len(data), out, cap)
        self.assertEqual(out.raw[cap:], b'\xa5' * 32)
        return result, out.raw[:cap]

    def test_exact_end_marker_and_roundtrip(self):
        self.assertEqual(unpack(self.package), self.raw)
        self.assertEqual(self.decode(self.package), (1, self.raw))

    def test_capacity_mismatch_rejected_before_write(self):
        result, out = self.decode(self.package, 256)
        self.assertEqual((result, out), (0, b'\xa5' * 256))

    def test_truncation_and_trailing_bytes(self):
        for data in [self.package[:8], self.package[:-1], self.package + b'x']:
            self.assertEqual(self.decode(data)[0], 0)
            with self.assertRaises((ValueError, EOFError)):
                unpack(data)

    def test_invalid_properties_cannot_grow_arena(self):
        data = bytearray(self.package)
        offset = struct.unpack_from('>I', data, 8)[0]
        data[offset] = 0xff
        result, out = self.decode(bytes(data))
        self.assertEqual(result, 0)
        self.assertEqual(out, b'\xa5' * len(self.raw))

    def test_offsets_and_sizes_rejected_before_write(self):
        for where, value in [(0, 0), (4, 0), (8, 0), (8, 0xffffffff),
                             (12, 0xffffffff), (4, 0xffffffff)]:
            data = bytearray(self.package)
            struct.pack_into('>I', data, where, value)
            result, out = self.decode(bytes(data))
            self.assertEqual(result, 0)
            self.assertEqual(out, b'\xa5' * len(self.raw))


class PpcLzmaStageTests(unittest.TestCase):
    def test_compiled_decoder_on_powerpc(self):
        sys.path.insert(0, str(ROOT / 'workspace/private/unicorn-2.1.1'))
        import unicorn as U
        from unicorn import ppc_const as R
        code = compile_decoder()
        raw = bytes(range(256)) * 128 + b'PPC decoder boundary'
        package = pack(raw, code)
        u = U.Uc(U.UC_ARCH_PPC, U.UC_MODE_32 | U.UC_MODE_BIG_ENDIAN)
        u.mem_map(0x80000000, 0x2000000)
        u.mem_map(0x90000000, 0x100000)
        u.mem_write(BASE, code)
        u.mem_write(0x90000000, package)
        u.mem_write(0x80010000 + len(raw), b'\xa5' * 32)
        u.reg_write(R.UC_PPC_REG_1, 0x900ff000)
        u.reg_write(R.UC_PPC_REG_3, 0x90000000)
        u.reg_write(R.UC_PPC_REG_4, len(package))
        u.reg_write(R.UC_PPC_REG_5, 0x80010000)
        u.reg_write(R.UC_PPC_REG_6, len(raw))
        u.reg_write(R.UC_PPC_REG_LR, 0x80001000)
        u.emu_start(BASE, 0x80001000, count=20_000_000)
        self.assertEqual(u.reg_read(R.UC_PPC_REG_PC), 0x80001000)
        self.assertEqual(u.reg_read(R.UC_PPC_REG_3), 1)
        self.assertEqual(bytes(u.mem_read(0x80010000, len(raw))), raw)
        self.assertEqual(bytes(u.mem_read(0x80010000 + len(raw), 32)), b'\xa5' * 32)


if __name__ == '__main__':
    unittest.main()

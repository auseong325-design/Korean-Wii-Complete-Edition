"""Run the real compiled reserve path with bounded synthetic file/heap I/O."""
import hashlib
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'workspace/private/unicorn-2.1.1'))
from kwce.dvd_native_hook import compile_hook, CAVE, BANNER, ORIGINAL


class NativePrepareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        player = bytearray(512)
        for at, val in ((0, 256), (0x48, 0x80004000), (0x90, 256),
                        (0xd8, 0x80005000), (0xdc, 32), (0xe0, 0x80004000)):
            struct.pack_into('>I', player, at, val)
        player[256:] = bytes(range(256))
        cls.player = bytes(player)
        cls.blobs, cls.symbols = compile_hook(cls.player)

    def reserve(self, kind):
        from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
        from unicorn.ppc_const import UC_PPC_REG_1, UC_PPC_REG_3, UC_PPC_REG_4, UC_PPC_REG_5, UC_PPC_REG_LR, UC_PPC_REG_PC
        u = Uc(UC_ARCH_PPC, UC_MODE_32 | UC_MODE_BIG_ENDIAN)
        u.mem_map(0x80000000, 0x1800000)
        u.mem_map(0x90000000, 0x200000)
        for name, address in [('native', CAVE), ('banner', BANNER), ('payload', ORIGINAL+32)]:
            u.mem_write(address, self.blobs[name])
        def word(a, v): u.mem_write(a, struct.pack('>I', v))
        scene, image, heap = 0x80400000, 0x90100000, 0x80500000
        word(scene+0x74, 16)
        word(0x81089084, 0x80100000)
        word(0x80100018, 0x80200000)
        u.mem_write(0x80201148, b'A')
        word(0x81089030, heap)
        word(heap+0x10, heap+0x100)
        word(heap+0x100+0x1c, 0x90200000)
        content = bytearray(self.player)
        if kind == 'body': content[-1] ^= 1
        if kind == 'header': content[10] ^= 1
        if kind == 'short': content = content[:-1]
        if kind == 'extra': content += b'X'
        position, closed, freed, prepared, disabled = 0, [], [], [], []
        digest = None
        def mock(uc, address, size, _):
            nonlocal position, digest
            ret = None
            arg = uc.reg_read(UC_PPC_REG_3)
            if address == 0x813B1564: ret = 15
            elif address == 0x8135E38C: ret = 0
            elif address == 0x8135E408: ret = 5
            elif address == 0x815C0DA4: ret = 0 if kind == 'missing' else 0x80300000
            elif address == 0x815D0A08: ret = 0 if kind == 'heap' else image
            elif address == 0x815C0E00:
                requested = uc.reg_read(UC_PPC_REG_4) * uc.reg_read(UC_PPC_REG_5)
                data = bytes(content[position:position+requested])
                if data: uc.mem_write(arg, data)
                position += len(data)
                ret = len(data)
            elif address == 0x815C0D4C: closed.append(arg); ret = 0
            elif address == 0x815D0B6C: freed.append(arg); ret = 0
            elif address == 0x8146CCCC: ret = 0
            elif address == 0x8146CD1C:
                data = bytes(uc.mem_read(uc.reg_read(UC_PPC_REG_4), uc.reg_read(UC_PPC_REG_5)))
                digest = hashlib.sha1(data).digest(); ret = 0
            elif address == 0x8146CDD0:
                uc.mem_write(uc.reg_read(UC_PPC_REG_4), digest); ret = 0
            elif address in (0x815066EC, 0x815067A4): ret = 0
            elif address == 0x813B8BB8: prepared.append(arg); ret = 0
            elif address == 0x813B8ED0: disabled.append(arg); ret = 0
            if ret is not None:
                uc.reg_write(UC_PPC_REG_3, ret)
                uc.reg_write(UC_PPC_REG_PC, uc.reg_read(UC_PPC_REG_LR))
        u.hook_add(UC_HOOK_CODE, mock)
        for function in ('kwce_native_bind_reset', 'kwce_reserve'):
            u.reg_write(UC_PPC_REG_1, 0x807ff000)
            u.reg_write(UC_PPC_REG_3, scene)
            u.reg_write(UC_PPC_REG_LR, 0x80001000)
            u.emu_start(self.symbols[function], 0x80001000, count=100000)
        self.assertEqual(len(closed), 0 if kind == 'missing' else 1)
        if kind == 'good':
            self.assertEqual(prepared, [scene]); self.assertEqual(disabled, [])
            self.assertEqual(freed, [])
            self.assertEqual(bytes(u.mem_read(image, 512)), self.player)
            self.assertEqual(int.from_bytes(u.mem_read(scene+0x58, 4), 'big'), 4)
        else:
            self.assertEqual(prepared, []); self.assertEqual(disabled, [scene])
            self.assertEqual(freed, [] if kind in ('missing', 'heap') else [image])
            self.assertEqual(int.from_bytes(u.mem_read(scene+0x58, 4), 'big'), 0)

    def test_valid_file_is_prepared(self): self.reserve('good')
    def test_invalid_files_do_not_leave_the_menu(self):
        for kind in ('missing', 'heap', 'short', 'extra', 'header', 'body'):
            with self.subTest(kind=kind): self.reserve(kind)

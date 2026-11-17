import struct
import unittest
import sys
from pathlib import Path
runtime = Path(__file__).resolve().parents[1] / 'workspace/private/unicorn-2.1.1'
if runtime.exists():
    sys.path.insert(0, str(runtime))
from kwce.dvd_native_relocate import compile_relocator, validate_payload


class RelocateTests(unittest.TestCase):
    def test_compiled_ppc_copies_and_zeros_using_only_reserved_memory(self):
        from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
        from unicorn.ppc_const import UC_PPC_REG_3, UC_PPC_REG_MSR
        code = compile_relocator()
        for trampoline in (0x92000000, 0x93000000):
            cpu = Uc(UC_ARCH_PPC, UC_MODE_32 | UC_MODE_BIG_ENDIAN)
            cpu.mem_map(0x80000000, 0x20000)
            cpu.mem_map(0x91000000, 0x10000)
            cpu.mem_map(trampoline, 0x10000)
            image = bytearray(0x180)
            # Unaligned data/cache line tails and nonzero BSS exercise boundaries.
            for i, address, offset, size in ((0, 0x80004000, 0x100, 32),
                                              (7, 0x80006003, 0x140, 45)):
                for field, value in ((0, offset), (0x48, address), (0x90, size)):
                    struct.pack_into('>I', image, field + i * 4, value)
                image[offset:offset+size] = bytes(range(size))
            struct.pack_into('>III', image, 0xd8, 0x80008005, 37, 0x80004000)
            validate_payload(image)
            cpu.mem_write(0x80008000, b'Z' * 0x80)
            cpu.mem_write(0x91000000, bytes(image))
            cpu.mem_write(trampoline, code)
            cpu.reg_write(UC_PPC_REG_MSR, 0x2000)
            cpu.reg_write(UC_PPC_REG_3, 0x91000000)
            reached = []
            def stop_at_entry(uc, address, size, _):
                if address == 0x80004000:
                    reached.append(address)
                    uc.emu_stop()
            cpu.hook_add(UC_HOOK_CODE, stop_at_entry)
            cpu.emu_start(trampoline, trampoline + len(code), count=10000)
            self.assertEqual(reached, [0x80004000])
            self.assertEqual(bytes(cpu.mem_read(0x80004000, 32)), bytes(range(32)))
            self.assertEqual(bytes(cpu.mem_read(0x80006003, 45)), bytes(range(45)))
            self.assertEqual(bytes(cpu.mem_read(0x80008000, 43)), b'Z'*5 + bytes(37) + b'Z')
            self.assertEqual(bytes(cpu.mem_read(0x91000000, len(image))), bytes(image))

    def test_mem2_target_is_rejected_before_destructive_copy(self):
        image = bytearray(0x120)
        for at, value in ((0, 0x100), (0x48, 0x91000000), (0x90, 32), (0xe0, 0x91000000)):
            struct.pack_into('>I', image, at, value)
        with self.assertRaises(ValueError):
            validate_payload(image)

    def test_resident_nintendo_ash_decoder_and_mem2_trampoline(self):
        from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
        from unicorn.ppc_const import UC_PPC_REG_1, UC_PPC_REG_3, UC_PPC_REG_MSR
        from kwce.formats import ash_compress
        from kwce.ppc_patch import to_file
        root=Path(__file__).resolve().parents[1]
        menu=(root/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
        image=bytearray(0x1120)
        for at,value in ((0,0x100),(0x48,0x80003f00),(0x90,0x1020),
                         (0xd8,0x80005000),(0xdc,128),(0xe0,0x80003f00)):
            struct.pack_into('>I',image,at,value)
        image[0x100:]=bytes(range(256))*16+bytes(32)
        validate_payload(image)
        packed=ash_compress(bytes(image))
        u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN)
        u.mem_map(0x80000000,0x1800000);u.mem_map(0x90000000,0x3400000)
        start=0x813317c0;length=0x4c4
        at=to_file(menu,start,length);u.mem_write(start,menu[at:at+length])
        code=compile_relocator(ash=True);u.mem_write(0x93000000,code)
        u.mem_write(0x91000000,packed);u.mem_write(0x80005000,b'X'*128)
        u.reg_write(UC_PPC_REG_1,0x93210000);u.reg_write(UC_PPC_REG_3,0x91000000)
        u.reg_write(UC_PPC_REG_MSR,0x2000)
        reached=[]
        def stop(uc,address,size,_):
            if address==0x80003f00:reached.append(address);uc.emu_stop()
        u.hook_add(UC_HOOK_CODE,stop)
        u.emu_start(0x93000000,0x93000000+len(code),count=1000000)
        self.assertEqual(reached,[0x80003f00])
        self.assertEqual(bytes(u.mem_read(0x80003e00,len(image))),bytes(image))
        self.assertEqual(bytes(u.mem_read(0x80005000,128)),bytes(128))

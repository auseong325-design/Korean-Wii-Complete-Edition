"""GC memory card menu: per-save comment decoder and ANSI format default.

The dispatcher is executed as PowerPC code with the 43K CARD control block
layout; the format patch is checked against every use of __CARDEncode.
Rendering of real comments was checked separately in the isolated emulator.
"""
import re
import struct
import unittest
from pathlib import Path

from kwce.gc_card import inspect_card
from kwce.gc_card_encoding import patch_card_encodings
from kwce.gc_card_format import patch_format_ansi, CALL as FORMAT_CALL
from kwce.gc_comment_region import (patch_comment_region, dispatcher, CAVE, CAVE_END,
                                    ADAPTER, ANSI, CALL, THUNK)
from kwce.gc_fixture import raw_card_saves
from kwce.gc_native import patch_gc_native, dol_offset
from kwce.ppc_patch import sections

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT/'workspace/console-baseline/menu-original-43K.dol'
CARD_BLOCK, STRIDE = 0x8112FFC8, 0x118


def base_menu():
    menu = ORIGINAL.read_bytes()
    return patch_card_encodings(patch_gc_native(menu, japanese_cards=True, japanese_comments=True)[0])[0]


class CommentDispatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = base_menu()
        cls.patched, cls.record = patch_comment_region(cls.base)

    def run_dispatch(self, chan=0, file_no=1, attached=1, region=b'P', empty=False, directory=True):
        from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
        from unicorn.ppc_const import UC_PPC_REG_23, UC_PPC_REG_28, UC_PPC_REG_3, UC_PPC_REG_4, UC_PPC_REG_5
        u = Uc(UC_ARCH_PPC, UC_MODE_32 | UC_MODE_BIG_ENDIAN)
        u.mem_map(0x80000000, 0x1800000)
        code = dispatcher(); u.mem_write(CAVE, code)
        block = CARD_BLOCK + chan*STRIDE if chan <= 1 else CARD_BLOCK
        u.mem_write(block, struct.pack('>I', attached))
        dir_addr = 0x80500000
        u.mem_write(block+0x84, struct.pack('>I', dir_addr if directory else 0))
        entry = (b'\xff'*64) if empty else (b'GKW' + region + b'01' + b'\xff'*58)
        u.mem_write(dir_addr + file_no*64 if file_no < 127 else dir_addr, entry)
        for reg, value in ((UC_PPC_REG_23, chan), (UC_PPC_REG_28, file_no*0x15c),
                           (UC_PPC_REG_3, 0x80600000), (UC_PPC_REG_4, 0x80601000), (UC_PPC_REG_5, 0x20)):
            u.reg_write(reg, value)
        landed = []
        def stop(uc, address, size, _):
            if address in (ANSI, ADAPTER): landed.append(address); uc.emu_stop()
        u.hook_add(UC_HOOK_CODE, stop)
        u.emu_start(CAVE, 0, count=200)
        self.assertEqual(u.reg_read(UC_PPC_REG_3), 0x80600000)   # arguments pass through
        self.assertEqual(u.reg_read(UC_PPC_REG_4), 0x80601000)
        self.assertEqual(u.reg_read(UC_PPC_REG_5), 0x20)
        return landed[0]

    def test_region_letter_selects_decoder(self):
        for region in b'EPDFSIXYU':
            self.assertEqual(self.run_dispatch(region=bytes([region])), ANSI)
        self.assertEqual(self.run_dispatch(region=b'J'), ADAPTER)
        for chan in (0, 1):
            for file_no in (0, 5, 126):
                self.assertEqual(self.run_dispatch(chan=chan, file_no=file_no, region=b'E'), ANSI)

    def test_every_uncertain_case_keeps_the_verified_cp932_path(self):
        self.assertEqual(self.run_dispatch(attached=0), ADAPTER)
        self.assertEqual(self.run_dispatch(directory=False), ADAPTER)
        self.assertEqual(self.run_dispatch(empty=True), ADAPTER)
        self.assertEqual(self.run_dispatch(chan=2), ADAPTER)
        self.assertEqual(self.run_dispatch(file_no=127), ADAPTER)

    def test_patch_scope(self):
        diff = [i for i, (a, b) in enumerate(zip(self.base, self.patched)) if a != b]
        call, cave = dol_offset(self.base, CALL), dol_offset(self.base, CAVE)
        self.assertTrue(all(call <= i < call+4 or cave <= i < cave+len(dispatcher()) for i in diff))
        self.assertLessEqual(CAVE + len(dispatcher()), CAVE_END)
        self.assertLessEqual(THUNK[1], CAVE)                          # encoding thunk untouched
        start, end = dol_offset(self.base, THUNK[0]), dol_offset(self.base, THUNK[1])
        self.assertEqual(self.patched[start:end], self.base[start:end])
        with self.assertRaises(ValueError): patch_comment_region(ORIGINAL.read_bytes())
        with self.assertRaises(ValueError): patch_comment_region(self.patched)

    def test_caller_registers_are_what_the_dispatcher_assumes(self):
        from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN
        menu = ORIGINAL.read_bytes(); start = 0x813cd4d0
        code = menu[dol_offset(menu, start):dol_offset(menu, start)+(CALL-start)+4]
        text = [(i.address, i.mnemonic, i.op_str) for i in
                Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN).disasm(code, start)]
        self.assertIn((0x813cd50c, 'mr', 'r23, r4'), text)              # u8 channel argument
        self.assertIn((0x813cd51c, 'mulli', 'r28, r25, 0x15c'), text)   # card file * 0x15c
        writes = [a for a, m, ops in text if a > 0x813cd51c and ops.split(',')[0] in ('r23', 'r28')
                  and m not in ('cmpwi', 'cmplwi', 'stw')]
        self.assertEqual(writes, [])                                     # unchanged until the call
        self.assertIn((0x813cd5bc, 'bl', '0x81542ebc'), text)            # SCGetLanguage branch
        # 43K CARD layout used by the dispatcher.
        directory = menu[dol_offset(menu, 0x81538F98):dol_offset(menu, 0x81538F98)+4]
        self.assertEqual(struct.unpack('>I', directory)[0], 0x80630084)  # lwz r3,0x84(r3)


class FormatDefaultTests(unittest.TestCase):
    def test_only_cardformat_consumes_the_changed_value(self):
        menu = ORIGINAL.read_bytes(); base = base_menu()
        patched, _ = patch_format_ansi(base)
        self.assertEqual(sum(a != b for a, b in zip(base, patched)), 1)
        self.assertEqual(struct.unpack_from('>I', patched, dol_offset(patched, FORMAT_CALL))[0], 0x38600000)
        with self.assertRaises(ValueError): patch_format_ansi(menu)
        with self.assertRaises(ValueError): patch_format_ansi(patched)
        syms = {}
        for line in (ROOT/'external/wii-ipl/config/43K/symbols.txt').read_text().splitlines():
            m = re.match(r'(\S+) = \.text:0x([0-9A-Fa-f]+);.*size:0x([0-9A-Fa-f]+)', line)
            if m: syms[m[1]] = (int(m[2], 16), int(m[3], 16))
        getter = syms['__CARDGetFontEncode'][0]
        def owner(a): return next(n for n, (s, z) in syms.items() if s <= a < s+z)
        readers, callers = [], []
        for _, off, addr, size in sections(menu)[:7]:
            for k in range(0, size, 4):
                w = struct.unpack_from('>I', menu, off+k)[0]
                if (w >> 16) & 31 == 13 and w & 0xffff == 0x10000-0x4b46 and w >> 26 in (40, 44):
                    readers.append(owner(addr+k))
                if w & 0xfc000003 == 0x48000001:
                    d = w & 0x3fffffc; d = d-(1 << 26) if d & (1 << 25) else d
                    if addr+k+d == getter: callers.append((owner(addr+k), addr+k))
        self.assertEqual(sorted(readers), ['CARDInit', '__CARDGetFontEncode'])
        self.assertEqual(sorted(n for n, _ in callers), ['CARDFormat', 'VerifyID'])
        verify_call = dict((n, a) for n, a in callers)['VerifyID']
        w = struct.unpack_from('>I', base, dol_offset(base, verify_call))[0]
        d = w & 0x3fffffc; d = d-(1 << 26) if d & (1 << 25) else d
        self.assertNotEqual(verify_call+d, getter)                       # mounting uses the per-card thunk


class FixtureTests(unittest.TestCase):
    def test_three_region_card_is_valid(self):
        line = lambda s, e: s.encode(e).ljust(32, b'\0')
        card = raw_card_saves([(b'GKWJ01', b'JP', line('テスト', 'cp932')*2),
                               (b'GKWP01', b'EU', line('Données', 'latin-1')*2),
                               (b'GKWE01', b'US', line('USA', 'ascii')*2)], encoding=0)
        info = inspect_card(card)
        self.assertEqual((info['encoding'], info['allocated_blocks'], info['free_blocks']), (0, 3, 56))
        self.assertTrue(info['checksums_valid'])


if __name__ == '__main__': unittest.main()

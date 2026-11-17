"""Exercise the real PPC tile hooks with synthetic channel manager responses."""
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
runtime = ROOT/'workspace/private/unicorn-2.1.1'
if runtime.exists(): sys.path.insert(0, str(runtime))
try:
    from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
    from unicorn.ppc_const import UC_PPC_REG_1, UC_PPC_REG_3, UC_PPC_REG_4, UC_PPC_REG_5, UC_PPC_REG_6, UC_PPC_REG_8, UC_PPC_REG_9, UC_PPC_REG_10, UC_PPC_REG_11, UC_PPC_REG_12, UC_PPC_REG_27, UC_PPC_REG_29, UC_PPC_REG_30, UC_PPC_REG_LR, UC_PPC_REG_PC
except ImportError:
    Uc = None
from kwce.dvd_hide_tile_v2 import CAVE, EVENT, SEARCH, SYMBOLS, compiled


@unittest.skipIf(Uc is None, 'Optional PPC emulator unavailable')
class HideTilePpcTest(unittest.TestCase):
    def execute(self, entry, title, valid=True):
        code, labels = compiled()
        uc = Uc(UC_ARCH_PPC, UC_MODE_32 | UC_MODE_BIG_ENDIAN)
        for address,size in [(0x80000000,0x400000),(0x81089000,0x1000),
                             (0x81337000,0x1000),(0x813AF000,0x1000),(0x813B0000,0x10000)]:
            uc.mem_map(address,size)
        uc.mem_write(CAVE,code)
        uc.mem_write(0x8108908c,struct.pack('>I',0x80200100))
        uc.mem_write(0x8020001c,struct.pack('>II',1,9))
        uc.reg_write(UC_PPC_REG_1,0x803ff000)
        uc.reg_write(UC_PPC_REG_3,0x80200000 if valid else 0)
        uc.reg_write(UC_PPC_REG_27,2)
        uc.reg_write(UC_PPC_REG_29,9)
        uc.reg_write(UC_PPC_REG_30,1)
        uc.reg_write(UC_PPC_REG_5,0x80200200)
        uc.reg_write(UC_PPC_REG_9,0x80200100)
        uc.reg_write(UC_PPC_REG_LR,0x80010000)
        seen=[]
        def hook(u, address, size, _):
            if address == SYMBOLS['getTitleID']:
                self.assertEqual((u.reg_read(UC_PPC_REG_4),u.reg_read(UC_PPC_REG_5)),(1,9))
                u.reg_write(UC_PPC_REG_3,title >> 32)
                u.reg_write(UC_PPC_REG_4,title & 0xffffffff)
                u.reg_write(UC_PPC_REG_PC,u.reg_read(UC_PPC_REG_LR))
            elif address in (SYMBOLS['thumbnail'], SYMBOLS['cursor'], SYMBOLS['balloon']):
                seen.append(address)
                u.reg_write(UC_PPC_REG_PC,u.reg_read(UC_PPC_REG_LR))
            elif address in (0x80010000,SYMBOLS['event_done'],EVENT+4,SYMBOLS['search_next'],SEARCH+4):
                seen.append(address)
                if address in (SYMBOLS['search_next'], SEARCH+4):
                    self.assertEqual(u.reg_read(UC_PPC_REG_5),0x80200200)
                    if address == SEARCH+4:
                        self.assertEqual(bytes(u.mem_read(0x80200200,4)),struct.pack('>I',1))
                u.emu_stop()
        uc.hook_add(UC_HOOK_CODE,hook)
        uc.emu_start(labels[entry],0xffffffff,count=1000)
        return seen

    def test_dvd_draws_are_hidden_other_channels_are_preserved(self):
        for name, target in [('hide_thumbnail','thumbnail'),('hide_cursor','cursor'),('hide_balloon','balloon')]:
            with self.subTest(name=name):
                self.assertEqual(self.execute(name,0x000100014b445644),[0x80010000])
                self.assertEqual(self.execute(name,0x0001000148414445),[SYMBOLS[target],0x80010000])

    def test_dvd_events_are_ignored_other_events_resume(self):
        self.assertEqual(self.execute('hide_event',0x000100014b445644),[SYMBOLS['event_done']])
        self.assertEqual(self.execute('hide_event',0x0001000148414445),[EVENT+4])

    def test_channel_preview_arrows_skip_only_dvd(self):
        self.assertEqual(self.execute('hide_search',0x000100014b445644),[SYMBOLS['search_next']])
        self.assertEqual(self.execute('hide_search',0x0001000148414445),[SEARCH+4])


if __name__ == '__main__': unittest.main()

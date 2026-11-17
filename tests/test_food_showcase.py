"""Food hardware-v17 showcase: order_done/inquiry_done complete on the console (Unicorn, channel code)."""
import datetime
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V16 = ROOT / 'workspace/channels/food/hardware-v16'
V17 = ROOT / 'workspace/channels/food/hardware-v17'


def exe(folder):
    from kwce.channels import load_library
    from kwce.wiiroom_formats import decompress_lz11
    t = load_library().title.Title(); t.load_wad(next(folder.glob('*.wad')).read_bytes())
    return decompress_lz11(t.get_content_by_index(1))


def post(dol, action):
    from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
    from unicorn import ppc_const as p
    u = Uc(UC_ARCH_PPC, UC_MODE_32 | UC_MODE_BIG_ENDIAN); u.mem_map(0x80000000, 0x01800000)
    for i in range(18):
        off, addr, size = (struct.unpack_from('>I', dol, b + 4 * i)[0] for b in (0, 0x48, 0x90))
        if size: u.mem_write(addr, dol[off:off + size])
    bus = 243000000; u.mem_write(0x800000f8, struct.pack('>I', bus))
    u.reg_write(p.UC_PPC_REG_1, 0x817f0000); u.reg_write(p.UC_PPC_REG_2, 0x8047a440); u.reg_write(p.UC_PPC_REG_13, 0x80478660)
    this, heap, stop = 0x81700000, 0x81710000, 0x817ffff0
    ticks = int((datetime.datetime(2026, 11, 16, 11, 47, 5) - datetime.datetime(2000, 1, 1)).total_seconds()) * (bus // 4)
    seen = []
    def hook(uc, a, s, _):
        lr = uc.reg_read(p.UC_PPC_REG_LR)
        if a == 0x800229c0: uc.reg_write(p.UC_PPC_REG_3, heap)
        elif a == 0x800229d4: pass
        elif a == 0x801a3f70: uc.reg_write(p.UC_PPC_REG_3, ticks >> 32); uc.reg_write(p.UC_PPC_REG_4, ticks & 0xffffffff)
        elif a == 0x8002c6ac: seen.append('network'); uc.emu_stop(); return
        else: return
        uc.reg_write(p.UC_PPC_REG_PC, lr)
    u.hook_add(UC_HOOK_CODE, hook, begin=0x80000000, end=0x81800000)
    u.reg_write(p.UC_PPC_REG_3, this); u.reg_write(p.UC_PPC_REG_4, action); u.reg_write(p.UC_PPC_REG_LR, stop)
    u.emu_start(0x8002c6a8, stop, count=2000000)
    fields = struct.unpack('>7I', bytes(u.mem_read(this + 0x14, 28)))
    return seen, fields, bytes(u.mem_read(heap, 0x400)).split(b'\0')[0]


@unittest.skipUnless(V16.is_dir() and V17.is_dir(), 'food hardware-v16/v17 not present')
class FoodShowcaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.new = exe(V17)

    def test_order_done_stays_local(self):
        seen, f, body = post(self.new, 0x18)
        self.assertEqual(seen, [])
        self.assertEqual((f[0], f[1], f[2], f[3], f[4]), (0, 200, 0, 0, 1))   # state, http, err, ssl, done
        self.assertIn(b'<orderDay><![CDATA[202611161147]]></orderDay>', body)
        self.assertIn(b'<code><![CDATA[0]]></code>', body)

    def test_inquiry_stays_local_and_others_use_network(self):
        self.assertEqual(post(self.new, 0x16)[0], [])
        for action in (0x0d, 0x0e):
            self.assertEqual(post(self.new, action)[0], ['network'])

    def test_executable_change_is_bounded(self):
        old = exe(V16)
        self.assertEqual(len(old), len(self.new))
        diff = [i for i in range(len(old)) if old[i] != self.new[i]]
        from kwce.ppc_patch import to_file
        spans = [(to_file(old, 0x8002c6a8), 4), (to_file(old, 0x8010b308), 0x8010b9bc - 0x8010b308),
                 (to_file(old, 0x802d710c), 37), (to_file(old, 0x802d71b3), 142)]
        self.assertTrue(all(any(a <= i < a + n for a, n in spans) for i in diff))


if __name__ == '__main__':
    unittest.main()

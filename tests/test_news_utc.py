"""News v27: the no-universal-time fallback yields UTC on a Korean (UTC+9) console clock.

The channel's own fallback code and OSTicksToCalendarTime run under Unicorn; only OSGetTime
is stubbed with a chosen console time. No network, console data or article text is used.
"""
import datetime
import json
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WADS = {n: ROOT / f'workspace/channels/news/build-v{n}/news-ko-personal.wad' for n in (25, 27)}
BUS_CLOCK = 243000000
FALLBACK, AFTER, OS_GET_TIME = 0x800761f8, 0x80076204, 0x80106e84


def executable(revision):
    from kwce.channels import load_library
    title = load_library().title.Title(); title.load_wad(WADS[revision].read_bytes())
    return title.get_content_by_index(1)


def calendar(dol, local):
    """Run the fallback with the console clock at `local`; return (year, mon, mday, hour, min)."""
    from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
    from unicorn import ppc_const as p
    u = Uc(UC_ARCH_PPC, UC_MODE_32 | UC_MODE_BIG_ENDIAN)
    u.mem_map(0x80000000, 0x01800000)
    for i in range(18):
        off, addr, size = (struct.unpack_from('>I', dol, base + 4 * i)[0] for base in (0, 0x48, 0x90))
        if size: u.mem_write(addr, dol[off:off + size])
    u.mem_write(0x800000f8, struct.pack('>I', BUS_CLOCK))
    seconds = int((local - datetime.datetime(2000, 1, 1)).total_seconds())
    ticks = seconds * (BUS_CLOCK // 4)
    out, stack = 0x81700000, 0x817f0000
    u.reg_write(p.UC_PPC_REG_1, stack); u.reg_write(p.UC_PPC_REG_31, out)

    def hook(uc, address, size, _):
        if address == OS_GET_TIME:
            uc.reg_write(p.UC_PPC_REG_3, ticks >> 32); uc.reg_write(p.UC_PPC_REG_4, ticks & 0xffffffff)
            uc.reg_write(p.UC_PPC_REG_PC, uc.reg_read(p.UC_PPC_REG_LR))
    u.hook_add(UC_HOOK_CODE, hook, begin=OS_GET_TIME, end=OS_GET_TIME)
    u.emu_start(FALLBACK, AFTER, count=20000)
    sec, minute, hour, mday, mon, year = struct.unpack('>6i', bytes(u.mem_read(out, 24)))
    return year, mon + 1, mday, hour, minute


@unittest.skipUnless(all(p.is_file() for p in WADS.values()), 'News v25/v27 builds not present')
class NewsUtcFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old, cls.new = executable(25), executable(27)

    def test_only_the_fallback_call_and_slot_change(self):
        diff = [i for i in range(len(self.old)) if self.old[i] != self.new[i]]
        self.assertEqual(len(self.old), len(self.new))
        from kwce.ppc_patch import to_file
        site, cave = to_file(self.old, FALLBACK), to_file(self.old, 0x801e0580)
        self.assertTrue(all(site <= i < site + 4 or cave <= i < cave + 64 for i in diff))
        record = json.loads((WADS[27].parent / 'build-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(record['utc_fallback']['offset_seconds'], -32400)
        self.assertEqual(record['changed_from_parent'], [1])

    def test_korean_clock_becomes_utc(self):
        for local in (datetime.datetime(2026, 11, 16, 0, 43), datetime.datetime(2026, 11, 16, 9, 0),
                      datetime.datetime(2027, 1, 1, 8, 59), datetime.datetime(2028, 3, 1, 3, 30)):
            utc = local - datetime.timedelta(hours=9)
            self.assertEqual(calendar(self.old, local), (local.year, local.month, local.day, local.hour, local.minute))
            self.assertEqual(calendar(self.new, local), (utc.year, utc.month, utc.day, utc.hour, utc.minute))


if __name__ == '__main__':
    unittest.main()


# --- v29: the path the console actually takes (KD time difference query succeeds) ---------
WAD28 = ROOT / 'workspace/channels/news/build-v29/news-ko-personal.wad'   # v28 had the wrong epoch (unused)
PRIMARY, HELPER_END = 0x800761b4, 0x80076208
TIME_DIFF, RTC_READY, COUNTER_BIAS = 0x8007bd98, 0x8012e528, 0x80130210


def helper(dol, local, bias_seconds, stored_difference=946684800):
    """Run the calendar helper from its universal-time call; KD answers the difference query.

    Returns (used universal time, (year, mon, mday, hour, min))."""
    from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
    from unicorn import ppc_const as p
    u = Uc(UC_ARCH_PPC, UC_MODE_32 | UC_MODE_BIG_ENDIAN)
    u.mem_map(0x80000000, 0x01800000)
    for i in range(18):
        off, addr, size = (struct.unpack_from('>I', dol, base + 4 * i)[0] for base in (0, 0x48, 0x90))
        if size: u.mem_write(addr, dol[off:off + size])
    u.mem_write(0x800000f8, struct.pack('>I', BUS_CLOCK))
    seconds = int((local - datetime.datetime(2000, 1, 1)).total_seconds()); ticks = seconds * (BUS_CLOCK // 4)
    out, stack, sda = 0x81700000, 0x817f0000, 0x81600000
    u.reg_write(p.UC_PPC_REG_1, stack); u.reg_write(p.UC_PPC_REG_31, out); u.reg_write(p.UC_PPC_REG_13, sda)

    def ret(uc): uc.reg_write(p.UC_PPC_REG_PC, uc.reg_read(p.UC_PPC_REG_LR))

    def hook(uc, address, size, _):
        if address == OS_GET_TIME:
            uc.reg_write(p.UC_PPC_REG_3, ticks >> 32); uc.reg_write(p.UC_PPC_REG_4, ticks & 0xffffffff); ret(uc)
        elif address == TIME_DIFF:            # KD ioctl 0x18: success, stored difference
            uc.mem_write(uc.reg_read(p.UC_PPC_REG_3), struct.pack('>q', stored_difference))
            uc.reg_write(p.UC_PPC_REG_3, 0); ret(uc)
        elif address == RTC_READY:
            uc.reg_write(p.UC_PPC_REG_3, 0); ret(uc)
        elif address == COUNTER_BIAS:
            uc.reg_write(p.UC_PPC_REG_3, bias_seconds); ret(uc)
    u.hook_add(UC_HOOK_CODE, hook)
    u.emu_start(PRIMARY, HELPER_END, count=200000)
    sec, minute, hour, mday, mon, year = struct.unpack('>6i', bytes(u.mem_read(out, 24)))
    return u.reg_read(p.UC_PPC_REG_3), (year, mon + 1, mday, hour, minute)


@unittest.skipUnless(WAD28.is_file() and WADS[27].is_file(), 'News v27/v29 builds not present')
class NewsUniversalTimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kwce.channels import load_library
        def exe(path):
            t = load_library().title.Title(); t.load_wad(path.read_bytes()); return t.get_content_by_index(1)
        cls.v27, cls.v28 = exe(WADS[27]), exe(WAD28)

    def test_v27_follows_the_stored_kd_difference_not_the_clock(self):
        # The console's case: the difference query succeeds, so the v27 fallback is never used and
        # the result depends on KD's stored value and the RTC counter bias, not on the clock setting.
        local = datetime.datetime(2026, 11, 17, 21, 0)
        used, shown = helper(self.v27, local, bias_seconds=5 * 86400)
        self.assertEqual(used, 1)
        self.assertEqual(shown, (2026, 11, 12, 21, 0))        # five days off although the clock is right

    def test_v29_uses_the_console_clock_minus_nine_hours(self):
        for local in (datetime.datetime(2026, 11, 17, 21, 0), datetime.datetime(2026, 11, 17, 3, 30), datetime.datetime(2027, 1, 1, 8, 59)):
            utc = local - datetime.timedelta(hours=9)
            for bias, stored in ((5 * 86400, 0), (0, 123456789), (-400, -32400)):
                used, shown = helper(self.v28, local, bias, stored)
                self.assertEqual(used, 1)
                self.assertEqual(shown, (utc.year, utc.month, utc.day, utc.hour, utc.minute))

    def test_v29_changes_only_the_library_function(self):
        from kwce.ppc_patch import to_file
        at = to_file(self.v27, 0x8007bc58)
        diff = [i for i in range(len(self.v27)) if self.v27[i] != self.v28[i]]
        self.assertTrue(diff and all(at <= i < at + 0x140 for i in diff))

"""Forecast banner date line (build-v107): executed as PowerPC with every area/language."""
import struct
import unittest
from pathlib import Path

from kwce import forecast_banner_date as fbd
from kwce.channels import ChannelArchive, load_library
from kwce.forecast_banner_language import BANNER_MEMBER, _lz

ROOT = Path(__file__).resolve().parents[1]
V106 = ROOT / 'workspace/channels/forecast/build-v106/forecast-ko-personal-test.wad'
V107 = ROOT / 'workspace/channels/forecast/build-v107/forecast-ko-personal-test.wad'
TAIL_CALLS = (0x1da4, 0x1de0, 0x1e1c)      # b swprintf (US, French, Japanese)


def _rso(path):
    title = load_library().title.Title()
    title.load_wad(path.read_bytes())
    return _lz(ChannelArchive(title.get_content_by_index(5)).get(BANNER_MEMBER))


def _string(rso, offset):
    at = fbd.SECTION5 + offset
    end = at
    while rso[end:end + 2] != b'\0\0':
        end += 2
    return rso[at:end].decode('utf-16-be')


def _format(rso, area, language, hour=16, mday=24):
    """Run the date function; return (format offset in section 5, r6, r7) at its swprintf."""
    from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
    from unicorn import ppc_const as p
    u = Uc(UC_ARCH_PPC, UC_MODE_32 | UC_MODE_BIG_ENDIAN)
    u.mem_map(0, 0x100000)
    u.mem_write(0, rso[:0x4840])
    cal = 0x80000
    u.mem_write(cal, struct.pack('>6I', 0, 0, hour, mday, 9, 2026))
    for reg, value in ((p.UC_PPC_REG_3, 0x90000), (p.UC_PPC_REG_4, 0x40), (p.UC_PPC_REG_6, cal),
                       (p.UC_PPC_REG_7, area), (p.UC_PPC_REG_8, language)):
        u.reg_write(reg, value)
    seen = []

    def hook(uc, address, size, _):
        if address in TAIL_CALLS:
            seen.append((uc.reg_read(p.UC_PPC_REG_5), uc.reg_read(p.UC_PPC_REG_6), uc.reg_read(p.UC_PPC_REG_7)))
            uc.emu_stop()
    u.hook_add(UC_HOOK_CODE, hook)
    # Unrelocated lis/addi leave the section base (r10) at 0, so r5 is the section offset.
    u.emu_start(0x1d34, 0, count=200)
    return seen[0] if seen else None


class BannerDateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v106 = _rso(V106)
        cls.patched, cls.record = fbd.patch_banner_date(cls.v106)

    def test_v106_korean_console_path_was_english(self):
        fmt, hour12, minute = _format(self.v106, 1, 1)
        self.assertEqual(_string(self.v106, fmt), fbd.ENGLISH_TEXT)
        self.assertEqual((hour12, minute), (4, 0))

    def test_every_area_and_language_formats_korean_day_hour(self):
        for area in (0, 1, 2):
            for language in range(0, 10):
                fmt, day, hour = _format(self.patched, area, language)
                self.assertEqual(_string(self.patched, fmt), fbd.KOREAN_TEXT)
                self.assertEqual((day, hour), (24, 16))
        self.assertEqual(fbd.KOREAN_TEXT.replace('%d', '{}').format(24, 16), '24일 16시 발표')

    def test_edit_scope(self):
        diff = [i for i, (a, b) in enumerate(zip(self.v106, self.patched)) if a != b]
        slot = fbd.SECTION5 + fbd.ENGLISH
        allowed = lambda i: (fbd.BRANCH <= i < fbd.BRANCH + 4 or fbd.FORMAT_ADDI <= i < fbd.FORMAT_ADDI + 4
                             or slot <= i < slot + 60)
        self.assertEqual(len(self.patched), len(self.v106))
        self.assertTrue(diff and all(allowed(i) for i in diff))
        self.assertEqual(_string(self.patched, fbd.JAPANESE), _string(self.v106, fbd.JAPANESE))
        self.assertEqual(fbd._relocated(self.patched), fbd._relocated(self.v106))
        with self.assertRaises(ValueError):
            fbd.patch_banner_date(self.patched)

    @unittest.skipUnless(V107.exists(), 'build-v107 not built')
    def test_build_v107_contains_exactly_this_module(self):
        self.assertEqual(_rso(V107), self.patched)


if __name__ == '__main__':
    unittest.main()

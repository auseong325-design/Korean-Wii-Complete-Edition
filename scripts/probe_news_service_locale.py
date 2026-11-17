"""Exercise the News v25 service locale selection on synthetic inputs.

The original PPC instructions are run with a stubbed system-language getter.
No Wii settings, console data, network requests or executable bytes are output.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'workspace/private/unicorn-2.1.1'))
sys.path.insert(0, str(ROOT / 'workspace/channels/nintendo/rc3'))
sys.path.insert(0, str(ROOT))
from dol import Dol
from kwce.channels import load_library
from unicorn import Uc, UC_ARCH_PPC, UC_MODE_PPC32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
from unicorn.ppc_const import (UC_PPC_REG_1, UC_PPC_REG_3, UC_PPC_REG_4,
                               UC_PPC_REG_29, UC_PPC_REG_LR, UC_PPC_REG_PC)

STOP = 0x81000000


def machine(dol):
    emulator = Uc(UC_ARCH_PPC, UC_MODE_PPC32 | UC_MODE_BIG_ENDIAN)
    emulator.mem_map(0x80000000, 0x00c00000)
    emulator.mem_map(0x81000000, 0x00200000)
    for _, offset, address, size in dol.sections:
        emulator.mem_write(address, dol.data[offset:offset + size])
    emulator.reg_write(UC_PPC_REG_1, 0x81100000)
    emulator.reg_write(UC_PPC_REG_LR, STOP)
    return emulator


def language(dol, system_language):
    emulator = machine(dol)
    def getter(uc, address, _size, _user):
        if address == 0x80130084:
            uc.reg_write(UC_PPC_REG_3, system_language)
            uc.reg_write(UC_PPC_REG_PC, uc.reg_read(UC_PPC_REG_LR))
    emulator.hook_add(UC_HOOK_CODE, getter, begin=0x80130084, end=0x80130084)
    emulator.emu_start(0x8003a10c, STOP, count=200)
    return emulator.reg_read(UC_PPC_REG_3)


def country(dol, requested_country):
    emulator = machine(dol)
    emulator.reg_write(UC_PPC_REG_4, requested_country)
    emulator.emu_start(0x800081f8, 0x800081fc, count=100)
    return emulator.reg_read(UC_PPC_REG_29)


def main():
    title = load_library().title.Title()
    title.load_wad((ROOT / 'workspace/channels/news/build-v25/news-ko-personal.wad').read_bytes())
    dol = Dol(title.get_content_by_index(1))
    for value in range(10):
        if language(dol, value) != (value if value <= 6 else 1):
            raise ValueError('Service-language control failed')
    for source, expected in ((136, 49), (49, 49), (1, 1)):
        if country(dol, source) != expected:
            raise ValueError('News-only country control failed')
    print('PASS: v25 PPC, Korean service language 9 -> English 1, News country 136 -> 49; controls passed')


if __name__ == '__main__':
    main()

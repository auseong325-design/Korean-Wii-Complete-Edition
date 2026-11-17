"""Exercise the v18 HTTP error mapper with synthetic status values only.

This bounded PPC experiment executes the channel's original status handler,
stubbing its external routines. It makes no network calls and models no data
submission. No binary bytes or console data are printed or written.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'workspace/private/unicorn-2.1.1'))
sys.path.insert(0, str(ROOT / 'workspace/channels/nintendo/rc3'))
from dol import Dol, load_dol
from unicorn import Uc, UC_ARCH_PPC, UC_MODE_PPC32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
from unicorn.ppc_const import (UC_PPC_REG_1, UC_PPC_REG_2, UC_PPC_REG_3,
                               UC_PPC_REG_4, UC_PPC_REG_13, UC_PPC_REG_LR,
                               UC_PPC_REG_PC)

HANDLER, END, STOP = 0x80044b20, 0x80044cc0, 0x81000000
MAPPER, SET_ERROR, GET_STATUS = 0x8002ef90, 0x800456a0, 0x80285ea0


def probe(dol, synthetic_status):
    machine = Uc(UC_ARCH_PPC, UC_MODE_PPC32 | UC_MODE_BIG_ENDIAN)
    machine.mem_map(0x80000000, 0x00c00000)
    machine.mem_map(0x81000000, 0x00200000)
    for _, offset, address, size in dol.sections:
        machine.mem_write(address, dol.data[offset:offset + size])
    for register, value in ((UC_PPC_REG_1, 0x81100000), (UC_PPC_REG_2, 0x807c6b60),
                            (UC_PPC_REG_13, 0x807c2820), (UC_PPC_REG_3, 0x81010000),
                            (UC_PPC_REG_4, 0x81011000), (UC_PPC_REG_LR, STOP)):
        machine.reg_write(register, value)
    observed = []
    reached_status = []

    def hook(uc, address, _size, _user):
        if address == SET_ERROR:
            observed.append(uc.reg_read(UC_PPC_REG_4))
        if MAPPER <= address <= MAPPER + 8 or HANDLER <= address < END:
            return
        if address == GET_STATUS:
            reached_status.append(True)
        result = synthetic_status if address == GET_STATUS else 4 if address == 0x80285750 else 0
        uc.reg_write(UC_PPC_REG_3, result)
        uc.reg_write(UC_PPC_REG_PC, uc.reg_read(UC_PPC_REG_LR))

    machine.hook_add(UC_HOOK_CODE, hook)
    machine.emu_start(HANDLER, STOP, count=3000)
    if not reached_status:
        raise ValueError('Synthetic response did not reach status path')
    return observed


def main():
    dol = Dol(load_dol(ROOT / 'workspace/channels/nintendo/build-v18/nintendo-ko-ui-test.wad'))
    for status in (200, 204):
        if probe(dol, status):
            raise ValueError('Synthetic successful HTTP status was reported as an error')
    print('synthetic HTTP statuses 200 and 204 -> no HTTP error')
    expected = {404: 268404, 500: 268500, 503: 268503}
    for status, code in expected.items():
        result = probe(dol, status)
        if code not in result:
            raise ValueError('Synthetic status mapping control failed')
        print(f'synthetic HTTP status {status} -> channel error {code}')
    print('PASS: synthetic HTTP error mapping; real Wii request is not identified')


if __name__ == '__main__':
    main()

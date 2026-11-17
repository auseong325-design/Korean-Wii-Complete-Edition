"""Run the channel's DS data checksum predicate on local synthetic/public data.

No console credentials, payload bytes, URLs, or executable bytes are printed or
written. Public responses stay in memory. The PPC emulator is installed only in
workspace/private/unicorn-2.1.1; this is an optional local investigation tool.
"""
import http.client
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'workspace/private/unicorn-2.1.1'))
sys.path.insert(0, str(ROOT / 'workspace/channels/nintendo/rc3'))
sys.path.insert(0, str(ROOT / 'scripts'))

import audit_nintendo_demo_responses as public
from dol import Dol, load_dol
from unicorn import Uc, UC_ARCH_PPC, UC_MODE_PPC32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
from unicorn.ppc_const import (UC_PPC_REG_1, UC_PPC_REG_2, UC_PPC_REG_3,
                               UC_PPC_REG_13, UC_PPC_REG_31, UC_PPC_REG_LR)

PREDICATE = 0x80034990
STOP = 0x81000000
DATA = 0x81010000


def predicate(executable, data, route=False):
    if len(data) < 332 or len(data) > public.LIMIT:
        raise ValueError('Unexpected input size')
    # The predicate uses the header-declared length; only run it on a bounded
    # buffer whose declared bytes are present, to prevent artificial overreads.
    declared = struct.unpack_from('>I', data, 4)[0]
    if declared < 332 or declared > len(data):
        raise ValueError('Declared checksum span exceeds the supplied buffer')
    machine = Uc(UC_ARCH_PPC, UC_MODE_PPC32 | UC_MODE_BIG_ENDIAN)
    machine.mem_map(0x80000000, 0x00c00000)
    machine.mem_map(0x81000000, 0x01000000)
    for _, offset, address, size in executable.sections:
        machine.mem_write(address, executable.data[offset:offset + size])
    machine.mem_write(DATA, bytes(data))
    for reg, value in ((UC_PPC_REG_1, 0x81f00000), (UC_PPC_REG_2, 0x807c6b60),
                       (UC_PPC_REG_13, 0x807c2820), (UC_PPC_REG_3, DATA),
                       (UC_PPC_REG_31, 0x81e00000),
                       (UC_PPC_REG_LR, STOP)):
        machine.reg_write(reg, value)
    if route:
        reached = []
        def on_instruction(uc, address, _size, _user):
            if address in (0x8003dd54, 0x8003dd58):
                reached.append(address)
                uc.emu_stop()
        machine.hook_add(UC_HOOK_CODE, on_instruction, begin=0x8003dd54, end=0x8003dd58)
        machine.emu_start(0x8003dd2c, STOP, count=40_000_000)
        if len(reached) != 1:
            raise ValueError('Bounded DS validation branch did not complete')
        code = struct.unpack('>I', machine.mem_read(0x81e0032c, 4))[0]
        return {'branch': 'checksum_error' if reached[0] == 0x8003dd54 else 'checksum_ok',
                'stored_error_code': code}
    machine.emu_start(PREDICATE, STOP, count=40_000_000)
    return machine.reg_read(UC_PPC_REG_3)


def read_public(ip, token, demo_id):
    path = f'/f/248/49125/1h/entus.wapp.wii.com/6/{token}/dstrial/KR/en/{demo_id}.bin'
    connection = http.client.HTTPConnection(ip, 80, timeout=30)
    try:
        connection.request('GET', path, headers={'Host': public.HOST,
                                                'User-Agent': 'KWCE-compatibility-check'})
        response = connection.getresponse()
        expected = int(response.getheader('Content-Length', '-1'))
        if response.status != 200 or not 0 <= expected <= public.LIMIT:
            raise ValueError('Unexpected public response')
        data = response.read(public.LIMIT + 1)
        if len(data) != expected:
            raise ValueError('Incomplete response')
        return data
    finally:
        connection.close()


def main():
    dol = Dol(load_dol(ROOT / 'workspace/channels/nintendo/build-v18/nintendo-ko-ui-test.wad'))
    synthetic = bytearray(512)
    synthetic[2] = 6
    struct.pack_into('>I', synthetic, 4, len(synthetic))
    struct.pack_into('>II', synthetic, 20, 332, 180)
    struct.pack_into('>I', synthetic, 8, zlib.crc32(synthetic) & 0xffffffff)
    corrupt = bytearray(synthetic)
    corrupt[-1] ^= 1
    if predicate(dol, synthetic) != 0 or predicate(dol, corrupt) != 1:
        raise ValueError('Synthetic predicate controls failed')
    if (predicate(dol, synthetic, route=True)['branch'] != 'checksum_ok' or
            predicate(dol, corrupt, route=True) != {'branch': 'checksum_error', 'stored_error_code': 262302}):
        raise ValueError('Synthetic branch controls failed')
    print('PASS: original channel predicate accepts synthetic valid data and rejects CRC corruption', flush=True)
    ids, token = public.inputs()
    ip = public.public_dns_ipv4()
    for name, demo_id in zip(('first_demo', 'burnout', 'tetris'), ids):
        data = read_public(ip, token, demo_id)
        result = predicate(dol, data, route=True)
        print(f'{name}: channel DS validation branch={result}', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, IndexError, struct.error, http.client.HTTPException) as error:
        raise SystemExit(f'Probe could not complete ({type(error).__name__}); content was not printed.') from None

"""Exercise v25/v26 error dispatch on synthetic return codes."""
import struct
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from probe_news_service_locale import Dol, load_library, machine
from unicorn.ppc_const import UC_PPC_REG_0, UC_PPC_REG_28, UC_PPC_REG_29, UC_PPC_REG_31, UC_PPC_REG_PC


def execute(dol, value):
    u = machine(dol); obj = 0x81010000
    u.reg_write(UC_PPC_REG_31, obj);u.mem_write(obj + 0x1bc, struct.pack('>i', value))
    u.emu_start(0x800095b0, 0x80009608, count=10)
    if u.reg_read(UC_PPC_REG_PC) != 0x80009608: raise ValueError('Unexpected dispatch control flow')
    return u.reg_read(UC_PPC_REG_29)


def load(rev):
    title = load_library().title.Title()
    title.load_wad((ROOT / f'workspace/channels/news/build-v{rev}/news-ko-personal.wad').read_bytes())
    return Dol(title.get_content_by_index(1))



def display_condition(dol, expected_language, file_language, first_language):
    u = machine(dol);obj, data = 0x81010000, 0x81012000
    def put(offset, value): u.mem_write(obj + offset, struct.pack('>I', value))
    put(0x8c, 5);put(0x3c8, 0);put(0x18, data);put(0x90, 512);put(0x1c4, expected_language)
    u.mem_write(data + 0x2c, bytes([file_language]));u.mem_write(data + 0x1c, bytes([first_language]))
    u.reg_write(UC_PPC_REG_28, obj);u.reg_write(UC_PPC_REG_0, 5)
    u.emu_start(0x8000872c, 0x800087f4, count=100)
    if u.reg_read(UC_PPC_REG_PC) != 0x800087f4: raise ValueError('Display branch instruction limit')
    return struct.unpack('>I', u.mem_read(obj + 0x8c, 4))[0]

def main():
    parent, diag = load(25), load(26)
    for val, expected in ((0, 10), (-1, 9), (-2, 8)):
        if execute(parent, val) != 6 or execute(diag, val) != expected:
            raise ValueError('Dispatch diagnostic failed')
    for expected, actual, first, result in ((1, 1, 1, 5), (9, 1, 1, 6), (1, 1, 255, 6)):
        if display_condition(parent, expected, actual, first) != result:
            raise ValueError('Runtime language display branch differs')
    print('PASS: real PPC error dispatch and display language / empty-list branches')

if __name__ == '__main__': main()

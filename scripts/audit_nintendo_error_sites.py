"""Verify known 262000 code sites without printing binary or console data.

These sites are static candidates, not a trace of the user's actual Wii.
"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN

SITES = (0x8002ccdc, 0x80041890, 0x800535ac, 0x80089b20)


def validate(executable):
    engine = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    verified = []
    for address in SITES:
        instructions = None
        for index in range(7):
            offset, start, length = (struct.unpack_from('>I', executable, base + 4*index)[0]
                                     for base in (0, 0x48, 0x90))
            if start <= address-24 and address+8 <= start+length:
                cursor = offset + address - start
                instructions = list(engine.disasm(executable[cursor-24:cursor+8], address-24))
                break
        if instructions is None:
            raise ValueError('Candidate outside executable sections')
        site = next((i for i in instructions if i.address == address), None)
        if site is None or site.mnemonic != 'addi':
            raise ValueError('Unexpected code-site instruction')
        operands = [x.strip() for x in site.op_str.split(',')]
        if len(operands) != 3 or int(operands[2], 0) != -144:
            raise ValueError('Expected 262000 constant not present')
        if not any(i.mnemonic == 'lis' and i.op_str in
                   (operands[1] + ', 4', operands[1] + ', 0x4')
                   for i in instructions if i.address < address):
            raise ValueError('Expected constant high half not found')
        verified.append(hex(address))
    return {'error_code': 262000, 'static_site_count': len(verified),
            'static_sites': verified, 'real_console_site_identified': False}


def main():
    lib = load_library()
    title = lib.title.Title()
    title.load_wad((ROOT / 'workspace/channels/nintendo/access-build-v6/nintendo-local-test.wad').read_bytes())
    print(json.dumps(validate(title.get_content_by_index(1)), sort_keys=True))


if __name__ == '__main__':
    main()

"""Experimental 43K per-card encoding selection after VerifyID's integrity checks.

The original size/checksum/flash checks and the final error calculation remain.
For an already-validated header, return its encoding iff ANSI(0) or SJIS(1).
Other values still differ from the returned SJIS value and produce -13.
No card bytes, CARDInit format default, global locale or string decoder change.
This is a separate, opt-in local candidate; existing patches remain reproducible.
"""
import hashlib
import json
from pathlib import Path
import struct

from .gc_native import dol_offset
from .ppc_patch import assemble

ROOT = Path(__file__).resolve().parents[1]


def encoding_stub():
    # At this exact call, r29 is the checked CARDID pointer. r29 is nonvolatile;
    # r3 and CR0 are caller-saved. The original caller reloads encode afterwards.
    return assemble('lhz 3,0x24(29)\ncmplwi 3,1\nblelr\nli 3,1\nblr',
                    0x81545a00, {})


def patch_card_encodings(data):
    pin = json.loads((ROOT / 'configs/gc-card-encoding-v1.lock.json').read_text())
    begin = dol_offset(data, pin['verify_id_address'])
    if hashlib.sha256(data[begin:begin+pin['verify_id_size']]).hexdigest() != pin['verify_id_sha256']:
        raise ValueError('Only the guarded original 43K VerifyID is supported')
    cave = dol_offset(data, pin['cave_address'])
    if hashlib.sha256(data[cave:cave+pin['cave_size']]).hexdigest() != pin['cave_input_sha256']:
        raise ValueError('Encoding thunk cave is not the original disabled ENC body')
    # The unused SJIS conversion loop is unreachable because 43K has no map.
    # Keep its map check/early -2 return and the older CP932 thunk untouched.
    flag = dol_offset(data, 0x81545864)
    if struct.unpack_from('>III', data, flag) != (0x2c000000, 0x4082000c, 0x3860fffe):
        raise ValueError('Disabled ENC map guard changed')
    call = pin['call_address']
    at = dol_offset(data, call)
    word = struct.unpack_from('>I', data, at)[0]
    displacement = word & 0x3fffffc
    if displacement & 1 << 25:
        displacement -= 1 << 26
    if word & 0xfc000003 != 0x48000001 or call + displacement != pin['expected_call_target']:
        raise ValueError('VerifyID encoding call guard changed')
    stub = encoding_stub()
    if len(stub) != pin['cave_size']:
        raise ValueError('Unexpected encoding thunk size')
    result = bytearray(data)
    result[cave:cave+len(stub)] = stub
    struct.pack_into('>I', result, at, 0x48000001 | ((pin['cave_address']-call) & 0x3fffffc))
    return bytes(result), dict(schema=1, call_address=hex(call), cave_address=hex(pin['cave_address']),
        cave_size=len(stub), stub_sha256=hashlib.sha256(stub).hexdigest(), supported_encodings=[0,1],
        card_data_writes=False, format_default_changed=False, integrity_checks_preserved=True,
        input_sha256=hashlib.sha256(data).hexdigest(), output_sha256=hashlib.sha256(result).hexdigest(),
        hardware_verified=False)

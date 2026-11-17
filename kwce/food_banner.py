"""Set the Food channel's IMET banner names to Korean.

The banner content carries a 0x40-byte build-tag prefix and an IMET header at
0x80, with ten 84-byte UTF-16BE name slots at 0x9c + 84*i and an MD5 integrity
field at 0x630 taken over banner[0x40:0x640] (that field zeroed during the
hash). Only the ten name slots are rewritten; every other banner byte and the
embedded icon/animation are preserved. The WiiLink English build calls this
"Food Channel"; we use '음식 배달 채널' for every language slot.
"""
import hashlib

NAME = '음식 배달 채널'
SLOT = 84
FIRST = 0x9c
MD5_AT = 0x630
MD5_RANGE = (0x40, 0x640)


def _imet_md5(banner):
    lo, hi = MD5_RANGE
    buf = bytearray(banner[lo:hi])
    for i in range(MD5_AT - lo, MD5_AT - lo + 16):
        buf[i] = 0
    return hashlib.md5(bytes(buf)).digest()


def korean_banner(content, name=NAME):
    banner = bytearray(content)
    if banner[0x80:0x84] != b'IMET':
        raise ValueError('Food banner: IMET header not at 0x80')
    # Confirm our MD5 model reproduces the shipped integrity field untouched.
    if _imet_md5(banner) != banner[MD5_AT:MD5_AT + 16]:
        raise ValueError('Food banner: IMET MD5 model does not match the original')
    payload = name.encode('utf-16-be')
    if len(payload) + 2 > SLOT:
        raise ValueError('Food banner: Korean name exceeds the 84-byte slot')
    for i in range(10):
        at = FIRST + SLOT * i
        banner[at:at + SLOT] = payload + bytes(SLOT - len(payload))
    banner[MD5_AT:MD5_AT + 16] = _imet_md5(banner)
    return bytes(banner), dict(name=name, slots=10, slot_bytes=SLOT,
                               imet_offset='0x80', integrity='md5 0x40..0x640',
                               icon_and_animation_unchanged=True)

"""Menu-side GC card format default: ANSI, the encoding games use on a Korean Wii.

CARDInit stores the console font encoding, and CARDFormat writes it into a new
card's header. The KWCE 'Japanese memory card encoding' step replaced that
call with `li r3,1` (Shift-JIS) so the menu would mount Japanese test cards.
Mounting no longer depends on it: the per-card VerifyID thunk
(gc_card_encoding.py) accepts ANSI and Shift-JIS headers by themselves.

The value now only decides how the Wii menu formats a card, and Shift-JIS is
the wrong choice on a Korean console. BS2 enables NTSC-J only for a Japanese
console region, so every GameCube game here, Japanese ones included, reports
ANSI from OSGetFontEncode. Hardware evidence (2026-11-08): a card created as
Japan/Shift-JIS was rejected by the Japanese Super Smash Bros. Melee disc,
which re-initialised it, and the result was an ANSI card. A card formatted by
the menu as Shift-JIS would therefore be refused by every game.

This changes that single immediate to ANSI (0). Existing cards are not
touched; only cards the user formats from the menu afterwards are affected.
"""
import hashlib
import struct

from .gc_native import dol_offset

CALL = 0x815375ac            # CARDInit: originally bl OSGetFontEncode (0x81508bf8)
SJIS = 0x38600001            # li r3,1 written by patch_gc_native(japanese_cards=True)
ANSI = 0x38600000            # li r3,0


def patch_format_ansi(data):
    at = dol_offset(data, CALL)
    if struct.unpack_from('>I', data, at)[0] != SJIS:
        raise ValueError('CARDInit encoding is not the KWCE Shift-JIS immediate')
    result = bytearray(data)
    struct.pack_into('>I', result, at, ANSI)
    return bytes(result), dict(schema=1, address=hex(CALL), before='li r3,1', after='li r3,0',
                               affects='CARDFormat header encoding only', card_data_writes=False,
                               input_sha256=hashlib.sha256(data).hexdigest(),
                               output_sha256=hashlib.sha256(result).hexdigest(), hardware_verified=False)

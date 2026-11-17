"""GC save comments: pick the decoder from the save's game region, not the card.

43K's MemoryCardManager::getComment chooses Shift-JIS only when the console
language is Japanese; every other language (Korean included) uses the
Latin-1 converter ANSIToUTF16. The KWCE comment patch redirects that Latin-1
call to a bounded CP932 adapter so that Japanese saves read correctly on a
Korean console. That also sent US/PAL comments through CP932, where Latin-1
letters such as e-acute (0xE9) are Shift-JIS lead bytes: they became kanji
and swallowed the next letter.

The card's encoding byte cannot decide this on a Korean console. The console
region is not Japan, so BS2 leaves NTSC-J off and a Japanese game formats and
writes an ANSI card while still storing Shift-JIS comment text.

This dispatcher reads the save's directory entry from the mounted card and
uses the region letter of its game code: 'J' keeps the CP932 adapter, any
other region takes the original Latin-1 converter. Whenever the card is not
attached, the file number is out of range or the entry is empty, it falls
back to the CP932 adapter, i.e. the behaviour already verified on hardware.

Inputs at the patched call (MemoryCardManager::getComment+0x164, 43K):
  r3, r4, r5  converter arguments (dst, src, length), passed through unchanged
  r23         card channel (getComment's u8 argument, callee-saved)
  r28         card file number * 0x15c (callee-saved, unchanged since +0x4c)
SDK layout (43K __CARDGetControlBlock / __CARDGetDirBlock):
  __CARDBlock 0x8112FFC8, stride 0x118, attached +0x00, currentDir +0x84.
No card bytes are written; the existing adapter and the encoding thunk stay.
"""
import hashlib
import struct

from .gc_native import dol_offset
from .ppc_patch import assemble

CALL = 0x813cd634            # bl to the comment converter inside getComment
ADAPTER = 0x815458d8         # existing bounded CP932 adapter (gc_comment.c)
ANSI = 0x81363390            # original ANSIToUTF16 (Latin-1)
CAVE = 0x81545a20            # unreachable SJIS loop body, after the encoding thunk
CAVE_END = 0x81545b1c        # epilogue of the disabled ENC function stays
THUNK = (0x81545a00, 0x81545a14)

SOURCE = '''
    cmplwi  23, 1
    bgt     cp932
    lis     12, 0x8113
    addi    12, 12, -0x38
    mulli   11, 23, 0x118
    add     12, 12, 11
    lwz     11, 0(12)
    cmpwi   11, 0
    beq     cp932
    lwz     12, 0x84(12)
    cmpwi   12, 0
    beq     cp932
    li      11, 0x15c
    divwu   11, 28, 11
    cmplwi  11, 127
    bge     cp932
    slwi    11, 11, 6
    add     12, 12, 11
    lbz     11, 0(12)
    cmplwi  11, 0xff
    beq     cp932
    lbz     11, 3(12)
    cmplwi  11, 0x4a
    beq     cp932
    b       ansi_converter
cp932:
    b       cp932_adapter
'''


def dispatcher():
    return assemble(SOURCE, CAVE, {'ansi_converter': ANSI, 'cp932_adapter': ADAPTER})


def _target(word, address):
    displacement = word & 0x3fffffc
    if displacement & 1 << 25:
        displacement -= 1 << 26
    return address + displacement


def patch_comment_region(data):
    """Apply on top of a menu that already has the CP932 comment adapter."""
    call = dol_offset(data, CALL)
    word = struct.unpack_from('>I', data, call)[0]
    if word & 0xfc000003 != 0x48000001 or _target(word, CALL) != ADAPTER:
        raise ValueError('Comment call does not reach the CP932 adapter')
    code = dispatcher()
    if CAVE + len(code) > CAVE_END:
        raise ValueError('Dispatcher exceeds the unreachable ENC body')
    start = dol_offset(data, CAVE)
    region = data[start:start + (CAVE_END - CAVE)]
    # The space must still hold the original (unreachable) instructions.
    from pathlib import Path
    original = (Path(__file__).resolve().parents[1] / 'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    if region != original[dol_offset(original, CAVE):dol_offset(original, CAVE_END)]:
        raise ValueError('Dispatcher cave already changed')
    result = bytearray(data)
    result[start:start + len(code)] = code
    struct.pack_into('>I', result, call, 0x48000001 | ((CAVE - CALL) & 0x3fffffc))
    return bytes(result), dict(schema=1, call=hex(CALL), cave=hex(CAVE), size=len(code),
                               sha256=hashlib.sha256(code).hexdigest(),
                               japanese_region='J', fallback='cp932_adapter',
                               card_data_writes=False, hardware_verified=False)

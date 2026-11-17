"""News banner/icon channel scripts: always use the news language the channel saved.

The Wii Menu runs ``arc/banner.cs.lz7`` (content 5) and ``arc/icon.cs.lz7`` (content 4) to show
headlines. Both read ``noerase/savedata.dat``: +4 = console language when the channel last saved,
+8 = the news language the channel chose. Only when +4 equals ``SCGetLanguage()`` do they use +8;
otherwise they look for news in the console language. The Korean build serves English news to a
Korean (9) console and saves +4 = +8 = 1, so the scripts searched for Korean news, found
"invalid language" and showed "뉴스를 가져올 수 없습니다" (Dolphin and hardware alike).

The edit replaces the 2-byte ``BF`` after that comparison with two ``STORE_UNDEFINED`` (0x2B)
opcodes, so the saved news language (+8) is always used. The accumulator is reloaded by the next
instruction; nothing else in either script changes.
"""
import hashlib
from .channels import ChannelArchive, compress_lz10

# (content index, archive path, code-relative pc of the BF, original BF bytes, expected script sha256)
EDITS = (
    (5, 'arc/banner.cs.lz7', 0x575, bytes.fromhex('a006')),
    (4, 'arc/icon.cs.lz7', 0x5c0, bytes.fromhex('a006')),
)
CODE_BASE = 0x80          # RCHE header 0x20 + module header 0x60 (pData = 0x60)
LANG_COMPARE = bytes.fromhex('10')   # EQ right before the BF


def _decompress_lz10(data):
    from .channels import load_library
    load_library()
    from libWiiPy.archive import decompress_lz77
    return decompress_lz77(data)


def patch_script(script, pc, old):
    at = CODE_BASE + pc
    if script[:4] != b'RCHE' or script[at - 1:at] != LANG_COMPARE or script[at:at + 2] != old:
        raise ValueError(f'Script site {pc:#x} differs')
    out = bytearray(script); out[at:at + 2] = b'\x2b\x2b'
    return bytes(out)


def patch_contents(contents):
    """contents: list of decrypted WAD contents. Returns (new contents dict {index: bytes}, record)."""
    changed, record = {}, []
    for index, path, pc, old in EDITS:
        archive = ChannelArchive(contents[index])
        packed = archive.get(path)
        script = _decompress_lz10(packed)
        edited = patch_script(script, pc, old)
        repacked = compress_lz10(edited)
        if _decompress_lz10(repacked) != edited: raise ValueError('LZ10 roundtrip')
        changed[index] = archive.replace(path, repacked)
        record.append(dict(content=index, path=path, pc=f'{pc:#x}', script_sha256=hashlib.sha256(script).hexdigest(),
                           edited_sha256=hashlib.sha256(edited).hexdigest()))
    return changed, record

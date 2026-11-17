"""Forecast Wii Menu banner: Korean "issued at" line (content 5 only).

After the build-v106 language fix the banner shows data, but its time line is
English ("As of 4:00 p.m., 10/24"). The banner RSO formats that line in one
function (file offset 0x1d34, args r6 = OSCalendarTime*, r7 = area, r8 = data
language from Common::getLanguage):

* r7 == 1 and r8 == 1 -> "As of %d:%02d %ls, %02d/%02d" (hour12, min, a.m./p.m.,
  month, day); the path a Korean console takes (language 9 -> data language 1);
* r7 == 1 and r8 == 3 -> French; otherwise a table by language, where the
  Japanese entry (0x1e04) formats "%d日 %d時発表" from (day, hour).

Edit, same sizes, no relocation touched, DOL and other contents untouched:

* 0x1d44 ``bne 0x1da8`` -> ``b 0x1e04``: after the section base (r10) and the
  calendar pointer (r11) are set, every console takes the day/hour branch;
* 0x1e14 ``addi r5,r10,0x230`` -> ``addi r5,r10,0x1ac``: that branch now reads the
  former English slot (60 bytes), which holds "%d일 %d시 발표" (NUL padded).

The Japanese string itself is not changed. The Korean build only runs on
Korean consoles (language 9), so no other language path is reachable there.
"""
import hashlib
import struct

from .channels import ChannelArchive, compress_lz10
from .forecast_banner_language import BANNER_MEMBER, _lz

BRANCH = 0x1d44             # bne 0x1da8 (area/language test)
DAY_HOUR = 0x1e04           # Japanese day/hour branch
FORMAT_ADDI = 0x1e14        # addi r5,r10,0x230 (Japanese format)
SECTION5 = 0x4840           # data section holding the format strings
ENGLISH = 0x1ac             # offset of the US English format in section 5
JAPANESE = 0x230
ENGLISH_TEXT = 'As of %d:%02d %ls, %02d/%02d'
KOREAN_TEXT = '%d일 %d시 발표'
V106_RSO_SHA256 = '0b93a97b27a4'  # prefix of the decompressed build-v106 banner RSO


def _bc(at, target, cond):
    return (0x40820000 if cond else 0x48000000) | ((target - at) & (0xFFFC if cond else 0x3FFFFFC))


def _addi(rt, ra, imm):
    return (14 << 26) | (rt << 21) | (ra << 16) | (imm & 0xFFFF)


def _relocated(rso):
    """File offsets touched by any internal or external relocation."""
    u32 = lambda a: struct.unpack_from('>I', rso, a)[0]
    out = set()
    for table, size in ((u32(0x30), u32(0x34)), (u32(0x38), u32(0x3C))):
        for i in range(size // 12):
            out.add(struct.unpack_from('>I', rso, table + 12 * i)[0])
    return out


def patch_banner_date(rso):
    """Return (patched RSO, record). Raises unless the v106 banner matches exactly."""
    if not hashlib.sha256(rso).hexdigest().startswith(V106_RSO_SHA256):
        raise ValueError('Forecast banner RSO is not the build-v106 module')
    word = lambda a: struct.unpack_from('>I', rso, a)[0]
    if word(BRANCH) != _bc(BRANCH, 0x1da8, True) or word(FORMAT_ADDI) != _addi(5, 10, JAPANESE):
        raise ValueError('Banner date function differs')
    slot = SECTION5 + ENGLISH
    old = (ENGLISH_TEXT + '\0').encode('utf-16-be')
    if rso[slot:slot + len(old)] != old or rso[SECTION5 + JAPANESE:SECTION5 + JAPANESE + 4] != '%d'.encode('utf-16-be'):
        raise ValueError('Banner date strings differ')
    new = (KOREAN_TEXT + '\0').encode('utf-16-be')
    if len(new) > len(old):
        raise ValueError('Korean date format exceeds the English slot')
    touched = _relocated(rso)
    if any(a in touched for a in (BRANCH, FORMAT_ADDI)) or any(slot <= a < slot + len(old) for a in touched):
        raise ValueError('Relocation inside the edited range')
    out = bytearray(rso)
    struct.pack_into('>I', out, BRANCH, _bc(BRANCH, DAY_HOUR, False))
    struct.pack_into('>I', out, FORMAT_ADDI, _addi(5, 10, ENGLISH))
    out[slot:slot + len(old)] = new.ljust(len(old), b'\0')
    return bytes(out), dict(member=BANNER_MEMBER, branch=hex(BRANCH), day_hour_branch=hex(DAY_HOUR),
                            format_addi=hex(FORMAT_ADDI), slot=hex(slot), before=ENGLISH_TEXT,
                            after=KOREAN_TEXT, args='day, hour (OSCalendarTime +0x0c, +0x08)',
                            size_preserved=len(out) == len(rso), relocations_changed=False)


def patch_content(banner_content):
    """Pure: content 5 (U8 archive) -> patched archive and a record."""
    arc = ChannelArchive(banner_content)
    raw = _lz(arc.get(BANNER_MEMBER))
    new, record = patch_banner_date(raw)
    packed = compress_lz10(new)
    if _lz(packed) != new:
        raise ValueError('LZ round trip failed')
    record['banner_rso_sha256'] = dict(before=hashlib.sha256(raw).hexdigest(), after=hashlib.sha256(new).hexdigest())
    return ChannelArchive(arc.replace(BANNER_MEMBER, packed)).compact(), record

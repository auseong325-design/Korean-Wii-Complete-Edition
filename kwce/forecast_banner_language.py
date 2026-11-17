"""Forecast Wii Menu icon/banner language fix (banner-only, contents 4 and 5).

Cause [static analysis of build-v103 == WiiLink archive contents 4/5]:
the channel downloads data in ``Common::getLanguage()`` = SCGetLanguage() when
0..6, else 1 (English); a Korean console (language 9) therefore receives English
(1) country-136 files. Both Wii Menu presenters then compare the data language
byte (offset 24 of ``3.bin``/``4.bin`` in ``wc24dl.vff``) with the RAW
SCGetLanguage() (9) and reject every file:

* icon channel script (content 4, ``arc/icon.cs.lz7``) ``load()`` at pc 0x0524 and
  0x0623 -> "forecastData/shortData: language changed" -> no data;
* banner RSO (content 5, ``arc/banner.rso.lz7``) ``Forecast::setup`` at 0x2934 and
  0x29bc -> return 4/7 -> reception-failure caption.

Fix, same sizes, no new code or section, DOL untouched:

* icon: each 20-byte check becomes
  ``load System; callm SCGetLanguage; case OK; gei 7; bf FAIL; ldi 1; case OK;
  FAIL: pop; ldi 0; retv`` -- accept when data language == console language, or
  when the console language is >= 7 and the data is English (the mapping the
  channel and Common::getLanguage use);
* banner RSO: both ``bl SCGetLanguage`` become ``bl Common::getLanguage`` (0x38d0,
  same module) and their two external R_PPC_REL24 relocations become R_PPC_NONE
  (RSORelocate ignores type 0; the import's relocation run stays contiguous).

Only the language comparison changes; every other check (savedata, size, CRC,
version, expiry, place lookup) stays as shipped.
"""
import hashlib
import struct

from . import channel_script
from .channels import ChannelArchive, compress_lz10, load_library

ICON_MEMBER = 'arc/icon.cs.lz7'
BANNER_MEMBER = 'arc/banner.rso.lz7'
ICON_SHA256 = 'a16d43d714a8'      # prefix of the decompressed v103/WiiLink/Nintendo icon script
RSO_SHA256 = '3ba440e73a62'       # prefix of the decompressed v103/WiiLink banner RSO
ICON_CHECKS = (0x0524, 0x0623)    # first byte after the data-language ``push``
RSO_CALLS = (0x2934, 0x29BC)      # ``bl SCGetLanguage`` in Forecast::setup
RSO_GET_LANGUAGE = 0x38D0         # getLanguage__6CommonFv (file offset)
R_PPC_REL24 = 10


def _lz(data):
    load_library()
    from libWiiPy.archive import decompress_lz77
    return decompress_lz77(data)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def patch_icon_script(script):
    """Return (patched RCHE bytes, record). Raises unless both checks match exactly."""
    module = channel_script.parse(script)
    code_at = 0x20 + struct.unpack_from('>I', script, 0x30)[0]
    ins = {i['pc']: i for i in channel_script.decode(module)}
    out = bytearray(script)
    for pc in ICON_CHECKS:
        seq = []
        at = pc
        for _ in range(10):
            seq.append(ins[at])
            at += ins[at]['size']
        names = [i['text'] for i in seq]
        expect = ['load System', 'callm .SCGetLanguage argc=0', 'ne']
        if names[:3] != expect or seq[3]['mnemonic'] != 'bf' or ins[pc - 1]['mnemonic'] != 'push':
            raise ValueError(f'Forecast icon language check differs at {pc:#06x}')
        if not seq[4]['text'].startswith("ldstr '$ ") or 'language changed' not in seq[4]['text']:
            raise ValueError(f'Forecast icon language message differs at {pc:#06x}')
        if [i['text'] for i in seq[5:9]] != ['push', 'load print', 'callf argc=1', 'ldi 0'] or seq[9]['mnemonic'] != 'retv':
            raise ValueError(f'Forecast icon failure path differs at {pc:#06x}')
        ok = seq[3]['target']
        if ok != pc + 20 or at != ok:
            raise ValueError(f'Forecast icon check length differs at {pc:#06x}')
        raw = bytes(out[code_at + pc:code_at + pc + 6])          # load System + callm SCGetLanguage
        body = bytearray(raw)
        body += bytes([0x80, (ok - (pc + 8)) & 0xFF])            # case OK   (pops on match)
        body += bytes([0x26, 7])                                 # gei 7
        body += bytes([0xA0, (pc + 16 - (pc + 12)) & 0xFF])      # bf FAIL
        body += bytes([0x18, 1])                                 # ldi 1
        body += bytes([0x80, (ok - (pc + 16)) & 0xFF])           # case OK
        body += bytes([0x05, 0x18, 0x00, 0x01])                  # FAIL: pop; ldi 0; retv
        if len(body) != 20:
            raise ValueError('Icon patch size')
        out[code_at + pc:code_at + pc + 20] = body
    patched = bytes(out)
    check = channel_script.parse(patched)
    got = {i['pc']: i['text'] for i in channel_script.decode(check)}
    for pc in ICON_CHECKS:
        if got.get(pc + 6) != f'case {pc + 20:#06x}' or got.get(pc + 16) != 'pop' or got.get(pc + 19) != 'retv':
            raise ValueError('Icon patch decode check failed')
    return patched, dict(member=ICON_MEMBER, checks=[f'{pc:#06x}' for pc in ICON_CHECKS], bytes_per_check=20,
                         rule='accept data language == SCGetLanguage(), or SCGetLanguage() >= 7 with English (1) data',
                         size_preserved=len(patched) == len(script))


def _rso_tables(rso):
    u32 = lambda a: struct.unpack_from('>I', rso, a)[0]
    erel, ersz = u32(0x38), u32(0x3C)
    itab, isz, istr = u32(0x4C), u32(0x50), u32(0x54)
    etab, esz, estr = u32(0x40), u32(0x44), u32(0x48)
    name = lambda a: rso[a:rso.index(b'\0', a)].decode('ascii')
    imports = [name(istr + u32(itab + 12 * i)) for i in range(isz // 12)]
    sections = [struct.unpack_from('>II', rso, u32(0x0C) + 8 * i) for i in range(u32(8))]
    exports = {}
    for i in range(esz // 16):
        so, val, sec, _ = struct.unpack_from('>IIII', rso, etab + 16 * i)
        if sec < len(sections):
            exports[name(estr + so)] = sections[sec][0] + val
    return erel, ersz, imports, exports


def patch_banner_rso(rso):
    """Return (patched RSO bytes, record). Raises unless the module matches exactly."""
    erel, ersz, imports, exports = _rso_tables(rso)
    if exports.get('getLanguage__6CommonFv') != RSO_GET_LANGUAGE or exports.get('setup__8ForecastFUli') != 0x286C:
        raise ValueError('Forecast banner RSO exports differ')
    if rso[RSO_GET_LANGUAGE:RSO_GET_LANGUAGE + 0x40].hex() != (
            '9421fff07c0802a690010014480000015460063e2c000007408000142c000000'
            '40800010480000084800000838600001800100147c0803a6382100104e800020'):
        raise ValueError('Common::getLanguage body differs')
    lang = imports.index('SCGetLanguage')
    out = bytearray(rso)
    hits = []
    for i in range(ersz // 12):
        at = erel + 12 * i
        off, info, add = struct.unpack_from('>III', rso, at)
        if off in RSO_CALLS:
            if info != (lang << 8) | R_PPC_REL24 or add != 0:
                raise ValueError(f'Relocation at {off:#x} is not REL24 SCGetLanguage')
            if rso[off] & 0xFC != 0x48 or rso[off + 3] & 3 != 1:
                raise ValueError(f'Instruction at {off:#x} is not bl')
            struct.pack_into('>I', out, at + 4, lang << 8)               # R_PPC_NONE, same symbol run
            delta = RSO_GET_LANGUAGE - off
            struct.pack_into('>I', out, off, 0x48000001 | (delta & 0x03FFFFFC))
            hits.append(off)
    if sorted(hits) != list(RSO_CALLS):
        raise ValueError('Forecast banner language relocations not found')
    return bytes(out), dict(member=BANNER_MEMBER, calls=[f'{x:#x}' for x in RSO_CALLS],
                            target='getLanguage__6CommonFv', relocation_type='R_PPC_REL24 -> R_PPC_NONE',
                            size_preserved=len(out) == len(rso))


def patch_contents(icon_content, banner_content):
    """Pure: content 4 and content 5 (U8 archives) -> patched archives and a record."""
    icon_arc, banner_arc = ChannelArchive(icon_content), ChannelArchive(banner_content)
    icon_raw, rso_raw = _lz(icon_arc.get(ICON_MEMBER)), _lz(banner_arc.get(BANNER_MEMBER))
    if not _sha(icon_raw).startswith(ICON_SHA256) or not _sha(rso_raw).startswith(RSO_SHA256):
        raise ValueError('Forecast icon/banner module differs from build-v103')
    icon_new, icon_rec = patch_icon_script(icon_raw)
    rso_new, rso_rec = patch_banner_rso(rso_raw)
    icon_lz, rso_lz = compress_lz10(icon_new), compress_lz10(rso_new)
    if _lz(icon_lz) != icon_new or _lz(rso_lz) != rso_new:
        raise ValueError('LZ round trip failed')
    c4 = ChannelArchive(icon_arc.replace(ICON_MEMBER, icon_lz)).compact()
    c5 = ChannelArchive(banner_arc.replace(BANNER_MEMBER, rso_lz)).compact()
    record = dict(icon=icon_rec, banner=rso_rec,
                  icon_script_sha256=dict(before=_sha(icon_raw), after=_sha(icon_new)),
                  banner_rso_sha256=dict(before=_sha(rso_raw), after=_sha(rso_new)))
    return c4, c5, record

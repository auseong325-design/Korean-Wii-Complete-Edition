"""Port WiiLink's Wiimmfi patch for the Wii Speak Channel to the Korean title.

WiiLink publishes Wiimmfi patches for the Japanese, USA and PAL Wii Speak
executables only (WiiSpeak_1_<region>.bsdiff). The official Korean channel
(000100014843464b v512) is already Korean, so the only work is the network
patch. Applied to the decompressed main executable (content 1):

1. Strings: every NUL-terminated network string that WiiLink's JP patch
   changes (nintendowifi.net -> wiimmfi.de, https -> http, HTTP agent
   'RVL SDK/1.0' -> 'J-3-1') is rewritten with the exact slot bytes the JP
   reference wrote. The edit table is derived from the JP reference, and
   replaying it on the JP stock executable must reproduce the reference
   byte-for-byte outside the patched routine.
2. Code: the DWC receive routine gets the same safety check as the JP
   patch: header byte sp+17 (a payload length) must be <= 128, otherwise
   the routine's existing error path runs. The Korean build allocates
   registers differently, so the JP words cannot be copied; the same logic
   is re-derived for the Korean registers. Every replaced word and every
   word between a compare and its branch is verified before writing.
"""
import hashlib

from .ppc_patch import assemble, to_file

KR_DOL_SHA256 = '7d95dd7b647dd8b74fa1038aaf93fcb5451e27ebed6cb1ed10b14a2a91806c17'
JP_DOL_SHA256 = '7da329f17754d3199b6254f26c3e059913671820f9017c2424236430aa64eff3'
JP_PATCHED_SHA256 = '316432849cbc949e5131e6cbc916716594766993362b85859d3974480d39b064'
JP_FUNCTION = 0x8039fcd4   # JP DWC receive routine (stwu r1,-176(r1))
KR_FUNCTION = 0x8036e420   # same routine in the Korean executable
FUNCTION_SIZE = 0x28c

# (offset, original Korean word, replacement). Block 1 replaces the byte swap
# of sp+12 (compared with 90) by a raw compare with 0x5a000000, which frees the
# words for the length check; the Korean code keeps sp+12 in r0 only until
# +0x9c, so the compare is placed there and the displaced swap step moves to +0xa0.
KR_BLOCKS = [
    (0x88, 0x5405c21e, 'lbz r5,17(r1)'),
    (0x8c, 0x5404400e, 'cmplwi r5,128'),
    (0x90, 0x5005c63e, 'bgt err1'),
    (0x98, 0x5004442e, 'lis r5,0x5a00'),
    (0x9c, 0x54e0400e, 'cmpw r5,r0'),
    (0xa0, 0x7ca42378, 'rlwinm r0,r7,8,0,7'),
    (0xa8, 0x5485803e, 'nop'),
    (0xbc, 0x2805005a, 'nop'),
    # Block 2: a byte-reversed load replaces the second swap of sp+12.
    (0x20c, 0x54e8c21e, 'li r7,4'),
    (0x210, 0x54e5400e, 'lwbrx r8,r3,r7'),
    (0x220, 0x50e8c63e, 'stw r8,12(r1)'),
    (0x224, 0x50e5442e, 'lbz r8,17(r1)'),
    (0x234, 0x7d082b78, 'cmplwi r8,128'),
    (0x244, 0x5500803e, 'nop'),
    (0x248, 0x9001000c, 'bgt err2'),
]
KR_ERROR_TARGETS = {'err1': 0xfc, 'err2': 0x264}
# Unchanged Korean words the new logic depends on (register sources, and every
# word between each compare and its conditional branch: none may set cr0).
KR_CONTEXT = {
    0x80: 0x8001000c, 0x84: 0x80e10018, 0x94: 0x54e3c21e, 0xa4: 0xa0c10012,
    0xac: 0x50e3c63e, 0xb0: 0x50e0442e, 0xb4: 0x7cc44670, 0xb8: 0x7c600378,
    0xc0: 0x50c4422e, 0xc4: 0x90a1000c, 0xc8: 0x5400803e, 0xcc: 0xb0810012,
    0xd0: 0x90010018, 0xd4: 0x41820018, 0xec: 0x88a10011, 0xf0: 0x38050014,
    0x1fc: 0x80e1000c, 0x200: 0x38610008, 0x204: 0x81410018, 0x214: 0x5546c21e,
    0x218: 0x5540400e, 0x21c: 0xa1210012, 0x228: 0x5146c63e, 0x22c: 0x5140442e,
    0x230: 0x7d274670, 0x238: 0x38a00004, 0x23c: 0x7cc60378, 0x240: 0x5127422e,
    0x24c: 0x54c0803e, 0x250: 0xb0e10012, 0x254: 0x90010018,
}
# Existing error paths (addi r4,<base>,<message>; li r3,8; crclr) the branches reuse.
KR_ERROR_PATHS = {0xfc: '389d25f8386000084cc63182', 0x264: '389f2678386000084cc63182'}
TOKENS = (b'https://', b'http://', b'%s.')


def _runs(buf):
    """(start, bytes) of printable runs terminated by NUL."""
    out = []
    i, n = 0, len(buf)
    while i < n:
        if 0x20 <= buf[i] < 0x7f:
            j = i
            while j < n and 0x20 <= buf[j] < 0x7f:
                j += 1
            if j < n and buf[j] == 0:
                out.append((i, bytes(buf[i:j])))
            i = j + 1
        else:
            i += 1
    return out


def _token_start(s):
    hits = [s.find(t) for t in TOKENS if s.find(t) >= 0]
    return min(hits) if hits else 0


def derive_string_edits(stock, patched):
    """{old string: slot bytes written by the reference} for each changed run."""
    edits = {}
    for at, run in _runs(stock):
        if patched[at:at + len(run) + 1] == run + b'\0':
            continue
        k = _token_start(run)
        if run[:k] != patched[at:at + k]:
            raise ValueError('Reference changed bytes before the string token')
        old, slot = run[k:], bytes(patched[at + k:at + len(run) + 1])
        if not (b'nintendowifi.net' in old or old.startswith(b'https://') or old == b'RVL SDK/1.0'):
            raise ValueError('Unexpected reference string edit: ' + old.decode())
        if edits.get(old, slot) != slot:
            raise ValueError('Inconsistent reference string edit')
        edits[old] = slot
    return edits


def apply_string_edits(dol, edits):
    out = bytearray(dol)
    counts = {}
    for at, run in _runs(dol):
        k = _token_start(run)
        slot = edits.get(run[k:])
        if slot is None:
            continue
        if len(slot) != len(run) - k + 1:
            raise ValueError('Slot size differs')
        out[at + k:at + len(run) + 1] = slot
        key = run[k:].decode()
        counts[key] = counts.get(key, 0) + 1
    return bytes(out), counts


def _word(dol, va):
    at = to_file(dol, va)
    return int.from_bytes(dol[at:at + 4], 'big')


def apply_kr_dwc_fix(dol):
    for offset, original, _ in KR_BLOCKS:
        if _word(dol, KR_FUNCTION + offset) != original:
            raise ValueError(f'Korean DWC routine differs at +{offset:#x}')
    for offset, expected in KR_CONTEXT.items():
        if _word(dol, KR_FUNCTION + offset) != expected:
            raise ValueError(f'Korean DWC routine context differs at +{offset:#x}')
    for offset, prefix in KR_ERROR_PATHS.items():
        at = to_file(dol, KR_FUNCTION + offset, 12)
        if dol[at:at + 12].hex() != prefix:
            raise ValueError(f'Korean DWC error path differs at +{offset:#x}')
    if _word(dol, KR_FUNCTION) != 0x9421ff50:
        raise ValueError('Korean DWC routine entry differs')
    symbols = {name: KR_FUNCTION + offset for name, offset in KR_ERROR_TARGETS.items()}
    out = bytearray(dol)
    words = []
    for offset, original, source in KR_BLOCKS:
        code = assemble(source, KR_FUNCTION + offset, symbols)
        if len(code) != 4:
            raise ValueError('One instruction per replaced word')
        at = to_file(dol, KR_FUNCTION + offset)
        out[at:at + 4] = code
        words.append(dict(offset=hex(offset), original=f'{original:08x}', new=code.hex(), asm=source))
    return bytes(out), words


def port(kr_dol, jp_dol, jp_patched):
    if hashlib.sha256(kr_dol).hexdigest() != KR_DOL_SHA256:
        raise ValueError('Only the official Korean Wii Speak v512 executable is supported')
    if hashlib.sha256(jp_dol).hexdigest() != JP_DOL_SHA256 or hashlib.sha256(jp_patched).hexdigest() != JP_PATCHED_SHA256:
        raise ValueError('Reference JP executable/WiiLink patch output differs')
    edits = derive_string_edits(jp_dol, jp_patched)
    replay, _ = apply_string_edits(jp_dol, edits)
    lo = to_file(jp_dol, JP_FUNCTION, FUNCTION_SIZE)
    hi = lo + FUNCTION_SIZE
    if replay[:lo] != jp_patched[:lo] or replay[hi:] != jp_patched[hi:]:
        raise ValueError('Derived string edits do not reproduce the JP reference')
    out, counts = apply_string_edits(kr_dol, edits)
    absent = sorted(k.decode() for k in edits if k.decode() not in counts)
    out, words = apply_kr_dwc_fix(out)
    return out, dict(reference='WiiLink WiiSpeak_1_Japan.bsdiff (Wiimmfi)', reference_string_edits=len(edits),
                     string_edits=counts, reference_strings_absent_in_korean=absent, dwc_words=words,
                     changed_bytes=sum(a != b for a, b in zip(kr_dol, out)),
                     jp_string_replay_matches_reference=True, korean_function_va=hex(KR_FUNCTION),
                     hardware_success_verified=False)

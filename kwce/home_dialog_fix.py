"""HOME Menu fixes inside two channels' own copy of the HOME Button library (2026-11-16 photos).

1. Dialog text too small (Food, Nintendo). When the HOME confirmation dialog opens, the linked
   library calls nw4r ``TextBox::SetFont(T_Dialog, font)``. SetFont resets the text box font size
   to the font's own cell (24x28), so the layout size (33.25x35.15, which the official Korean
   channels keep) is lost and the sentence draws at ~0.78 scale. The two ``bl SetFont`` calls are
   replaced by ``nop``: T_Dialog keeps the font it was built with and its layout size.
   [direct: Dolphin, food matches the Korean Photo Channel dialog size]
2. Light strips above/below the HOME Menu (Food only). Food builds the HOME projection with
   ``228 * 480/456 = 240`` vertical units (``lfs f1,-0x7f04(r2)`` = 1.0526), but the HOME layout is
   456 units tall, so 8 rows on top and 3 below its letterbox stay uncovered. The four projection
   loads and the two pointer y scale loads now read ``-0x7f08(r2)`` (1.0): HOME covers the frame,
   pointer mapping stays consistent. Same behaviour with the original Japanese HOME archive.
"""
import hashlib, struct
from .ppc_patch import to_file

NOP = 0x60000000
FOOD = dict(
    parent_executable_sha256='0f2d203a681d4441e26f2226e861c1183787b98555b817c522a787e566149c08',
    edits=[(0x80211688, 0x4800af55, NOP), (0x802129b4, 0x48009c29, NOP)] +
          [(a, w, (w & 0xffff0000) | 0x80f8) for a, w in (
              (0x8001d9dc, 0xc02280fc), (0x8001da18, 0xc02280fc), (0x8001e008, 0xc00280fc),
              (0x8001e030, 0xc00280fc), (0x8001e7b8, 0xc02280fc), (0x8001e7f4, 0xc02280fc))])
NINTENDO = dict(
    parent_executable_sha256='450272d9eaed94948bb401359504bb39b5caab61c7fe67c009abad9370fbe88d',
    edits=[(0x8011f5ec, 0x4800ae25, NOP), (0x80120938, 0x48009ad9, NOP)])


def patch(exe, spec):
    if hashlib.sha256(exe).hexdigest() != spec['parent_executable_sha256']:
        raise ValueError('Executable identity differs')
    out = bytearray(exe)
    for site, old, new in spec['edits']:
        at = to_file(exe, site, 4)
        if struct.unpack_from('>I', exe, at)[0] != old:
            raise ValueError(f'Site {site:#x} differs')
        struct.pack_into('>I', out, at, new)
    return bytes(out), dict(sites=[f'{s:#010x}' for s, _, _ in spec['edits']], source_sha256=spec['parent_executable_sha256'],
                            output_sha256=hashlib.sha256(out).hexdigest())

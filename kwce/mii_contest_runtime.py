"""In-channel runtime Korean translation of the server-supplied specialty vocabulary.

The Mii Contest Channel downloads `addition/<group>.ces` from the server and parses it in
``AdditionParse`` (content 1 @ 0x800678bc): the NJ records (tag 0x4E4A, u32 code + 96-byte name)
are stored by code into the skill table at ``obj + 0x801c + code*0x40`` (name at slot+0, read back
by the skill getter 0x80068720 which returns the slot pointer unchanged). Because WiiLink only
serves languages 0-6 (``first/addition.go`` GetSupportedLanguagesForRegion: region3 -> {1..6}; no
language 9), a Korean console falls back to the English slot, so the 19 specialty names
(Acting/Art/Athletics/... the 12:18 picker) and the specialty shown in a Mii's profile render in
English even though our BMG copies are Korean -- the picker reads the SERVER skill table, not BMG.

This patch moves a FIXED-vocabulary translation into the channel. A stub replaces the dispatcher's
single ``bl AdditionParse`` call site (0x800770b0): it runs the real parser, then a converter walks
the 19 known skill codes and, for each slot the server actually filled whose stored text still
equals the expected English, overwrites it in place with the reviewed Korean name (UTF-8, the same
encoding the channel's synthetic local feed proved renders with the system shared font wbf1 that
these panes use). Fail-safe and all-or-nothing per slot: an empty slot (skill not supplied), an
unknown code, or any text that does not match the expected English is left exactly as supplied, so
dynamic content (contest titles, Mii and artisan names, countries) is never touched. Every Korean
name is <= its 0x1f-byte slot, asserted when the table is built.

Only the ONE call-site word is rewritten; the converter lives in a new text section placed above
bss so the apploader's ArenaLo protects it (cf. kwce/forecast_supply.py, kwce/kirbytv_dol.py).
Hardware is not verified; see docs/channels/mii-contest.md.

build-v27 rework (``patch_specialty_cave``; the functions above stay only so build-v26 regenerates):
* Placement. build-v26's appended section (0x80431000, above bss end 0x80430724) panicked at boot in
  Dolphin (PC 0x80004040 = memcpy in .init). That address is inside the main boot stack, which
  __init_registers puts at 0x80430728..0x80440728 (r1 = 0x80440728), and past the image end the NAND
  loader and OS treat as free. build-v27 adds NO section: the stub, converter and table go into an
  in-place cave inside text0 (.init): MetroTRK's gTRKInterruptVectorTable (0x80004188, banner
  "Metrowerks Target Resident Kernel for PowerPC") has no handlers for vectors 0x1800..0x1B00, so
  0x80005988..0x80005d88 is 1024 zero bytes between the 0x1700 and 0x1C00 stubs. The table is only
  copied by InitMetroTRK, which __start reaches on the debug-monitor path alone. Before writing, the
  cave must be zero, bounded by those two stubs, and targeted by no branch, pointer word or lis-based
  address in any section. The DOL header, section table, file length and bss are unchanged.
* Encoding. A skill slot is UTF-16BE, not UTF-8: the store routine 0x80068388 clears the 64-byte
  slot and calls ENCConvertStringUtf8ToUnicode (0x80175974 -> 0x80175c80, UTF-8 source, ``sth`` u16
  output, 31 units), and the presence test 0x80068130 reads the first halfword. build-v26 compared
  and wrote bytes, so its "slot[0] == 0" test skipped every real slot and it never translated
  anything. The rule is unchanged (by code; only a supplied slot whose text is exactly the expected
  English; everything else left as supplied); comparisons and writes are now UTF-16BE units.
"""
import hashlib
import json
import struct
import subprocess
import tempfile
from pathlib import Path
from .toolchain import tool

from .ppc_patch import BIN, add_text_section, assemble, sections, to_file

# Dispatcher call site (AD tag -> AdditionParse) and the reused parser entry.
DISPATCH_SITE = 0x800770b0          # `bl 0x800678bc` == 0x4bff080d
ADDITION_PARSE = 0x800678bc         # AdditionParse(obj r3, buf r4, len r5); first word 0x9421f870
CONTEXT = {DISPATCH_SITE: 0x4bff080d, ADDITION_PARSE: 0x9421f870}

# Skill table geometry, from the parser store loop and the skill getter.
SKILL_TABLE_BIAS = 0x801c           # slot(code) = obj + 0x801c + code*0x40, name at slot+0
SKILL_SLOT_STRIDE = 0x40
SKILL_NAME_CAP = 0x1f               # bytes the parser copies into a slot

# New text section: 32-byte aligned, above bss end 0x80430724, reachable by bl from the 0x80077xxx
# site and to the 0x800678bc parser (<32 MiB). Loaded as the highest section so ArenaLo sits above.
SECTION_VA = 0x80431000

# Fixed server specialty vocabulary: code -> (expected English, reviewed-message id for the Korean).
# Codes/English come from the pinned server source (first/addition.json, region1['1'] skills, codes
# 1..19). The Korean is the channel's own reviewed specialty name (BMG ids 1163..1181) so the runtime
# vocabulary matches what the localized channel already shows elsewhere.
SKILL_ENGLISH = {
    1: 'Acting', 2: 'Art', 3: 'Athletics', 4: 'Comedy', 5: 'Conversation', 6: 'Cooking',
    7: 'Dance', 8: 'Design', 9: 'Exploration', 10: 'Fashion', 11: 'Fighting', 12: 'Gourmand',
    13: 'Music', 14: 'Secret', 15: 'Singing', 16: 'Speeches', 17: 'Study', 18: 'Supervising',
    19: 'Writing',
}
SKILL_REVIEWED_ID = {
    1: 1165, 2: 1176, 3: 1164, 4: 1166, 5: 1173, 6: 1172, 7: 1169, 8: 1175, 9: 1170, 10: 1179,
    11: 1168, 12: 1180, 13: 1167, 14: 1181, 15: 1163, 16: 1174, 17: 1177, 18: 1171, 19: 1178,
}

GCC = tool('powerpc-eabi-gcc.exe')
LD = tool('powerpc-eabi-ld.exe')
OBJCOPY = tool('powerpc-eabi-objcopy.exe')
NM = tool('powerpc-eabi-nm.exe')
GCC_FLAGS = ['-mcpu=750', '-meabi', '-mbig-endian', '-Os', '-ffreestanding', '-fno-builtin',
             '-fno-tree-loop-distribute-patterns', '-fno-pic', '-msdata=none', '-G0',
             '-ffixed-r2', '-ffixed-r13', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
             '-fomit-frame-pointer']

CONVERT_C = r'''
typedef unsigned char u8;
typedef unsigned int u32;

extern const u8 mc_table[];

/* Translate the fixed server specialty vocabulary in place, by code, fail-safe per slot. */
int mc_convert(u8 *obj){
    const u8 *t = mc_table;
    u32 n = ((u32)t[0]<<24)|((u32)t[1]<<16)|((u32)t[2]<<8)|t[3];
    u32 e, i;
    t += 4;
    for (e = 0u; e < n; e++){
        u8 code = t[0], el = t[1], kl = t[2];
        const u8 *en = t + 3;
        const u8 *ko = t + 3 + el;
        t = t + 3u + el + kl;
        if (code < 1u || code > 254u) continue;
        u8 *slot = obj + 0x801cu + (u32)code * 0x40u;
        if (slot[0] == 0u) continue;                 /* skill not supplied by the server */
        int ok = 1;
        for (i = 0u; i < el; i++){ if (slot[i] != en[i]){ ok = 0; break; } }
        if (ok && slot[el] != 0u) ok = 0;            /* must terminate exactly at el */
        if (!ok) continue;                           /* unexpected text -> leave as supplied */
        for (i = 0u; i < 0x20u; i++) slot[i] = 0u;
        for (i = 0u; i < kl; i++) slot[i] = ko[i];   /* kl <= 0x1e, asserted at build */
    }
    return 0;
}
'''

STUB_S = r'''
.text
.globl mc_stub
mc_stub:
  mflr   r0
  stwu   r1,-0x20(r1)
  stw    r0,0x24(r1)
  stw    r3,0x08(r1)
  bl     mc_parse
  stw    r3,0x0c(r1)
  lwz    r3,0x08(r1)
  bl     mc_convert
  lwz    r3,0x0c(r1)
  lwz    r0,0x24(r1)
  addi   r1,r1,0x20
  mtlr   r0
  blr
'''


def build_specialty_dict(root):
    """code -> (english, korean) using the channel's reviewed/draft specialty names."""
    root = Path(root)
    reviewed = json.loads((root / 'configs/mii-contest-reviewed-ko.json').read_text(encoding='utf-8'))['reviewed_messages']
    draft = json.loads((root / 'workspace/channels/mii-contest/draft/messages-ko.json').read_text(encoding='utf-8'))['messages']
    out = {}
    for code in sorted(SKILL_ENGLISH):
        mid = str(SKILL_REVIEWED_ID[code])
        korean = reviewed.get(mid, draft.get(mid))
        if not korean:
            raise ValueError(f'No reviewed Korean for specialty code {code} (message {mid})')
        out[code] = (SKILL_ENGLISH[code], korean)
    return out


def build_table(mapping):
    """u32 count, then per entry u8 code, u8 en_len, u8 ko_len, en bytes, ko bytes."""
    items = sorted(mapping.items())
    blob = bytearray(struct.pack('>I', len(items)))
    rows = []
    for code, (english, korean) in items:
        en = english.encode('ascii')
        ko = korean.encode('utf-8')
        if len(en) > SKILL_NAME_CAP or len(ko) > SKILL_NAME_CAP - 1:
            raise ValueError(f'Specialty name exceeds slot for code {code}: {english!r}->{korean!r}')
        blob += struct.pack('>BBB', code, len(en), len(ko)) + en + ko
        rows.append(dict(code=code, english=english, korean=korean, en_len=len(en), ko_len=len(ko)))
    return bytes(blob), rows


def _run(args, cwd=None):
    result = subprocess.run([str(args[0]), *map(str, args[1:])], capture_output=True, text=True, cwd=cwd)
    if result.returncode:
        raise ValueError(f'{Path(args[0]).name}: {result.stderr.strip()}')
    return result.stdout


def build_blob(table):
    """Compile the stub + converter at SECTION_VA, append the table, return (blob, record)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / 'convert.c').write_text(CONVERT_C, encoding='ascii')
        (tmp / 'stub.s').write_text(STUB_S, encoding='ascii')
        (tmp / 'link.ld').write_text(
            'SECTIONS {\n'
            f'  . = {SECTION_VA:#x};\n'
            '  .all : {\n'
            '    stub.o(.text .text.*)\n'
            '    *(.text .text.*)\n'
            '    *(.rodata .rodata.* .sdata2 .sdata2.*)\n'
            '    . = ALIGN(4);\n'
            '    mc_table = .;\n'
            '  }\n'
            '}\n', encoding='ascii')
        _run([GCC, *GCC_FLAGS, '-c', 'convert.c', '-o', 'convert.o'], cwd=tmp)
        _run([GCC, '-c', '-Wa,-mregnames,-mgekko', 'stub.s', '-o', 'stub.o'], cwd=tmp)
        libgcc = _run([GCC, *GCC_FLAGS, '-print-libgcc-file-name']).strip()
        _run([LD, '-T', 'link.ld', f'--defsym=mc_parse={ADDITION_PARSE:#x}',
              '-o', 'blob.elf', 'stub.o', 'convert.o', libgcc], cwd=tmp)
        syms = {}
        for line in _run([NM, 'blob.elf'], cwd=tmp).splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        if syms.get('mc_stub') != SECTION_VA:
            raise ValueError(f'mc_stub not at section base: {syms.get("mc_stub")}')
        und = [p.split()[-1] for p in _run([NM, '-u', 'blob.elf'], cwd=tmp).splitlines() if p.strip()]
        if und:
            raise ValueError(f'Unresolved symbols in hook: {und}')
        _run([OBJCOPY, '-O', 'binary', '-j', '.all', 'blob.elf', 'blob.bin'], cwd=tmp)
        code = (tmp / 'blob.bin').read_bytes()
    table_va = syms['mc_table']
    code_len = table_va - SECTION_VA
    code = code[:code_len].ljust(code_len, b'\0')
    blob = code + table
    record = dict(section_va=hex(SECTION_VA), mc_stub=hex(syms['mc_stub']),
                  mc_convert=hex(syms['mc_convert']), mc_table=hex(table_va),
                  code_bytes=code_len, table_bytes=len(table), blob_bytes=len(blob),
                  blob_sha256=hashlib.sha256(blob).hexdigest())
    return blob, record


def _word(dol, va):
    return struct.unpack_from('>I', dol, to_file(dol, va, 4))[0]


def verify_sites(dol):
    for va, word in CONTEXT.items():
        if _word(dol, va) != word:
            raise ValueError(f'Mii Contest addition path context differs at {va:#x}')


def patch_specialty_runtime(executable, mapping):
    """Add the specialty-vocabulary converter and redirect the AdditionParse call site.

    ``executable`` may already carry the keyboard-label edits (content 1, rev>=19); those touch only
    0x8033xxxx/0x8042xxxx slots, so the site and parser words still hold.
    """
    verify_sites(executable)
    table, rows = build_table(mapping)
    blob, record = build_blob(table)
    out = bytearray(executable)
    slot = add_text_section(out, SECTION_VA, blob)
    at = to_file(out, DISPATCH_SITE, 4)
    code = assemble('bl dest', DISPATCH_SITE, dict(dest=SECTION_VA))
    out[at:at + 4] = code
    record.update(dol_section_slot=slot, dispatch_site=hex(DISPATCH_SITE),
                  dispatch_word=code.hex(), reused_routine=dict(addition_parse=hex(ADDITION_PARSE)),
                  skill_table_bias=hex(SKILL_TABLE_BIAS), slot_stride=hex(SKILL_SLOT_STRIDE),
                  entries=rows, vocabulary='server specialty codes 1..19 (fixed)',
                  fail_safe='per-slot: empty/unknown/mismatched English left as supplied',
                  dynamic_left_as_supplied=['contest titles', 'Mii names', 'artisan names', 'countries', 'marquee'],
                  hardware_verified=False)
    return bytes(out), record



# ---------------------------------------------------------------------------------------------
# build-v27+: in-place code cave inside text0, UTF-16BE slots. No DOL section is added.
# ---------------------------------------------------------------------------------------------
TRK_TABLE = 0x80004188              # MetroTRK gTRKInterruptVectorTable (text0 / .init)
TRK_BANNER = b'Metrowerks Target Resident Kernel for PowerPC'
CAVE_VA = TRK_TABLE + 0x1800        # 0x80005988: first of the four empty vector slots 0x1800..0x1B00
CAVE_END = TRK_TABLE + 0x1c00       # 0x80005d88: the populated vector 0x1C00 stub starts here
CAVE_ZERO_FROM = 0x800058bc         # the zero run already starts right after the 0x1700 stub
# Words that bound the zero run: the 0x1700 stub's `li r3,0x1700; rfi` and the 0x1C00 stub's head.
CAVE_BOUNDS = {0x800058b4: 0x38601700, 0x800058b8: 0x4c000064,
               0x80005d88: 0x7c5143a6, 0x80005db4: 0x38601c00}
CAVE_SHA256 = hashlib.sha256(bytes(CAVE_END - CAVE_ZERO_FROM)).hexdigest()
SLOT_UNITS = 0x1f                   # ENCConvertStringUtf8ToUnicode dstlen used by the store routine
SLOT_BYTES = 0x40

CONVERT16_C = r'''
typedef unsigned char u8;
typedef unsigned int u32;

extern const u8 mc_table[];

/* Translate the fixed server specialty vocabulary in place, by code, fail-safe per slot.
   A skill slot is 64 bytes of UTF-16BE: the parser stores each name with
   ENCConvertStringUtf8ToUnicode (<= 31 units + NUL) and tests presence by the first unit. */
int mc_convert(u8 *obj){
    const u8 *t = mc_table;
    u32 n = ((u32)t[0]<<24)|((u32)t[1]<<16)|((u32)t[2]<<8)|t[3];
    u32 e, i;
    t += 4;
    for (e = 0u; e < n; e++){
        u32 code = t[0], el = t[1], kl = t[2];      /* el: English chars, kl: Korean units */
        const u8 *en = t + 3;                       /* ASCII */
        const u8 *ko = t + 3 + el;                  /* UTF-16BE, 2*kl bytes */
        t = t + 3u + el + 2u * kl;
        if (code < 1u || code > 254u) continue;
        u8 *slot = obj + 0x801cu + code * 0x40u;
        if (slot[0] == 0u && slot[1] == 0u) continue;        /* skill not supplied by the server */
        int ok = 1;
        for (i = 0u; i < el; i++){
            if (slot[2u * i] != 0u || slot[2u * i + 1u] != en[i]){ ok = 0; break; }
        }
        if (ok && (slot[2u * el] != 0u || slot[2u * el + 1u] != 0u)) ok = 0;  /* must end there */
        if (!ok) continue;                                    /* unexpected text -> leave as supplied */
        for (i = 0u; i < 0x40u; i++) slot[i] = 0u;
        for (i = 0u; i < 2u * kl; i++) slot[i] = ko[i];       /* kl <= 30, asserted at build */
    }
    return 0;
}
'''


def build_table16(mapping):
    """u32 count, then per entry u8 code, u8 en_chars, u8 ko_units, ASCII English, UTF-16BE Korean."""
    items = sorted(mapping.items())
    blob = bytearray(struct.pack('>I', len(items)))
    rows = []
    for code, (english, korean) in items:
        en = english.encode('ascii')
        if any(ord(ch) > 0xffff for ch in korean):
            raise ValueError(f'Korean name needs surrogates for code {code}: {korean!r}')
        ko = korean.encode('utf-16-be')
        units = len(ko) // 2
        if not 1 <= code <= 254 or not en or len(en) > SLOT_UNITS or not 1 <= units <= SLOT_UNITS - 1:
            raise ValueError(f'Specialty name exceeds slot for code {code}: {english!r}->{korean!r}')
        blob += struct.pack('>BBB', code, len(en), units) + en + ko
        rows.append(dict(code=code, english=english, korean=korean, en_chars=len(en), ko_units=units))
    return bytes(blob), rows


def _link(convert_c, base, table, tag):
    """Compile stub + converter at ``base``, append ``table``; return (blob, symbols, code_len)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / 'convert.c').write_text(convert_c, encoding='ascii')
        (tmp / 'stub.s').write_text(STUB_S, encoding='ascii')
        (tmp / 'link.ld').write_text(
            'SECTIONS {\n'
            f'  . = {base:#x};\n'
            '  .all : {\n'
            '    stub.o(.text .text.*)\n'
            '    *(.text .text.*)\n'
            '    *(.rodata .rodata.* .sdata2 .sdata2.*)\n'
            '    . = ALIGN(4);\n'
            '    mc_table = .;\n'
            '  }\n'
            '}\n', encoding='ascii')
        _run([GCC, *GCC_FLAGS, '-c', 'convert.c', '-o', 'convert.o'], cwd=tmp)
        _run([GCC, '-c', '-Wa,-mregnames,-mgekko', 'stub.s', '-o', 'stub.o'], cwd=tmp)
        libgcc = _run([GCC, *GCC_FLAGS, '-print-libgcc-file-name']).strip()
        _run([LD, '-T', 'link.ld', f'--defsym=mc_parse={ADDITION_PARSE:#x}',
              '-o', 'blob.elf', 'stub.o', 'convert.o', libgcc], cwd=tmp)
        syms = {}
        for line in _run([NM, 'blob.elf'], cwd=tmp).splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        if syms.get('mc_stub') != base:
            raise ValueError(f'{tag}: mc_stub not at base: {syms.get("mc_stub")}')
        und = [p.split()[-1] for p in _run([NM, '-u', 'blob.elf'], cwd=tmp).splitlines() if p.strip()]
        if und:
            raise ValueError(f'{tag}: unresolved symbols in hook: {und}')
        _run([OBJCOPY, '-O', 'binary', '-j', '.all', 'blob.elf', 'blob.bin'], cwd=tmp)
        code = (tmp / 'blob.bin').read_bytes()
    code_len = syms['mc_table'] - base
    code = code[:code_len].ljust(code_len, b'\0')
    return code + table, syms, code_len


def build_cave_blob(table):
    """Stub + UTF-16 converter linked at CAVE_VA, followed by the table; must fit the cave."""
    blob, syms, code_len = _link(CONVERT16_C, CAVE_VA, table, 'cave')
    if len(blob) > CAVE_END - CAVE_VA:
        raise ValueError(f'Runtime blob {len(blob)} bytes exceeds the {CAVE_END - CAVE_VA}-byte cave')
    record = dict(cave_va=hex(CAVE_VA), cave_end=hex(CAVE_END), cave_bytes=CAVE_END - CAVE_VA,
                  mc_stub=hex(syms['mc_stub']), mc_convert=hex(syms['mc_convert']),
                  mc_table=hex(syms['mc_table']), code_bytes=code_len, table_bytes=len(table),
                  blob_bytes=len(blob), blob_end=hex(CAVE_VA + len(blob)),
                  blob_sha256=hashlib.sha256(blob).hexdigest())
    return blob, record


def cave_references(dol, start=CAVE_ZERO_FROM, end=CAVE_END):
    """Every place that branches to, points at or builds an address inside [start, end)."""
    hits = []
    for index, off, va, size in sections(dol):
        if not off or off + size > len(dol):
            continue
        words = struct.unpack_from(f'>{size // 4}I', dol, off)
        for j, w in enumerate(words):
            here = va + 4 * j
            if start <= w < end:
                hits.append(('word', hex(here)))
            if index >= 7:
                continue
            op = w >> 26
            if op in (16, 18):
                mask, sign = (0xfffc, 0x8000) if op == 16 else (0x3fffffc, 0x2000000)
                d = w & mask
                d = d - 2 * sign if d & sign else d
                target = d if w & 2 else here + d
                if start <= target < end:
                    hits.append(('branch', hex(here)))
            if op == 15 and (w >> 16 & 31) == 0:                 # lis rD,hi
                reg, hi = w >> 21 & 31, (w & 0xffff) << 16
                for v in words[j + 1:j + 12]:
                    vop, vrt, vra, lo = v >> 26, v >> 21 & 31, v >> 16 & 31, v & 0xffff
                    if vra == reg and (vop == 14 or 32 <= vop <= 55):  # addi / D-form load-store
                        target = (hi + (lo - 0x10000 if lo & 0x8000 else lo)) & 0xffffffff
                        if start <= target < end:
                            hits.append(('lis+lo', hex(here)))
                    if vop == 24 and vrt == reg and start <= (hi | lo) < end:   # ori rA,rS: source rS
                        hits.append(('lis+ori', hex(here)))
                    if vop in (14, 15, 32, 34, 40, 42, 46) and vrt == reg:
                        break                                      # reg overwritten
    return hits


def verify_cave(dol):
    """The cave is the empty TRK vector-slot run: zero, bounded by the stubs, referenced by nothing."""
    text0 = next((s for s in sections(dol) if s[0] == 0), None)
    if text0 is None or not (text0[2] <= CAVE_ZERO_FROM and CAVE_END + 0x34 <= text0[2] + text0[3]):
        raise ValueError('Mii Contest cave is not inside text0')
    banner = to_file(dol, TRK_TABLE, len(TRK_BANNER))
    if dol[banner:banner + len(TRK_BANNER)] != TRK_BANNER:
        raise ValueError('MetroTRK vector table not found at the pinned address')
    for va, word in CAVE_BOUNDS.items():
        if _word(dol, va) != word:
            raise ValueError(f'TRK vector stub differs at {va:#x}')
    at = to_file(dol, CAVE_ZERO_FROM, CAVE_END - CAVE_ZERO_FROM)
    if hashlib.sha256(dol[at:at + CAVE_END - CAVE_ZERO_FROM]).hexdigest() != CAVE_SHA256:
        raise ValueError('Mii Contest cave is not empty')
    hits = cave_references(dol)
    if hits:
        raise ValueError(f'Mii Contest cave is referenced: {hits[:4]}')


def dol_layout(dol):
    """Header facts the boot path reads: sections, image bounds, bss, entry, file length."""
    live = sections(dol)
    bss, bss_size, entry = struct.unpack_from('>III', dol, 0xd8)
    return dict(section_count=len(live), sections=[(i, o, a, s) for i, o, a, s in live],
                image_lo=min(a for _, _, a, _ in live), image_hi=max(a + s for _, _, a, s in live),
                bss=bss, bss_size=bss_size, entry=entry, file_length=len(dol))


def patch_specialty_cave(executable, mapping):
    """build-v27+: stub + converter + table written into the in-place cave; one call-site word.

    ``executable`` may already carry the keyboard-label edits (content 1, rev>=19); those touch only
    0x8033xxxx/0x8042xxxx data slots. Returns the patched DOL whose header and length are unchanged.
    """
    verify_sites(executable)
    verify_cave(executable)
    table, rows = build_table16(mapping)
    blob, record = build_cave_blob(table)
    out = bytearray(executable)
    at = to_file(out, CAVE_VA, len(blob))
    out[at:at + len(blob)] = blob
    site = to_file(out, DISPATCH_SITE, 4)
    word = assemble('bl dest', DISPATCH_SITE, dict(dest=CAVE_VA))
    out[site:site + 4] = word
    if out[:0x100] != executable[:0x100] or len(out) != len(executable):
        raise ValueError('DOL header or length changed')
    changed = [i for i in range(len(out)) if out[i] != executable[i]]
    if any(not (at <= i < at + len(blob) or site <= i < site + 4) for i in changed):
        raise ValueError('Bytes outside the cave and the call site changed')
    layout = dol_layout(out)
    record.update(placement='in-place cave: empty MetroTRK vector slots 0x1800..0x1B00 in text0 (.init)',
                  dol_header_unchanged=True, new_dol_section=False,
                  section_count=layout['section_count'], image_lo=hex(layout['image_lo']),
                  image_hi=hex(layout['image_hi']), bss=hex(layout['bss']),
                  bss_end=hex(layout['bss'] + layout['bss_size']), file_length=layout['file_length'],
                  changed_bytes=len(changed), dispatch_site=hex(DISPATCH_SITE), dispatch_word=word.hex(),
                  reused_routine=dict(addition_parse=hex(ADDITION_PARSE)),
                  skill_table_bias=hex(SKILL_TABLE_BIAS), slot_stride=hex(SKILL_SLOT_STRIDE),
                  slot_encoding='UTF-16BE (ENCConvertStringUtf8ToUnicode, 31 units + NUL)',
                  entries=rows, vocabulary='server specialty codes 1..19 (fixed)',
                  fail_safe='per-slot: empty/unknown/mismatched English left as supplied',
                  dynamic_left_as_supplied=['contest titles', 'Mii names', 'artisan names', 'countries', 'marquee'],
                  cave_checked='zero run 0x800058bc..0x80005d88 between TRK stubs 0x1700/0x1C00; '
                               'no branch, pointer word or lis-based address targets it',
                  hardware_verified=False)
    return bytes(out), record

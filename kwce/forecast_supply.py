"""Runtime Korean conversion of WiiLink Forecast supply strings, inside the channel.

The USA Forecast executable (content 1) downloads forecast.bin / short.bin, decompresses them,
and verifies the decompressed weather buffer in one routine (0x8000c734: word@0==0, word@4==len,
country byte@20==136, language byte@24==1, CRC over [12:] vs word@8) before it is parsed. Our PC
tools convert these supply strings with ``kwce.forecast_data.localize_forecast``, but that runs
only in the launch/seed scripts, so a real console shows English conditions, UV levels and place
names. This patch moves the SAME conversion into the channel.

A small stub replaces both ``bl 0x8000c734`` call sites (state 2 = forecast complete, state 4 =
short complete; the two states share one decompressed-buffer pointer). The stub calls the real
verify routine and, only when it reports data present, calls a converter that applies
localize_forecast's in-place UTF-16 replacement rules from a table generated at build time from
``forecast_mapping()``.

Fail-safe: the converter first re-validates the full long-forecast shape -- the header fields plus
the stride-128 forecast-record table at offset 32 that the shorter short.bin buffer does not have
-- and every referenced string pointer in a validation pass. On ANY unexpected shape it leaves the
buffer untouched, so the short buffer (and any malformed download) is never edited and only the
long forecast buffer is converted, exactly as localize_forecast does on the PC side. Because every
Korean replacement is <= its English source in UTF-16 bytes (asserted when the table is built), a
matched replacement can never overflow its slot, so the only runtime abort is a shape error --
true all-or-nothing. The reused CRC routine (0x80067d44, byte-identical to zlib.crc32) recomputes
word@8 after edits.

Hand-encoded against the pinned original content 1; every replaced word and every reused routine
entry is verified before writing (cf. kwce/wiispeak_wiimmfi.py, kwce/kirbytv_dol.py). Hardware is
not verified; see docs/channels/forecast.md.
"""
import hashlib
import struct
import subprocess
import tempfile
from pathlib import Path
from .toolchain import tool

from .ppc_patch import BIN, add_text_section, assemble, sections, to_file

# Pinned original USA Forecast content 1 (uncompressed main DOL).
ORIGINAL_DOL_SHA256 = '8420bca668f873381e3bf3e3e8589ecdbfd8761ca64237cac3a42cad83b3138c'
CRC32 = 0x80067d44        # u32 crc32(const void* r3, u32 len r4) -> r3; reflected, == zlib.crc32
VERIFY = 0x8000c734       # verify(buf r3, len r4, ...) -> nonzero when the buffer holds valid data
# Both call sites hold `bl VERIFY` (link bit set); replaced with `bl fc_stub`.
HOOK_SITES = {0x8000aee0: 0x48001855, 0x8000b080: 0x480016b5}
# Unchanged words the hook depends on: the arg load before the call, and the test+branch after it,
# plus the reused routine entries. None are touched by the other forecast executable patches.
CONTEXT = {
    0x8000aedc: 0x80fd002c, 0x8000aee4: 0x2c030000, 0x8000aee8: 0x4182004c,
    0x8000b07c: 0x80fd002c, 0x8000b084: 0x2c030000, 0x8000b088: 0x4182004c,
    VERIFY: 0x9421ff70, CRC32: 0x2c040000,
}

# Arena reservation (v105). v104 placed the section at 0x80334000, which fell inside the small-data
# window (r13=0x80337540 / r2=0x80339900) and under the stack base (0x803437A8): the game's constant
# SDA-relative global accesses hit the table, so a corrupted pointer drove the boot memmove to
# 0x1f810000 (crash). Instead, place the section at the TOP of the MEM1 arena and lower OSInit's
# ArenaHi by exactly the reservation so the heap can never allocate over it. OSInit sets
# ArenaHi=0x81700000 via `lis r3,0x8170; addi r3,r3,0; bl OSSetArenaHi` at 0x800e40bc..0x800e40c4
# (default path; the devkit-config override at 0x800e40a4 is inactive on retail/Dolphin, globals 0).
# Rewriting the addi immediate to -RESERVE makes ArenaHi = 0x81700000 - RESERVE = SECTION_VA.
ARENA_HI_DEFAULT = 0x81700000
ARENA_RESERVE = 0x7000                       # 28672 B reserved at the arena top (blob must fit)
SECTION_VA = ARENA_HI_DEFAULT - ARENA_RESERVE # 0x816f9000: above SDA/SDA2/stack, below old ArenaHi
ARENA_HI_SITE = 0x800e40c0                    # addi r3,r3,0  ->  addi r3,r3,-RESERVE
ARENA_HI_ORIG = 0x38630000
ARENA_HI_NEW = (14 << 26) | (3 << 21) | (3 << 16) | ((-ARENA_RESERVE) & 0xffff)  # addi r3,r3,-0x7000
ARENA_HI_CONTEXT = {0x800e40bc: 0x3c608170, 0x800e40c4: 0x48001289}  # lis r3,0x8170 ; bl OSSetArenaHi

# localize_forecast string-pointer tables: (count_at, offset_at, stride, fields).
DESCRIPTORS = ((48, 52, 8, (4,)), (56, 60, 8, (4,)), (80, 84, 24, (4, 8, 12)))

CONVERT_C = r'''
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;

extern u32 fc_crc32(const void *p, u32 n);
extern const u8 fc_table[];

static u32 rd32(const u8 *p){ return ((u32)p[0]<<24)|((u32)p[1]<<16)|((u32)p[2]<<8)|p[3]; }

int fc_convert(u8 *buf, u32 len){
    static const u16 D[3][7] = {
        {48u,52u,8u,1u,4u,0u,0u},
        {56u,60u,8u,1u,4u,0u,0u},
        {80u,84u,24u,3u,4u,8u,12u},
    };
    u32 d, i, f, count, offset, stride, pos, end, rec, e, n, sl, dl, k, j, cnt32, off32;
    const u8 *t, *src, *dst;
    int modified;
    if (len < 88u || len > 0x400000u) return 0;
    if (rd32(buf+0) != 0u) return 0;
    if (rd32(buf+4) != len) return 0;
    if (buf[20] != 136u) return 0;
    if (buf[24] != 1u) return 0;
    cnt32 = rd32(buf+32); off32 = rd32(buf+36);         /* long-forecast discriminator */
    if (cnt32 < 1u || cnt32 > 10000u) return 0;
    if (off32 < 88u || off32 + cnt32*128u > len) return 0;
    /* PASS 1: validate every referenced string pointer; any shape error -> leave untouched */
    for (d=0u; d<3u; d++){
        count = rd32(buf + D[d][0]); offset = rd32(buf + D[d][1]); stride = D[d][2];
        if (count==0u && offset==0u) continue;
        if (count > 10000u) return 0;
        if (offset < 88u || offset + count*stride > len) return 0;
        for (i=0u; i<count; i++){
            rec = offset + i*stride;
            for (f=0u; f<(u32)D[d][3]; f++){
                pos = rd32(buf + rec + D[d][4u+f]);
                if (pos==0u) continue;
                if (pos < 88u || (pos & 1u) || pos >= len) return 0;
                end = pos;
                while (end+2u <= len && !(buf[end]==0u && buf[end+1u]==0u)){
                    end += 2u;
                    if (end - pos > 4096u) return 0;
                }
                if (end+2u > len) return 0;
            }
        }
    }
    /* PASS 2: apply the table replacements in place */
    modified = 0;
    for (d=0u; d<3u; d++){
        count = rd32(buf + D[d][0]); offset = rd32(buf + D[d][1]); stride = D[d][2];
        if (count==0u && offset==0u) continue;
        for (i=0u; i<count; i++){
            rec = offset + i*stride;
            for (f=0u; f<(u32)D[d][3]; f++){
                pos = rd32(buf + rec + D[d][4u+f]);
                if (pos==0u) continue;
                end = pos;
                while (end+2u <= len && !(buf[end]==0u && buf[end+1u]==0u)) end += 2u;
                n = rd32(fc_table); t = fc_table + 4;
                for (e=0u; e<n; e++){
                    sl = ((u32)t[0]<<8)|t[1]; dl = ((u32)t[2]<<8)|t[3];
                    src = t + 4; dst = src + sl; t = dst + dl;
                    if (sl == end - pos){
                        for (k=0u; k<sl; k++){ if (buf[pos+k] != src[k]) break; }
                        if (k == sl){
                            for (j=0u; j<dl; j++) buf[pos+j] = dst[j];
                            for (j=dl; j<sl; j++) buf[pos+j] = 0u;
                            modified++;
                            break;
                        }
                    }
                }
            }
        }
    }
    if (modified){
        u32 c = fc_crc32(buf+12, len-12);
        buf[8]=(u8)(c>>24); buf[9]=(u8)(c>>16); buf[10]=(u8)(c>>8); buf[11]=(u8)c;
    }
    return modified;
}
'''

# The hook stub: preserve the verify args, call the real verify, and on a non-zero result (data
# present) run the converter on the same buffer before it is parsed. fc_stub is the first byte of
# the section, so the two call sites branch to SECTION_VA.
STUB_S = r'''
.text
.globl fc_stub
fc_stub:
  mflr   r0
  stwu   r1,-0x20(r1)
  stw    r0,0x24(r1)
  stw    r3,0x08(r1)
  stw    r4,0x0c(r1)
  bl     fc_verify
  cmpwi  r3,0
  beq    1f
  stw    r3,0x10(r1)
  lwz    r3,0x08(r1)
  lwz    r4,0x0c(r1)
  bl     fc_convert
  lwz    r3,0x10(r1)
1:
  lwz    r0,0x24(r1)
  addi   r1,r1,0x20
  mtlr   r0
  blr
'''

GCC = tool('powerpc-eabi-gcc.exe')
AS = tool('powerpc-eabi-as.exe')
LD = tool('powerpc-eabi-ld.exe')
OBJCOPY = tool('powerpc-eabi-objcopy.exe')
NM = tool('powerpc-eabi-nm.exe')
GCC_FLAGS = ['-mcpu=750', '-meabi', '-mbig-endian', '-Os', '-ffreestanding', '-fno-builtin',
             '-fno-tree-loop-distribute-patterns', '-fno-pic', '-msdata=none', '-G0',
             '-ffixed-r2', '-ffixed-r13', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
             '-fomit-frame-pointer']


def build_table(mapping):
    """UTF-16-BE edit table: u32 count, then per entry u16 src_len,u16 dst_len,src,dst."""
    items = sorted(mapping.items())
    blob = bytearray(struct.pack('>I', len(items)))
    for english, korean in items:
        src = english.encode('utf-16-be')
        dst = korean.encode('utf-16-be')
        if len(dst) > len(src):
            raise ValueError(f'Korean overlay exceeds original slot: {english!r} -> {korean!r}')
        blob += struct.pack('>HH', len(src), len(dst)) + src + dst
    return bytes(blob), len(items)


def long_shape_ok(buf, length):
    """Fail-safe gate the compiled converter applies before touching the buffer.

    Accepts only the long forecast structure: header identity plus the stride-128 forecast-record
    table at offset 32 that the shorter short.bin buffer does not carry.
    """
    if length < 88 or length > 0x400000:
        return False
    if struct.unpack_from('>I', buf, 0)[0] != 0 or struct.unpack_from('>I', buf, 4)[0] != length:
        return False
    if buf[20] != 136 or buf[24] != 1:
        return False
    count = struct.unpack_from('>I', buf, 32)[0]
    offset = struct.unpack_from('>I', buf, 36)[0]
    if not (1 <= count <= 10000) or offset < 88 or offset + count * 128 > length:
        return False
    return True


def apply_supply_reference(data, mapping):
    """Pure-Python model of the compiled hook (the spec it mirrors).

    Applies localize_forecast's in-place UTF-16 replacement rules to the decompressed weather
    buffer with a validate-then-apply fail-safe, and recomputes word@8 (CRC over [12:]) only when
    something changed. Returns (new_bytes, modified). On any unexpected shape it returns the input
    unchanged, matching the runtime fail-safe (where localize_forecast would instead raise).
    """
    import zlib
    buf = bytearray(data)
    length = len(buf)
    lookup = {en.encode('utf-16-be'): ko.encode('utf-16-be') for en, ko in mapping.items()}
    if not long_shape_ok(buf, length):
        return bytes(data), 0
    for count_at, offset_at, stride, fields in DESCRIPTORS:         # PASS 1: validate
        count = struct.unpack_from('>I', buf, count_at)[0]
        offset = struct.unpack_from('>I', buf, offset_at)[0]
        if count == 0 and offset == 0:
            continue
        if count > 10000 or offset < 88 or offset + count * stride > length:
            return bytes(data), 0
        for i in range(count):
            rec = offset + i * stride
            for f in fields:
                pos = struct.unpack_from('>I', buf, rec + f)[0]
                if pos == 0:
                    continue
                if pos < 88 or pos % 2 or pos >= length:
                    return bytes(data), 0
                end = pos
                while end + 2 <= length and buf[end:end + 2] != b'\0\0':
                    end += 2
                    if end - pos > 4096:
                        return bytes(data), 0
                if end + 2 > length:
                    return bytes(data), 0
    modified = 0
    for count_at, offset_at, stride, fields in DESCRIPTORS:         # PASS 2: apply
        count = struct.unpack_from('>I', buf, count_at)[0]
        offset = struct.unpack_from('>I', buf, offset_at)[0]
        if count == 0 and offset == 0:
            continue
        for i in range(count):
            rec = offset + i * stride
            for f in fields:
                pos = struct.unpack_from('>I', buf, rec + f)[0]
                if pos == 0:
                    continue
                end = pos
                while end + 2 <= length and buf[end:end + 2] != b'\0\0':
                    end += 2
                dst = lookup.get(bytes(buf[pos:end]))
                if dst is not None:
                    buf[pos:pos + len(dst)] = dst
                    for j in range(pos + len(dst), end):
                        buf[j] = 0
                    modified += 1
    if modified:
        struct.pack_into('>I', buf, 8, zlib.crc32(buf[12:]) & 0xffffffff)
    return bytes(buf), modified


def _run(args, cwd=None):
    result = subprocess.run([str(args[0]), *map(str, args[1:])], cwd=cwd, capture_output=True, text=True)
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
            '    fc_table = .;\n'
            '  }\n'
            '}\n', encoding='ascii')
        _run([GCC, *GCC_FLAGS, '-c', 'convert.c', '-o', 'convert.o'], cwd=tmp)
        _run([AS, '-mregnames', '-mgekko', '-mbig', '-o', 'stub.o', 'stub.s'], cwd=tmp)
        # gcc emits out-of-line GPR save/restore helpers (_savegpr/_restgpr) from libgcc for the
        # matching multilib; include that archive so ld resolves them into our section.
        libgcc = _run([GCC, *GCC_FLAGS, '-print-libgcc-file-name']).strip()
        _run([LD, '-T', 'link.ld', f'--defsym=fc_verify={VERIFY:#x}', f'--defsym=fc_crc32={CRC32:#x}',
              '-o', 'blob.elf', 'stub.o', 'convert.o', libgcc], cwd=tmp)
        syms = {}
        for line in _run([NM, 'blob.elf'], cwd=tmp).splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        if syms.get('fc_stub') != SECTION_VA:
            raise ValueError(f'fc_stub not at section base: {syms.get("fc_stub")}')
        und = [p.split()[-1] for p in _run([NM, '-u', 'blob.elf'], cwd=tmp).splitlines() if p.strip()]
        if und:
            raise ValueError(f'Unresolved symbols in hook: {und}')
        _run([OBJCOPY, '-O', 'binary', '-j', '.all', 'blob.elf', 'blob.bin'], cwd=tmp)
        code = (tmp / 'blob.bin').read_bytes()
    table_va = syms['fc_table']
    code_len = table_va - SECTION_VA
    if code_len < len(code):                      # objcopy trimmed trailing zero padding
        code = code + bytes(code_len - len(code)) if code_len > len(code) else code
    code = code[:code_len].ljust(code_len, b'\0')
    blob = code + table
    record = dict(section_va=hex(SECTION_VA), fc_stub=hex(syms['fc_stub']),
                  fc_convert=hex(syms['fc_convert']), fc_table=hex(table_va),
                  code_bytes=code_len, table_bytes=len(table), blob_bytes=len(blob),
                  blob_sha256=hashlib.sha256(blob).hexdigest())
    return blob, record


def _word(dol, va):
    at = to_file(dol, va, 4)
    return struct.unpack_from('>I', dol, at)[0]


def verify_sites(dol):
    """Confirm the hook sites, their context and the reused routine entries are the expected words."""
    for va, word in CONTEXT.items():
        if _word(dol, va) != word:
            raise ValueError(f'Forecast load-path context differs at {va:#x}')
    for va, word in HOOK_SITES.items():
        if _word(dol, va) != word:
            raise ValueError(f'Forecast verify call site differs at {va:#x}')
    if _word(dol, ARENA_HI_SITE) != ARENA_HI_ORIG:
        raise ValueError(f'Forecast ArenaHi setter differs at {ARENA_HI_SITE:#x}')
    for va, word in ARENA_HI_CONTEXT.items():
        if _word(dol, va) != word:
            raise ValueError(f'Forecast ArenaHi context differs at {va:#x}')


def patch_executable(executable, mapping):
    """Add the supply-string converter to Forecast content 1 and redirect both verify call sites.

    ``executable`` may already carry the other forecast executable edits (error label, literals,
    time, wind); none of those touch the verified words, so the site checks still hold.
    """
    verify_sites(executable)
    table, entries = build_table(mapping)
    blob, record = build_blob(table)
    if ((len(blob) + 31) & ~31) > ARENA_RESERVE:
        raise ValueError(f'Converter blob {len(blob)} exceeds arena reservation {ARENA_RESERVE:#x}')
    out = bytearray(executable)
    slot = add_text_section(out, SECTION_VA, blob)
    hook_words = {}
    for va in HOOK_SITES:
        at = to_file(out, va, 4)
        code = assemble('bl dest', va, dict(dest=SECTION_VA))
        out[at:at + 4] = code
        hook_words[hex(va)] = code.hex()
    # Reserve the section from the arena top: ArenaHi = 0x81700000 - RESERVE = SECTION_VA.
    arena_at = to_file(out, ARENA_HI_SITE, 4)
    struct.pack_into('>I', out, arena_at, ARENA_HI_NEW)
    record.update(table_entries=entries, dol_section_slot=slot, hook_sites=hook_words,
                  reused_routines=dict(verify=hex(VERIFY), crc32=hex(CRC32)),
                  descriptors=[dict(count_at=c, offset_at=o, stride=s, fields=list(fl))
                               for c, o, s, fl in DESCRIPTORS],
                  original_content1_sha256=ORIGINAL_DOL_SHA256,
                  arena_reservation=dict(site=hex(ARENA_HI_SITE), original=f'{ARENA_HI_ORIG:08x}',
                                         patched=f'{ARENA_HI_NEW:08x}', arena_hi_before=hex(ARENA_HI_DEFAULT),
                                         arena_hi_after=hex(SECTION_VA), reserved_bytes=ARENA_RESERVE),
                  rule='localize_forecast in-place UTF-16 replacement; shape fail-safe; CRC recomputed',
                  hardware_verified=False)
    return bytes(out), record

"""Korean phone numbers for Food revision >= 10 (rc6 W-Food; workspace/private/rc6-work/L4.md section 5 'B').

Static facts in the WiiLink Demae_1_Japan DOL (stock, WiiLink and every translated Food DOL
share these code bytes, function sha256 25c1c543...):
  * 0x80024620 = phone-number check (const char *s): copy s without '-', it must start with
    '0' and not with '00'; then the length must be exactly 11 when the first three digits
    are 050/060/070/080/090 and exactly 10 otherwise (Japanese numbering plan).
    Helpers 0x800fb34c strlen, 0x80025b80 operator new[], 0x80102300 strncmp; literal pool
    0x802d6270 (+0x37 "0", +0x39 "00", +0x3c..+0x4c the five prefixes).
  * Two callers: 0x800d6e94 (scene state 0x0e, the pd.dat phone number right before the
    area request; result 0 -> message 41 '전화번호가 정확하지 않을 수 있어…', real console
    IMG_5642/5682) and 0x800340bc (shop-request screen, the shop's number, message 75).
  * A Korean mobile number 010-XXXX-XXXX (11 digits) is always refused because 010 is not in
    the list; Seoul 02-XXX-XXXX (9 digits) and 11-digit area numbers too. The Korean
    personal-data channel stores digits only (number pad), so the user cannot work around it.

Edit: five instruction words in the function tail, in place (no new section, no code cave,
DOL size and header unchanged). Both length branches meet in one unsigned range test,
(length - 9) <= 2, so 9 to 11 digits pass; the '0' / '00' rules stay. r0 is free there (the
epilogue reloads it) and nothing outside the function branches into the tail.
"""
import hashlib
import struct

from .ppc_patch import to_file

FUNC, FUNC_END = 0x80024620, 0x80024790
STOCK_SHA256 = '25c1c543eaf4c42d3ba85f5f87c2958bc8c41f55debe4c9ee8eee9b81cd586c0'
PATCHED_SHA256 = '4062f9992354906efdd23b9dad13b58ba359a4b0db1857f6867068847fccb4a9'
STRLEN, NEW_ARRAY, STRNCMP = 0x800fb34c, 0x80025b80, 0x80102300
# leaf helpers executed instruction by instruction: (start, end, sha256 of the bytes)
LEAVES = ((STRLEN, 0x800fb368, 'f58f7c8d679971405aab2dad8962c759a9df2175d01e58db592f9ae361e706db'),
          (STRNCMP, 0x80102340, '24e8c9534c8f394b64dc4a77d2b554b37dffe12239c2edb866851283eac57039'))
POOL = 0x802d62a7
POOL_BYTES = b'0\x0000\x00050\x00060\x00070\x00080\x00090\x00'
CALLERS = ((0x800d6e94, 0x4bf4d78d, 'scene state 0x0e: pd.dat phone number before the area request (message 41)'),
           (0x800340bc, 0x4bff0565, 'shop-request screen: the shop phone number (message 75)'))

# (virtual address, original word, new word, purpose)
DOL_EDITS = (
    (0x80024750, 0x281f000b, 0x381ffff7, '11-digit branch: cmplwi r31,11 -> addi r0,r31,-9'),
    (0x80024754, 0x4082001c, 0x48000010, '11-digit branch: bne fail -> b 0x80024764 (common test)'),
    (0x80024760, 0x281f000a, 0x381ffff7, '10-digit branch: cmplwi r31,10 -> addi r0,r31,-9'),
    (0x80024764, 0x4082000c, 0x28000002, 'common test: cmplwi r0,2, i.e. unsigned (length - 9) <= 2'),
    (0x8002476c, 0x48000008, 0x40810008, 'b return -> ble return (r3 = 1 from 0x80024768), else li r3,0'),
)

# Fictional numbers (L4.md section 4): (number, case, stock result, patched result)
CASES = (
    ('01012345678', 'Korean mobile 010, 11 digits', False, True),
    ('010-1234-5678', 'same number with hyphens', False, True),
    ('0100000000', 'Dolphin fictional pd.dat number, 10 digits', True, True),
    ('021234567', 'Seoul 02, 9 digits', False, True),
    ('0212345678', 'Seoul 02, 10 digits', True, True),
    ('0311234567', 'Gyeonggi 031, 10 digits', True, True),
    ('03112345678', 'Gyeonggi 031, 11 digits', False, True),
    ('07012345678', 'internet phone 070, 11 digits', True, True),
    ('01112345678', 'old mobile 011, 11 digits', False, True),
    ('0312345678', 'Tokyo 03, 10 digits', True, True),
    ('09012345678', 'Japanese mobile 090, 11 digits', True, True),
    ('15881234', 'representative number 1588, 8 digits', False, False),
    ('00112345678', 'international prefix 00', False, False),
    ('0123456', '7 digits', False, False),
    ('012345678901', '12 digits', False, False),
    ('', 'empty', False, False),
)


def _word(dol, va):
    return struct.unpack_from('>I', dol, to_file(dol, va))[0]


def _sha(dol, lo, hi):
    at = to_file(dol, lo, hi - lo)
    return hashlib.sha256(dol[at:at + hi - lo]).hexdigest()


def _check_context(dol, function_sha):
    if _sha(dol, FUNC, FUNC_END) != function_sha:
        raise ValueError('Food phone-check function differs')
    for lo, hi, digest in LEAVES:
        if _sha(dol, lo, hi) != digest:
            raise ValueError('Food phone-check helper differs at %08x' % lo)
    at = to_file(dol, POOL, len(POOL_BYTES))
    if dol[at:at + len(POOL_BYTES)] != POOL_BYTES:
        raise ValueError('Food phone prefix literals differ')
    for va, word, _ in CALLERS:
        if _word(dol, va) != word:
            raise ValueError('Food phone-check caller differs at %08x' % va)


def patch_phone_check(dol):
    """Five in-place words; refuses anything but the expected stock function and context."""
    _check_context(dol, STOCK_SHA256)
    out = bytearray(dol)
    for va, old, new, _ in DOL_EDITS:
        at = to_file(dol, va)
        if struct.unpack_from('>I', out, at)[0] != old:
            raise ValueError('Food phone-check word differs at %08x' % va)
        struct.pack_into('>I', out, at, new)
    out = bytes(out)
    diff = [i for i in range(0, len(dol), 4) if dol[i:i + 4] != out[i:i + 4]]
    if len(out) != len(dol) or out[:0x100] != dol[:0x100] or len(diff) != len(DOL_EDITS):
        raise ValueError('Food phone-check edit changed more than its words')
    _check_context(out, PATCHED_SHA256)
    results = {number: check_phone(out, number) for number, _, _, _ in CASES}
    bad = [n for n, _, _, want in CASES if results[n] != want]
    if bad:
        raise ValueError('Food phone-check simulation differs: %r' % bad)
    return out, dict(edited_words=len(DOL_EDITS), sites=['%08x' % e[0] for e in DOL_EDITS], new_sections=0,
                     dol_size_unchanged=True, function='%08x' % FUNC,
                     callers=['%08x' % c[0] for c in CALLERS],
                     rule="hyphens removed; must start with '0', not '00'; 9 to 11 digits (was 10, or 11 after 050/060/070/080/090)",
                     simulated={n or '(empty)': results[n] for n, _, _, _ in CASES})


# ---- bounded interpreter for the check function and its two leaf helpers ----

def check_phone(dol, number, max_steps=20000):
    """Run 0x80024620 on an ASCII number with the DOL's own instructions; new[] is the only stub."""
    M = 0xffffffff
    STACK_TOP, HEAP, TEXT, RETURN = 0x81700000, 0x81000000, 0x81600000, 0x80000100
    raw = number.encode('ascii') + b'\0'
    # the stack region reaches past the top: the prologue saves LR in the caller's frame (+0x24)
    regions = [(STACK_TOP - 0x1000, bytearray(0x1100)), (HEAP, bytearray(0x1000)), (TEXT, bytearray(raw))]
    code = [(FUNC, FUNC_END)] + [(lo, hi) for lo, hi, _ in LEAVES]
    heap_next = [HEAP]

    def region(a, n):
        for base, buf in regions:
            if base <= a and a + n <= base + len(buf):
                return buf, a - base
        return None, None

    def read(a, n):
        buf, at = region(a, n)
        if buf is not None:
            return int.from_bytes(buf[at:at + n], 'big')
        at = to_file(dol, a, n)
        return int.from_bytes(dol[at:at + n], 'big')

    def write(a, n, v):
        buf, at = region(a, n)
        if buf is None:
            raise ValueError('Simulated store outside the scratch regions: %08x' % a)
        buf[at:at + n] = (v & ((1 << (8 * n)) - 1)).to_bytes(n, 'big')

    def sx(v, bits):
        return v - (1 << bits) if v & (1 << (bits - 1)) else v

    r = [0] * 32; cr = [0] * 8; lr = RETURN; pc = FUNC
    r[1], r[3] = STACK_TOP, TEXT

    def compare(field, a, b):
        cr[field] = 8 if a < b else 4 if a > b else 2

    for _ in range(max_steps):
        if pc == RETURN:
            if r[3] not in (0, 1):
                raise ValueError('Phone check returned %08x' % r[3])
            return bool(r[3])
        if not any(lo <= pc < hi for lo, hi in code):
            raise ValueError('Simulation left the checked code at %08x' % pc)
        w = read(pc, 4); op = w >> 26; nxt = (pc + 4) & M
        d, a, b = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
        simm = sx(w & 0xffff, 16); uimm = w & 0xffff; base = r[a] if a else 0
        if op == 14:                                   # addi / li
            r[d] = (base + simm) & M
        elif op == 15:                                 # addis / lis
            r[d] = (base + (simm << 16)) & M
        elif op == 13:                                 # addic.
            r[d] = (r[a] + simm) & M; compare(0, sx(r[d], 32), 0)
        elif op == 10:                                 # cmpli (cmplwi)
            if d & 1:
                raise ValueError('64-bit compare at %08x' % pc)
            compare(d >> 2, r[a], uimm)
        elif op == 11:                                 # cmpi (cmpwi)
            if d & 1:
                raise ValueError('64-bit compare at %08x' % pc)
            compare(d >> 2, sx(r[a], 32), simm)
        elif op == 32:                                 # lwz
            r[d] = read((base + simm) & M, 4)
        elif op == 34:                                 # lbz
            r[d] = read((base + simm) & M, 1)
        elif op == 35:                                 # lbzu
            ea = (r[a] + simm) & M; r[d] = read(ea, 1); r[a] = ea
        elif op == 36:                                 # stw
            write((base + simm) & M, 4, r[d])
        elif op == 37:                                 # stwu
            ea = (r[a] + simm) & M; write(ea, 4, r[d]); r[a] = ea
        elif op == 38:                                 # stb
            write((base + simm) & M, 1, r[d])
        elif op == 18:                                 # b / bl
            if w & 2:
                raise ValueError('Absolute branch at %08x' % pc)
            target = (pc + sx(w & 0x03fffffc, 26)) & M
            if w & 1:
                if target == NEW_ARRAY:                # operator new[]: fresh zeroed block, volatile registers poisoned
                    size = r[3]; ptr = heap_next[0]; heap_next[0] = (ptr + size + 31) & ~31
                    if heap_next[0] > HEAP + 0x1000:
                        raise ValueError('Simulated heap exhausted')
                    for i in (0,) + tuple(range(4, 13)):
                        r[i] = 0xdeadbeef
                    for f in (0, 1, 5, 6, 7):
                        cr[f] = 0xf
                    r[3] = ptr; lr = nxt
                elif target in (STRLEN, STRNCMP):
                    lr = nxt; nxt = target
                else:
                    raise ValueError('Unexpected call from %08x to %08x' % (pc, target))
            else:
                nxt = target
        elif op == 16:                                 # bc
            if not d & 4 or w & 3:
                raise ValueError('Unexpected CTR/link/absolute branch at %08x' % pc)
            bit = (cr[a >> 2] >> (3 - (a & 3))) & 1
            if d & 0x10 or bit == (d >> 3) & 1:
                nxt = (pc + sx(w & 0xfffc, 16)) & M
        elif op == 19 and (w >> 1) & 0x3ff == 16 and d == 20 and not w & 1:
            nxt = lr                                   # blr
        elif op == 31:
            xo = (w >> 1) & 0x3ff; rc = w & 1; spr = a | (b << 5)
            if xo == 444 and not rc:                   # or / mr
                r[a] = r[d] | r[b]
            elif xo == 339 and spr == 8:               # mflr
                r[d] = lr
            elif xo == 467 and spr == 8:               # mtlr
                lr = r[d]
            elif xo == 954:                            # extsb[.]
                r[a] = sx(r[d] & 0xff, 8) & M
                if rc:
                    compare(0, sx(r[a], 32), 0)
            elif xo == 215:                            # stbx
                write((base + r[b]) & M, 1, r[d])
            elif xo == 32 and not rc:                  # cmpl (cmplw)
                if d & 1:
                    raise ValueError('64-bit compare at %08x' % pc)
                compare(d >> 2, r[a], r[b])
            elif xo == 40 and not rc:                  # subf
                r[d] = (r[b] - r[a]) & M
            else:
                raise ValueError('Unsupported instruction %08x at %08x' % (w, pc))
        else:
            raise ValueError('Unsupported instruction %08x at %08x' % (w, pc))
        pc = nxt
    raise ValueError('Simulation step limit reached')

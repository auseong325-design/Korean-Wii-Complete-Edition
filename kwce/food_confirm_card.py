"""Korean recipient card on the Food order-confirm screens + order-record strings (revision >= 12, content 1).

Static facts in the WiiLink Demae_1_Japan DOL (the translated local/hardware DOLs keep these words):
  * Two builders fill the recipient card of the final-confirm (12) and order-complete (14) screens
    from the current order object (*(0x8038a210 + 0x260)): B1 0x800984d0 (literal pool P1 0x804707ac:
    L" " +0, L"" +4, L"〒" +6, L"\\n" +0xa) and B2 0x800a5384 (pool P2 0x80470810: L"" +0, L" " +2,
    L"〒" +6, L"\\n" +0xa). B1's class also formats the delivery-time line, so B1 is most likely the
    screen-12 class and B2 screen 14 (inferred; both are edited the same way).
  * Order object fields (copied by 0x800f6c98 from pd.dat, see kwce.food_address_card): +0x14 pd+0x80
    (Korean SPD '이름', given), +0x18 pd+0x40 ('성', family), +0x30 postal code, +0x50 / +0x54 / +0x5c /
    +0x64 the address parts pd+0xe4 / +0x124 / +0x164 / +0x264, +0x58 / +0x60 / +0x68 always L"".
    Getters 0x800bb574 (+0x14) and 0x800bb57c (+0x18) are `lwz r3, off(r3); blr`.
  * Name: wcscpy(L""), wcscat(+0x14), wcscat(L" "), wcscat(+0x18) -> 'given family' ('길동 홍').
  * Address: wcscpy(L""), then wcscat of L"〒", zip, L"\\n", +0x50, +0x54, +0x58, +0x5c, +0x60, +0x64,
    +0x68 into a buffer of (len(zip) + len(L"〒") + 1 + sum(parts) + 1) wide chars: '〒12345\\n' and the
    parts run together without spaces (IMG_5700).

Edits (20 instruction words in place, no new code or section, DOL size unchanged), per builder:
  name    first getter -> +0x18, separator L" " -> L"", second getter -> +0x14  => '홍길동'
  address the eleven copy/append slots are re-pointed to: L"", zip, L"\\n", +0x50, L" ", +0x54, L" ",
          +0x5c, L" ", +0x64, +0x68  => '12345\\n서울특별시 종로구 세종대로 1 101동 202호' (no 〒), and the
          base length term `addi rX, r4, 1` -> 3 so the buffer holds the two extra spaces.
A bounded interpreter runs the four builder segments with their helper calls (getters, wcslen
0x801050d0, wcscpy 0x801050ec, wcscat 0x8010514c; the heap allocator 0x80025b80 is a recorded stub)
on the stock and the edited DOL and checks both results plus the buffer bound.

Strings (UTF-16 literals in .sdata, each rewritten inside its own extent, NUL padded):
  0x804706f8 '可' / 0x804706fc '不可' -> '가' / '불가' (shop detail 04c '배달시간 지정:' value, set by
  0x800480e4 with AllocStringBuffer(wcslen)); 0x804708c6 / 0x80470972 the two order-record reorder notes
  (L2_T_reorder1, SetString by 0x800d2010 / 0x800d2034 from pool 0x804708c4 + 2 / + 0xae, so the start
  addresses must not move); the colour tags (0x0c + 2 code units) around 予約注文 are kept.
"""
import struct

from .food_address_card import _offset, _sections, _word

R13 = 0x80478660
OBJ_GETTERS = {0x800bb574: 0x14, 0x800bb57c: 0x18}
WCSLEN, WCSCPY, WCSCAT, ALLOC = 0x801050d0, 0x801050ec, 0x8010514c, 0x80025b80
POOLS = {0x804707ac: bytes.fromhex('0020000000003012' '0000000a0000'),      # B1: L" " L"" L"〒" L"\n"
         0x80470810: bytes.fromhex('0000002000003012' '0000000a0000')}      # B2: L"" L" " L"〒" L"\n"

# (virtual address, stock word, new word, purpose)
CARD_EDITS = (
    (0x8009866c, 0x48022f09, 0x48022f11, 'B1 name: first part = family (+0x18)'),
    (0x80098680, 0x388d814c, 0x388d8150, 'B1 name: separator L" " -> L""'),
    (0x8009868c, 0x48022ef1, 0x48022ee9, 'B1 name: second part = given (+0x14)'),
    (0x8009893c, 0x3b440001, 0x3b440003, 'B1 address: buffer length +2 (three spaces, no 〒)'),
    (0x80098a20, 0x389b0006, 0x809d0030, 'B1 address slot 1: L"〒" -> postal code'),
    (0x80098a28, 0x809d0030, 0x389b000a, 'B1 address slot 2: postal code -> L"\\n"'),
    (0x80098a38, 0x389b000a, 0x809d0050, 'B1 address slot 3: L"\\n" -> part 1'),
    (0x80098a40, 0x809d0050, 0x389b0000, 'B1 address slot 4: part 1 -> L" "'),
    (0x80098a58, 0x809d0058, 0x389b0000, 'B1 address slot 6: L"" -> L" "'),
    (0x80098a70, 0x809d0060, 0x389b0000, 'B1 address slot 8: L"" -> L" "'),
    (0x800a5578, 0x48015ffd, 0x48016005, 'B2 name: first part = family (+0x18)'),
    (0x800a558c, 0x389a0002, 0x389a0000, 'B2 name: separator L" " -> L""'),
    (0x800a5598, 0x48015fe5, 0x48015fdd, 'B2 name: second part = given (+0x14)'),
    (0x800a5848, 0x3b040001, 0x3b040003, 'B2 address: buffer length +2'),
    (0x800a592c, 0x389b0006, 0x809d0030, 'B2 address slot 1: L"〒" -> postal code'),
    (0x800a5934, 0x809d0030, 0x389b000a, 'B2 address slot 2: postal code -> L"\\n"'),
    (0x800a5944, 0x389b000a, 0x809d0050, 'B2 address slot 3: L"\\n" -> part 1'),
    (0x800a594c, 0x809d0050, 0x389b0002, 'B2 address slot 4: part 1 -> L" "'),
    (0x800a5964, 0x809d0058, 0x389b0002, 'B2 address slot 6: L"" -> L" "'),
    (0x800a597c, 0x809d0060, 0x389b0002, 'B2 address slot 8: L"" -> L" "'),
)
# Unchanged words that pin the context (pool loads, wcscpy of L"", r29 = order object).
CONTEXT = ((0x80006314, 0x3da08047), (0x80006318, 0x61ad8660),     # __start: r13 = 0x80478660
           (0x8009861c, 0x83a40260), (0x800a5528, 0x83a40260),     # lwz r29, 0x260(r4)
           (0x80098a0c, 0x3b6d814c), (0x80098a14, 0x389b0004),     # B1: r27 = P1; wcscpy(L"")
           (0x800a5924, 0x3b6d81b0), (0x800a591c, 0x388d81b0),     # B2: r27 = P2; wcscpy(L"")
           (0x800bb574, 0x80630014), (0x800bb57c, 0x80630018))     # getters
SEGMENTS = dict(b1_name=(0x80098620, 0x8009869c, 27), b1_address=(0x80098914, 0x80098a94, 25),
                b2_name=(0x800a552c, 0x800a55a8, 27), b2_address=(0x800a5820, 0x800a59a0, 25))

REORDER_TAG = '\x0c'
STRING_EDITS = (
    (0x804706f8, '可', '가', '04c delivery-time designation: possible'),
    (0x804706fc, '不可', '불가', '04c delivery-time designation: not possible'),
    (0x804708c6, None, None, 'order record reorder note (reservation, colour-tagged 予約注文)'),
    (0x80470972, None, None, 'order record reorder note (same-day)'),
)
REORDER_JA_PLAIN = ('同じ商品内容で注文リストをつくり、\n注文することができます。\n1つでも前回注文した商品がなくなっている'
                    '場合は、\n注文リストはつくれません。ご了承ください。')
REORDER_KO_PLAIN = '같은 내용으로 주문 목록을 만들어\n주문할 수 있습니다.\n전에 주문한 상품이 하나라도 없으면\n주문 목록을 만들 수 없습니다.'


def _read_wide(dol, va):
    at = _offset(dol, va); out = []
    while True:
        v = struct.unpack_from('>H', dol, at)[0]
        if not v:
            return ''.join(out)
        out.append(chr(v)); at += 2


def visible_text(text):
    """Drop the channel's colour tags (0x0c + two code units of RGBA) to get the drawn characters."""
    out, i = [], 0
    while i < len(text):
        if text[i] == REORDER_TAG:
            i += 3; continue
        out.append(text[i]); i += 1
    return ''.join(out)


def reorder_korean(ja_tagged):
    """Korean reservation note keeping the stock colour tags (0x0c + two code units) around 予約注文."""
    a = ja_tagged.index(REORDER_TAG); b = ja_tagged.index(REORDER_TAG, a + 1)
    if ja_tagged[a + 3:b] != '予約注文' or not ja_tagged.startswith('同じ商品内容で注文リストをつくり、\n'):
        raise ValueError('Food reorder note layout differs')
    return ('같은 내용으로 주문 목록을 만들어\n' + ja_tagged[a:a + 3] + '예약 주문' + ja_tagged[b:b + 3]
            + '할 수 있습니다.\n전에 주문한 상품이 하나라도 없으면\n주문 목록을 만들 수 없습니다.')


def string_plan(dol):
    """[(va, stock text, Korean text, purpose)] resolved against this DOL (stock text verified)."""
    plan = []
    for va, ja, ko, why in STRING_EDITS:
        cur = _read_wide(dol, va)
        if va == 0x804708c6:
            ja, ko = cur, reorder_korean(cur)
            if len(cur) != 85:
                raise ValueError('Food reorder note length differs')
        elif va == 0x80470972:
            ja, ko = REORDER_JA_PLAIN, REORDER_KO_PLAIN
        if cur != ja:
            raise ValueError('Food order string differs at %08x' % va)
        if len(ko) > len(ja):
            raise ValueError('Food Korean string exceeds its literal at %08x' % va)
        plan.append((va, ja, ko, why))
    return plan


def patch_order_strings(dol):
    from .food_textfit import korean_metrics
    out = bytearray(dol); plan = string_plan(dol); m = korean_metrics()
    missing = sorted({c for _, _, ko, _ in plan for c in m.missing(visible_text(ko)) if ord(c) >= 0x20})
    if missing:
        raise ValueError('Food order strings use glyphs missing from wbf1: %r' % missing)
    for va, ja, ko, _ in plan:
        at = _offset(dol, va); n = 2 * len(ja)
        if dol[at + n:at + n + 2] != b'\0\0':
            raise ValueError('Food order string not terminated at %08x' % va)
        out[at:at + n] = ko.encode('utf-16-be') + bytes(n - 2 * len(ko))
    out = bytes(out)
    if any(_read_wide(out, va) != ko for va, _, ko, _ in plan) or len(out) != len(dol):
        raise ValueError('Food order string rewrite failed')
    return out, [dict(va='%08x' % va, ja_chars=len(ja), ko=ko, purpose=why) for va, ja, ko, why in plan]


def patch_confirm_card(dol):
    """Twenty in-place instruction edits; refuses anything but the expected stock words."""
    for va, word in CONTEXT:
        if _word(dol, va) != word:
            raise ValueError('Food confirm-card context word differs at %08x' % va)
    for va, raw in POOLS.items():
        at = _offset(dol, va)
        if dol[at:at + len(raw)] != raw:
            raise ValueError('Food confirm-card literal pool differs at %08x' % va)
    if simulate(dol) != stock_expectation():
        raise ValueError('Food confirm-card stock simulation differs: %r' % (simulate(dol),))
    out = bytearray(dol)
    for va, old, new, _ in CARD_EDITS:
        at = _offset(dol, va)
        if struct.unpack_from('>I', out, at)[0] != old:
            raise ValueError('Food confirm-card word differs at %08x' % va)
        struct.pack_into('>I', out, at, new)
    out = bytes(out)
    diff = [i for i in range(0, len(dol), 4) if dol[i:i + 4] != out[i:i + 4]]
    if len(out) != len(dol) or _sections(out) != _sections(dol) or len(diff) != len(CARD_EDITS):
        raise ValueError('Food confirm-card edit changed more than its words')
    sim = simulate(out)
    if sim != korean_expectation():
        raise ValueError('Food confirm-card simulation differs: %r' % (sim,))
    empty = simulate(out, parts=('서울특별시', '', '세종대로 1', ''))
    if empty['b1_address'][0] != '12345\n서울특별시  세종대로 1 ' or not all(v[1] for v in empty.values()):
        raise ValueError('Food confirm-card empty-part simulation differs: %r' % (empty,))
    return out, dict(edited_words=len(CARD_EDITS), sites=['%08x' % e[0] for e in CARD_EDITS], new_sections=0,
                     dol_size_unchanged=True, builders=['800984d0 (screen 12)', '800a5384'],
                     name_order='family+given, no separator', postal='no 〒', address='parts joined with spaces',
                     simulated=dict(input='family 홍 / given 길동 / zip 12345 / parts 서울특별시|종로구|세종대로 1|101동 202호',
                                    **{k: v[0] for k, v in sim.items()}))


SAMPLE = dict(family='홍', given='길동', zip='12345', parts=('서울특별시', '종로구', '세종대로 1', '101동 202호'))


def stock_expectation():
    s = SAMPLE; addr = '〒%s\n%s' % (s['zip'], ''.join(s['parts']))
    return dict(b1_name=('%s %s' % (s['given'], s['family']), True), b1_address=(addr, True),
                b2_name=('%s %s' % (s['given'], s['family']), True), b2_address=(addr, True))


def korean_expectation():
    s = SAMPLE; addr = '%s\n%s' % (s['zip'], ' '.join(s['parts']))
    return dict(b1_name=(s['family'] + s['given'], True), b1_address=(addr, True),
                b2_name=(s['family'] + s['given'], True), b2_address=(addr, True))


# ---- bounded interpreter (integer subset + calls into the helper leaves) ----

class _Memory:
    def __init__(self, dol):
        self.dol, self.regions = dol, {}

    def add(self, base, size):
        self.regions[base] = bytearray(size); return base

    def _region(self, a, n):
        for base, buf in self.regions.items():
            if base <= a and a + n <= base + len(buf):
                return buf, a - base
        return None, None

    def read(self, a, n):
        buf, at = self._region(a, n)
        if buf is not None:
            return int.from_bytes(buf[at:at + n], 'big')
        return int.from_bytes(self.dol[_offset(self.dol, a):_offset(self.dol, a) + n], 'big')

    def write(self, a, n, v):
        buf, at = self._region(a, n)
        if buf is None:
            raise ValueError('Simulated store outside the scratch regions: %08x' % a)
        buf[at:at + n] = (v & ((1 << (8 * n)) - 1)).to_bytes(n, 'big')

    def put_wide(self, a, text):
        raw = text.encode('utf-16-be') + b'\0\0'
        for i in range(0, len(raw), 2):
            self.write(a + i, 2, int.from_bytes(raw[i:i + 2], 'big'))

    def wide(self, a, limit=4096):
        out = []
        while len(out) < limit:
            v = self.read(a + 2 * len(out), 2)
            if not v:
                return ''.join(out)
            out.append(chr(v))
        raise ValueError('Unterminated simulated string')


def _run(dol, start, stop, regs, mem, allocs, max_steps=200000):
    M = 0xffffffff; cr = [0] * 8; pc = start; lr = [0]

    def sx(v, bits):
        return v - (1 << bits) if v & (1 << (bits - 1)) else v

    def compare(field, a, b):
        cr[field] = 8 if a < b else 4 if a > b else 2

    for _ in range(max_steps):
        if pc == stop:
            return regs
        if pc == ALLOC:                                   # heap allocator stub: fresh region, size recorded
            size = regs[3]; base = 0x81200000 + 0x1000 * len(allocs)
            if not 0 < size <= 0x1000:
                raise ValueError('Simulated allocation size %d' % size)
            mem.add(base, size); allocs.append((base, size)); regs[3] = base; pc = lr[0]; continue
        w = _word(dol, pc); op = w >> 26; nxt = pc + 4
        d, a, b = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
        simm = sx(w & 0xffff, 16); base = 0 if a == 0 else regs[a]
        if op == 14:
            regs[d] = (base + simm) & M
        elif op == 15:
            regs[d] = (base + (simm << 16)) & M
        elif op == 10:
            compare(d >> 2, regs[a], w & 0xffff)
        elif op == 11:
            compare(d >> 2, sx(regs[a], 32), simm)
        elif op == 21:
            sh, mb, me = b, (w >> 6) & 31, (w >> 1) & 31
            rot = ((regs[d] << sh) | (regs[d] >> (32 - sh))) & M if sh else regs[d]
            mask = 0
            for bit in range(32):
                if (mb <= me and mb <= bit <= me) or (mb > me and (bit >= mb or bit <= me)):
                    mask |= 1 << (31 - bit)
            regs[a] = rot & mask
            if w & 1:
                compare(0, sx(regs[a], 32), 0)
        elif op == 18:
            if w & 2:
                raise ValueError('Unexpected absolute branch at %08x' % pc)
            target = (pc + sx(w & 0x03fffffc, 26)) & M
            if w & 1:
                lr[0] = nxt
            nxt = target
        elif op == 16:
            bo, bi = d, a
            if not bo & 4 or w & 3:
                raise ValueError('Unexpected CTR/link branch at %08x' % pc)
            bit = (cr[bi >> 2] >> (3 - (bi & 3))) & 1
            if bo & 0x10 or bit == (bo >> 3) & 1:
                nxt = (pc + sx(w & 0xfffc, 16)) & M
        elif op == 19 and ((w >> 1) & 0x3ff) == 16 and d == 20 and not w & 1:
            nxt = lr[0]                                   # blr (leaf helpers only: no nested frames)
        elif op == 31:
            xo = (w >> 1) & 0x3ff
            if xo == 266:
                regs[d] = (regs[a] + regs[b]) & M
            elif xo == 444:
                regs[a] = regs[d] | regs[b]
            elif xo == 0:
                compare(d >> 2, sx(regs[a], 32), sx(regs[b], 32))
            elif xo == 32:
                compare(d >> 2, regs[a], regs[b])
            else:
                raise ValueError('Unsupported instruction %08x at %08x' % (w, pc))
        elif op == 32:
            regs[d] = mem.read((base + simm) & M, 4)
        elif op == 36:
            mem.write((base + simm) & M, 4, regs[d])
        elif op == 40:
            regs[d] = mem.read((base + simm) & M, 2)
        elif op == 41:
            ea = (regs[a] + simm) & M; regs[d] = mem.read(ea, 2); regs[a] = ea
        elif op == 44:
            mem.write((base + simm) & M, 2, regs[d])
        elif op == 45:
            ea = (regs[a] + simm) & M; mem.write(ea, 2, regs[d]); regs[a] = ea
        elif op == 52:                                    # stfs f, imm(r1): FP layout values, not modelled
            if a != 1:
                raise ValueError('Unexpected FP store at %08x' % pc)
        else:
            raise ValueError('Unsupported instruction %08x at %08x' % (w, pc))
        pc = nxt
    raise ValueError('Simulation step limit reached')


def simulate(dol, parts=None):
    """{segment: (built text, fits its allocation)} for the four builder segments."""
    s = dict(SAMPLE)
    if parts is not None:
        s['parts'] = parts
    out = {}
    for name, (start, stop, result) in SEGMENTS.items():
        mem = _Memory(dol); stack = mem.add(0x81700000 - 0x400, 0x800); obj = mem.add(0x81600000, 0x100)
        text = mem.add(0x81610000, 0x1000); allocs = []
        strings = dict(given=s['given'], family=s['family'], zip=s['zip'], p1=s['parts'][0], p2=s['parts'][1],
                       p3=s['parts'][2], p4=s['parts'][3], empty='')
        where = {}
        for i, (k, v) in enumerate(strings.items()):
            where[k] = text + 0x100 * i; mem.put_wide(where[k], v)
        for off, key in ((0x14, 'given'), (0x18, 'family'), (0x30, 'zip'), (0x50, 'p1'), (0x54, 'p2'),
                         (0x58, 'empty'), (0x5c, 'p3'), (0x60, 'empty'), (0x64, 'p4'), (0x68, 'empty')):
            mem.write(obj + off, 4, where[key])
        for off in range(0x34, 0x50, 4):                  # 'part present' fields read by the length loop
            mem.write(obj + off, 4, text + 0xf00)
        regs = [0] * 32
        regs[1], regs[2], regs[13], regs[29] = stack, 0x8047a440, R13, obj
        regs = _run(dol, start, stop, regs, mem, allocs)
        built = mem.wide(regs[result])
        cap = [size for b, size in allocs if b == regs[result]]
        out[name] = (built, bool(cap) and 2 * (len(built) + 1) <= cap[0])
    return out

"""Korean address card for Food revision >= 9 (rc3 W5): name order, postal code, reading line.

Static facts in the WiiLink Demae_1_Japan DOL (the translated local/hardware DOLs keep
these code words; only string data, endpoints and the area bridge differ):
  * Textbox table 0x802da478 = {layout index, pane name}; the init loop 0x800f4744 stores
    the TextBox pointers at scene+0x808+4*i (post00 +0x808, post01 +0x80c, nama +0x814,
    huriga +0x818, sama +0x81c, adT_09_zip-code +0x834, adT_09_user-name +0x83c,
    adTc_09_sama +0x840, adT_09_huriga +0x844).
  * The personal-data struct the screens read is pd.dat from byte 143 on: +0x40 family
    name (file 207, SPD field '성'), +0x80 given name (file 271, SPD field '이름'),
    +0xc0 postal code (file 335).
  * Main menu card 0x800f59d0: post00.SetString(zip + 0, 0, 3) and
    post01.SetString(zip + 8 bytes, 0, 4): the Japanese 'NNN-NNNN' form. A Korean
    5-digit code '00000' showed '000' + '0' over 7 boxes (lead review: 000-0 + 3 boxes).
  * Name: main card 0x800f5f34 and address screen 0x800f693c build
    given + L" " + family ('길동 홍'). The reading (furigana) lines repeat the same
    order from the KANA block, which the Korean SPD fills with the name itself.
  * Address-confirm postal line 0x800f65bc: L"〒" + zip.
  * Wide literals at 0x80470ac0 (r13 0x80478660 - 0x7ba0): L"\\n" +0, L" " +4,
    L"〒" +8, each followed by its NUL halfword (+6 and +0xa are therefore L"").

Edits: nine instruction words in place (DOL size and section table unchanged, no new
section, no new code): family first, then given, no separator ('홍길동'); post01 starts
at zip index 3 and shows 2 digits; the address-screen line drops 〒.
Content 2 (Dtest/DtestTitle.arc): 01_win_ad_post.tpl redrawn as five boxes (CI4, same
header and palette), 01_T_win_post01 moved 4 units left so the boxes are evenly spaced,
and the reading panes 01_T_win_huriga / adT_09_huriga hidden (visible flag cleared): the
Korean SPD stores reading == name, so the full name is shown once. The '님' honorific
is the layout text from revision 4 on (adTc_09_sama, 01_Tc_win_sama).
"""
import struct

from .channels import ChannelArchive, layout_sections, rebuild_layout, sha256

R13 = 0x80478660
LITERALS = 0x80470ac0            # L"\n", L" ", L"〒" with NUL halfwords
PD_BASE_IN_FILE = 143            # pd.dat byte that the in-memory struct starts at
FAMILY, GIVEN, ZIP = 0x40, 0x80, 0xc0

# (virtual address, original word, new word, purpose)
DOL_EDITS = (
    (0x800f5a18, 0x389e00c8, 0x389e00c6, 'main card post01: zip index 4 -> 3 (no hyphen in a Korean code)'),
    (0x800f5a20, 0x38c00004, 0x38c00002, 'main card post01: 4 -> 2 digits'),
    (0x800f5fac, 0xa0030080, 0xa0030040, 'main card name: first part = family name (+0x40)'),
    (0x800f5fe0, 0x38a30004, 0x38a30006, 'main card name: separator L" " -> L"" (its NUL)'),
    (0x800f6088, 0xa0030040, 0xa0030080, 'main card name: second part = given name (+0x80)'),
    (0x800f65c8, 0x38c60008, 0x38c6000a, 'address screen postal line: L"〒" -> L"" (its NUL)'),
    (0x800f6984, 0xa0030080, 0xa0030040, 'address screen name: first part = family name'),
    (0x800f69b8, 0x38830004, 0x38830006, 'address screen name: separator L" " -> L""'),
    (0x800f6a60, 0xa0030040, 0xa0030080, 'address screen name: second part = given name'),
)
# Unchanged words that pin the context of the edits (r13 literal loads, post00 arguments).
CONTEXT = ((0x80006314, 0x3da08047), (0x80006318, 0x61ad8660),          # __start: r13 = 0x80478660
           (0x800f5fd8, 0x386d8460), (0x800f69b0, 0x386d8460),          # addi r3, r13, -0x7ba0
           (0x800f65bc, 0x38cd8460),                                    # addi r6, r13, -0x7ba0
           (0x800f59d8, 0x38c00003), (0x800f5a0c, 0x388400c0))          # post00: len 3, zip + 0


def _sections(dol):
    offs = struct.unpack_from('>18I', dol, 0); addrs = struct.unpack_from('>18I', dol, 0x48)
    sizes = struct.unpack_from('>18I', dol, 0x90)
    return [(o, a, s) for o, a, s in zip(offs, addrs, sizes) if s]


def _offset(dol, va):
    for o, a, s in _sections(dol):
        if a <= va < a + s:
            return o + va - a
    raise ValueError('Address outside the DOL: %08x' % va)


def _word(dol, va):
    return struct.unpack_from('>I', dol, _offset(dol, va))[0]


def _check_literals(dol):
    at = _offset(dol, LITERALS)
    if dol[at:at + 12] != bytes.fromhex('000a0000002000003012' '0000'):
        raise ValueError('Food name/postal wide literals differ')


def patch_address_card(dol):
    """Nine in-place instruction edits; refuses anything but the expected stock words."""
    for va, word in CONTEXT:
        if _word(dol, va) != word:
            raise ValueError('Food address-card context word differs at %08x' % va)
    _check_literals(dol)
    out = bytearray(dol)
    for va, old, new, _ in DOL_EDITS:
        at = _offset(dol, va)
        if struct.unpack_from('>I', out, at)[0] != old:
            raise ValueError('Food address-card word differs at %08x' % va)
        struct.pack_into('>I', out, at, new)
    out = bytes(out)
    diff = [i for i in range(0, len(dol), 4) if dol[i:i + 4] != out[i:i + 4]]
    if len(out) != len(dol) or _sections(out) != _sections(dol) or len(diff) != len(DOL_EDITS):
        raise ValueError('Food address-card edit changed more than its words')
    sim = simulate(out, '홍', '길동', '12345')
    want = dict(main_name='홍길동', address_name='홍길동', address_postal='12345', main_postal=['123', '45'])
    if sim != want:
        raise ValueError('Food address-card simulation differs: %r' % (sim,))
    return out, dict(edited_words=len(DOL_EDITS), sites=['%08x' % e[0] for e in DOL_EDITS], new_sections=0,
                     dol_size_unchanged=True, name_order='family+given, no separator',
                     postal='main card 3+2 digits from a 5-digit code; address line without 〒',
                     simulated=dict(input='family 홍 / given 길동 / zip 12345', **sim))


# ---- bounded interpreter for the three string builders (the subset they use) ----

class _Memory:
    def __init__(self, dol, regions):
        self.dol, self.regions = dol, regions      # regions: {base: bytearray} (writable)

    def _region(self, a, n):
        for base, buf in self.regions.items():
            if base <= a and a + n <= base + len(buf):
                return buf, a - base
        return None, None

    def read(self, a, n):
        buf, at = self._region(a, n)
        if buf is not None:
            return int.from_bytes(buf[at:at + n], 'big')
        at = _offset(self.dol, a)
        return int.from_bytes(self.dol[at:at + n], 'big')

    def write(self, a, n, v):
        buf, at = self._region(a, n)
        if buf is None:
            raise ValueError('Simulated store outside the scratch regions: %08x' % a)
        buf[at:at + n] = (v & ((1 << (8 * n)) - 1)).to_bytes(n, 'big')


def _run(dol, start, stop, regs, mem, max_steps=50000):
    M = 0xffffffff; cr = [0] * 8; pc = start

    def sx(v, bits):
        return v - (1 << bits) if v & (1 << (bits - 1)) else v

    def compare(field, a, b):
        cr[field] = 8 if a < b else 4 if a > b else 2

    for _ in range(max_steps):
        if pc == stop:
            return regs
        w = _word(dol, pc); op = w >> 26; nxt = pc + 4
        d, a, b = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
        simm = sx(w & 0xffff, 16); base = 0 if a == 0 else regs[a]
        if op == 14:
            regs[d] = (base + simm) & M
        elif op == 15:
            regs[d] = (base + (simm << 16)) & M
        elif op == 8:
            regs[d] = (simm - regs[a]) & M
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
            if w & 3:
                raise ValueError('Unexpected call/absolute branch at %08x' % pc)
            nxt = (pc + sx(w & 0x03fffffc, 26)) & M
        elif op == 16:
            bo, bi = d, a
            if not bo & 4 or w & 3:
                raise ValueError('Unexpected CTR/link branch at %08x' % pc)
            bit = (cr[bi >> 2] >> (3 - (bi & 3))) & 1
            if bo & 0x10 or bit == (bo >> 3) & 1:
                nxt = (pc + sx(w & 0xfffc, 16)) & M
        elif op == 31:
            xo = (w >> 1) & 0x3ff
            if xo == 266:
                regs[d] = (regs[a] + regs[b]) & M
            elif xo == 279:
                regs[d] = mem.read((base + regs[b]) & M, 2)
            elif xo == 311:
                ea = (regs[a] + regs[b]) & M; regs[d] = mem.read(ea, 2); regs[a] = ea
            elif xo == 407:
                mem.write((base + regs[b]) & M, 2, regs[d])
            elif xo == 444:
                regs[a] = regs[d] | regs[b]
            elif xo == 32:
                compare(d >> 2, regs[a], regs[b])
            else:
                raise ValueError('Unsupported instruction %08x at %08x' % (w, pc))
        elif op == 36:
            mem.write((base + simm) & M, 4, regs[d])
        elif op == 40:
            regs[d] = mem.read((base + simm) & M, 2)
        elif op == 44:
            mem.write((base + simm) & M, 2, regs[d])
        else:
            raise ValueError('Unsupported instruction %08x at %08x' % (w, pc))
        pc = nxt
    raise ValueError('Simulation step limit reached')


def _wide(buf, at):
    out = []
    while True:
        v = int.from_bytes(buf[at:at + 2], 'big')
        if not v:
            return ''.join(out)
        out.append(chr(v)); at += 2


def simulate(dol, family, given, zip_code):
    """What the main card and the address-confirm screen build from a pd struct."""
    STACK, PD = 0x81700000, 0x81600000
    pd = bytearray(0x400)
    for off, text in ((FAMILY, family), (GIVEN, given), (ZIP, zip_code)):
        raw = text.encode('utf-16-be'); pd[off:off + len(raw)] = raw
    out = {}
    # main card name builder (from after its prologue to the SetString call)
    stack = bytearray(0x200); regs = [0] * 32
    regs[1], regs[2], regs[13], regs[4], regs[5], regs[6] = STACK, 0x8047a440, R13, PD, 0x81500000, 0x81500100
    _run(dol, 0x800f5f48, 0x800f60b4, regs, _Memory(dol, {STACK: stack, PD: pd}))
    out['main_name'] = _wide(stack, 0x58)
    # address screen: postal line, then the name
    stack = bytearray(0x200); regs = [0] * 32
    regs[1], regs[2], regs[13], regs[3], regs[4], regs[5] = STACK, 0x8047a440, R13, 0x81500000, PD, 0x81500200
    _run(dol, 0x800f65bc, 0x800f66c0, regs, _Memory(dol, {STACK: stack, PD: pd}))
    out['address_postal'] = _wide(stack, 0x28)
    stack = bytearray(0x200); regs = [0] * 32
    regs[1], regs[2], regs[13], regs[30] = STACK, 0x8047a440, R13, PD
    _run(dol, 0x800f693c, 0x800f6a8c, regs, _Memory(dol, {STACK: stack, PD: pd}))
    out['address_name'] = _wide(stack, 0x28)
    # main card postal boxes: SetString(pd + imm, 0, n) arguments decoded from the words
    z = zip_code + '\0' * 8
    parts = []
    for addi, li in ((0x800f5a0c, 0x800f59d8), (0x800f5a18, 0x800f5a20)):
        start = ((_word(dol, addi) & 0xffff) - ZIP) // 2; n = _word(dol, li) & 0xffff
        parts.append(z[start:start + n].split('\0')[0])
    out['main_postal'] = parts
    return out


# ---- content 2: five postal boxes, evenly spaced digits, reading lines hidden ----

TITLE_ARC = 'Dtest/DtestTitle.arc'
POST_TPL = 'Title/timg/01_win_ad_post.tpl'
MAIN_LAYOUT = 'Title/blyt/01_m_layout.brlyt'
ADDRESS_LAYOUT = 'Title/blyt/address_layout.brlyt'
POST01, POST01_X, POST01_NEW_X = '01_T_win_post01', -133.0, -137.0
HIDDEN = {MAIN_LAYOUT: ('01_T_win_huriga',), ADDRESS_LAYOUT: ('adT_09_huriga',)}
BOXES, PITCH, BOX, EDGE = 5, 19, 18, 2      # stock boxes: 18 px, 1 px gap, 2 px border, rows 1-22
BORDER_INDEX, PAPER_INDEX = 0, 2            # stock palette: 0 dark pink (first group), 2 white


def _ci4_layout(raw):
    from .channel_texture import texture_records
    recs = texture_records(raw)
    if len(recs) != 1 or recs[0]['format'] != 8 or (recs[0]['width'], recs[0]['height']) != (136, 24):
        raise ValueError('Expected the 136x24 CI4 postal-box texture')
    return recs[0]


def _indices(raw):
    r = _ci4_layout(raw); w, h, pos = r['width'], r['height'], r['offset']; grid = [[0] * w for _ in range(h)]
    for by in range(0, h, 8):
        for bx in range(0, w, 8):
            for y in range(8):
                for x in range(8):
                    v = raw[pos + y * 4 + x // 2]
                    grid[by + y][bx + x] = v >> 4 if x % 2 == 0 else v & 15
            pos += 32
    return grid


def _write_indices(raw, grid):
    r = _ci4_layout(raw); w, h, pos = r['width'], r['height'], r['offset']; out = bytearray(raw)
    for by in range(0, h, 8):
        for bx in range(0, w, 8):
            for y in range(8):
                for x in range(0, 8, 2):
                    out[pos + y * 4 + x // 2] = (grid[by + y][bx + x] << 4) | grid[by + y][bx + x + 1]
            pos += 32
    return bytes(out)


def five_box_grid(w=136, h=24):
    grid = [[PAPER_INDEX] * w for _ in range(h)]
    for i in range(BOXES):
        x0 = i * PITCH
        for y in range(1, h - 1):
            for x in range(x0, x0 + BOX):
                if y - 1 < EDGE or y > h - 2 - EDGE or x - x0 < EDGE or x - x0 >= BOX - EDGE:
                    grid[y][x] = BORDER_INDEX
    return grid


def box_columns(raw):
    """Start columns of the boxes (left border runs on the box top row)."""
    row = _indices(raw)[1]; starts = []
    for x, v in enumerate(row):
        if v != PAPER_INDEX and (x == 0 or row[x - 1] == PAPER_INDEX):
            starts.append(x)
    return starts


def postal_texture(raw):
    stock = _indices(raw)
    # the stock texture: 7 boxes (3 dark + hyphen + 4 light) on white
    if box_columns(raw) != [0, 19, 38, 61, 80, 99, 118] or any(stock[0][x] != PAPER_INDEX for x in range(136)):
        raise ValueError('Unexpected stock postal-box texture')
    new = _write_indices(raw, five_box_grid())
    if new[:_ci4_layout(raw)['offset']] != raw[:_ci4_layout(raw)['offset']] or len(new) != len(raw):
        raise ValueError('Postal texture header/palette changed')
    return new


def _pane_sections(data):
    secs = layout_sections(data)
    return secs, {s[12:28].split(b'\0')[0].decode('ascii'): i for i, s in enumerate(secs)
                  if s[:4] in (b'pan1', b'pic1', b'txt1', b'wnd1', b'bnd1')}


def edit_layout(data, hide=(), move=None):
    secs, index = _pane_sections(data); secs = list(secs)
    for name in hide:
        s = bytearray(secs[index[name]])
        if s[:4] != b'txt1' or not s[8] & 1:
            raise ValueError('Expected a visible textbox: ' + name)
        s[8] &= 0xfe; secs[index[name]] = bytes(s)
    if move:
        name, old, new = move; s = bytearray(secs[index[name]])
        if struct.unpack_from('>f', s, 0x24)[0] != old:
            raise ValueError('Unexpected X position: ' + name)
        struct.pack_into('>f', s, 0x24, new); secs[index[name]] = bytes(s)
    out = rebuild_layout(data, secs)
    if len(out) != len(data):
        raise ValueError('Layout size changed')
    return out


def korean_address_card(content2):
    """Content-2 edits for revision >= 9 (DtestTitle.arc: one texture, two layouts)."""
    outer = ChannelArchive(content2); inner = ChannelArchive(outer.get(TITLE_ARC)); before = inner
    tex = postal_texture(inner.get(POST_TPL))
    main = edit_layout(inner.get(MAIN_LAYOUT), hide=HIDDEN[MAIN_LAYOUT], move=(POST01, POST01_X, POST01_NEW_X))
    addr = edit_layout(inner.get(ADDRESS_LAYOUT), hide=HIDDEN[ADDRESS_LAYOUT])
    for name, payload in ((POST_TPL, tex), (MAIN_LAYOUT, main), (ADDRESS_LAYOUT, addr)):
        inner = ChannelArchive(inner.replace(name, payload))
    changed = sorted(n for n in before.files if before.get(n) != inner.get(n))
    if changed != sorted([POST_TPL, MAIN_LAYOUT, ADDRESS_LAYOUT]) or set(inner.files) != set(before.files):
        raise ValueError('Address-card edit touched other files')
    result = ChannelArchive(outer.replace(TITLE_ARC, inner.data))
    return result.data, dict(archive=TITLE_ARC, postal_texture=dict(file=POST_TPL, boxes=BOXES, columns=box_columns(tex),
                             sha256=sha256(tex)), moved=dict(pane=POST01, x=[POST01_X, POST01_NEW_X]),
                             hidden_reading_panes=[p for v in HIDDEN.values() for p in v], honorific='님 (layout text, rev>=4)')

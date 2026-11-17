"""Title-local Korea-area bridge for the Japan-only Food (Demae) channel.

The Food executable resolves the console area with the RVL SDK SCGetArea
routine at 0x80238050 (identical bytes in the stock and WiiLink DOLs). It
returns the area index from the 13-entry table at 0x80378208
(JPN0 USA1 EUR2 AUS3 BRA4 TWN/ROC5 KOR6 ...). Callers bucket that index into
three service regions (JPN=0, USA=1, EUR=2); every index >= 3, Korea included,
falls through to a null region base and the channel cannot proceed on a
Korean console. This mirrors the Wii Room finding (see kwce/wiiroom_compat).

This patch coerces only SCGetArea's returned index 6 (KOR) to 0 (JPN) through
an unused code cave at the tail of .text1, so a Korean console takes the
native Japanese path. No console setting, personal data, NAND result or other
area is touched. Operates on the decompressed DOL bytes; hardware_verified=False.

The same SCGetArea feeds Demae's personal-data (SPD) library, which has no
Korea entry: path table 0x802346b0 (calls 0x80234710/0x80234758/0x802347ac;
table 0x803102b8 -> /title/00010008/48434{34a,345,350}/data/nocopy/pd.dat),
SPD title/version query 0x80234534 (call 0x8023456c; HCCJ/HCCE/HCCP) and the
"Go to Set Personal Data" launch 0x801a7750 (call 0x801a77b8). With the bridge
Korea resolves to HCCJ = 00010008-4843434a, the title the Korean SPD build uses.
"""
import hashlib

# SCGetArea epilogue/match path, stable across stock and WiiLink DOLs.
SCGETAREA = 0x80238050
MATCH_SITE = 0x8023809c        # `mr r3,r31` on the table-match path
MATCH_ORIG = bytes.fromhex('7fe3fb78')
RESUME = 0x802380a0            # original `b <epilogue>` following the match
CAVE = 0x802d4d48             # 6 words of zero padding at the end of .text1
FUNC_LEN = 132


def _sections(dol):
    import struct
    off = struct.unpack_from('>18I', dol, 0)
    addr = struct.unpack_from('>18I', dol, 0x48)
    size = struct.unpack_from('>18I', dol, 0x90)
    return [(i, off[i], addr[i], size[i]) for i in range(18) if size[i]]


def _to_file(dol, va, length=4):
    for _, o, a, s in _sections(dol):
        if a <= va and va + length <= a + s:
            return o + va - a
    raise ValueError('Address outside DOL sections: %#x' % va)


def _audit_cave(dol, cave, length):
    """Cave must be zero and must not be a branch/absolute target."""
    import struct
    at = _to_file(dol, cave, length)
    if dol[at:at + length] != bytes(length):
        raise ValueError('Food area cave is not free padding')
    if cave.to_bytes(4, 'big') in dol:
        raise ValueError('Food area cave has an absolute reference')
    for _, o, a, s in _sections(dol):
        if a >= 0x80d00000:
            continue
        for pos in range(o, o + s, 4):
            word = int.from_bytes(dol[pos:pos + 4], 'big')
            op = word >> 26
            if op not in (16, 18):
                continue
            mask, sign = (0xfffc, 0x8000) if op == 16 else (0x3fffffc, 0x2000000)
            delta = word & mask
            if delta & sign:
                delta -= 2 * sign
            target = delta if word & 2 else a + pos - o + delta
            if cave <= target < cave + length:
                raise ValueError('An existing branch targets the Food area cave')


def patch_korean_area(dol):
    """Return (patched DOL bytes, record). dol = decompressed Food executable."""
    from .ppc_patch import assemble
    data = bytearray(dol)
    at = _to_file(dol, MATCH_SITE)
    if dol[at:at + 4] != MATCH_ORIG:
        raise ValueError('SCGetArea match instruction differs; refusing to patch')
    # Confirm the KOR row is present in the area table (index byte 6 before "KOR").
    if b'\x06KOR\x00' not in dol:
        raise ValueError('KOR area table row not found')
    cave_payload = assemble(
        'mr 3,31\ncmpwi 3,6\nbne back\nli 3,0\nback: b resume',
        CAVE, {'resume': RESUME})
    if len(cave_payload) % 4 or len(cave_payload) > 24:
        raise ValueError('Food area cave payload size')
    _audit_cave(dol, CAVE, 24)
    trampoline = assemble('b guard', MATCH_SITE, {'guard': CAVE})
    # Write the cave first, then redirect the match path into it.
    cat = _to_file(dol, CAVE, len(cave_payload))
    data[cat:cat + len(cave_payload)] = cave_payload
    data[at:at + 4] = trampoline
    func_at = _to_file(dol, SCGETAREA, FUNC_LEN)
    return bytes(data), dict(
        function='SCGetArea return, Food channel only',
        entry=hex(SCGETAREA), match_site=hex(MATCH_SITE), cave=hex(CAVE),
        source_area=6, resource_area=0, other_areas_unchanged=True,
        console_region_language_country_unchanged=True,
        personal_data_bytes_unchanged=True, native_table_preserved=True,
        scgetarea_sha256=hashlib.sha256(dol[func_at:func_at + FUNC_LEN]).hexdigest(),
        cave_words=len(cave_payload) // 4, hardware_verified=False)

"""News: Korean local time -> UTC when WC24 has no universal time.

The channel's calendar helper (0x80076138) asks WC24 (KD) for universal time and,
when KD has none, falls back to the console clock. WiiLink numbers and stamps the
hourly news files in UTC; a Korean console clock is UTC+9, so in the fallback the
channel asks for the file of the wrong hour and its own check rejects it as about a
day old (NEWS000006). Only the fallback call is redirected: OSGetTime minus nine
hours. With KD universal time available the original path is used unchanged.
"""
import hashlib, struct
from .ppc_patch import assemble, to_file

SITE = 0x800761f8          # 'bl OSGetTime' in the helper's fallback path
OS_GET_TIME = 0x80106e84
CAVE = 0x801e0580          # inside the reference-audited 128-byte slot at 0x801e0560 (country code uses 24 bytes)
CAVE_END = 0x801e05e0
KST_SECONDS = 9 * 3600

SOURCE = f'''
    stwu r1,-16(r1)
    mflr r0
    stw r0,20(r1)
    bl os_get_time
    lis r5,0x8000
    lwz r5,0x00F8(r5)      # bus clock; OS ticks per second = bus clock / 4
    srwi r5,r5,2
    li r6,{KST_SECONDS}
    mulhwu r7,r5,r6
    mullw r6,r5,r6
    subfc r4,r6,r4         # 64-bit ticks -= 9 h
    subfe r3,r7,r3
    lwz r0,20(r1)
    mtlr r0
    addi r1,r1,16
    blr
'''


def branch(site, target, link=True):
    distance = target - site
    if distance % 4 or not -0x2000000 <= distance < 0x2000000: raise ValueError('News branch range')
    return struct.pack('>I', 0x48000000 | (distance & 0x3fffffc) | int(link))


def references(raw, lo, hi):
    """Absolute words, and addresses formed from a live `lis` value, that point into [lo, hi).

    A register holds a known value from `lis` (optionally followed by addi/ori on itself) until
    any other instruction writes it; a use is a displacement load/store or addi/ori from it.
    """
    STORES = set(range(36, 48)) | {52, 53, 54, 55}
    found = []
    for i in range(18):
        off, addr, size = (struct.unpack_from('>I', raw, base + 4 * i)[0] for base in (0, 0x48, 0x90))
        if not size: continue
        words = struct.unpack_from(f'>{size // 4}I', raw, off)
        known = {}
        for k, w in enumerate(words):
            if i >= 7:
                # Data: an aligned word equal to an address in the range is a pointer.
                if lo <= w < hi: found.append(addr + 4 * k)
                continue
            # Code: a word such as 0x801E05D0 is the instruction 'lwz r0,0x5d0(r30)', not a pointer.
            op, rd, ra, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xffff
            simm = imm - 0x10000 if imm & 0x8000 else imm
            if op in (16, 18, 19) :           # branch: forget everything (conservative per block)
                known.clear(); continue
            if op == 15 and ra == 0: known[rd] = imm << 16; continue
            if op == 14 and ra in known:      # addi rd, ra, simm
                value = (known[ra] + simm) & 0xffffffff
                if lo <= value < hi: found.append(addr + 4 * k)
                known[rd] = value; continue
            if op == 24 and rd in known:      # ori ra, rs(rd field), imm
                value = known[rd] | imm
                if lo <= value < hi: found.append(addr + 4 * k)
                known[ra] = value
                if ra != rd: pass
                continue
            if 32 <= op <= 55 and ra in known:   # displacement load/store
                value = (known[ra] + simm) & 0xffffffff
                if lo <= value < hi: found.append(addr + 4 * k)
            if op not in STORES and op not in (10, 11): known.pop(rd, None)
    return found


def patch(raw, parent_sha256):
    if hashlib.sha256(raw).hexdigest() != parent_sha256: raise ValueError('News v25 executable identity differs')
    site = to_file(raw, SITE)
    if raw[site:site + 4] != branch(SITE, OS_GET_TIME): raise ValueError('News fallback time call differs')
    # The two instructions after the call convert ticks to a calendar: mr r5,r31 / bl OSTicksToCalendarTime.
    if raw[site + 4:site + 8] != bytes.fromhex('7fe5fb78'): raise ValueError('News fallback sequence differs')
    payload = assemble(SOURCE, CAVE, dict(os_get_time=OS_GET_TIME))
    if CAVE + len(payload) > CAVE_END: raise ValueError('News UTC adapter exceeds the audited slot')
    refs = references(raw, CAVE, CAVE_END)
    if refs: raise ValueError('Audited slot is referenced: ' + ', '.join(hex(v) for v in refs[:4]))
    at = to_file(raw, CAVE, len(payload))
    out = bytearray(raw)
    out[at:at + len(payload)] = payload
    out[site:site + 4] = branch(SITE, CAVE)
    return bytes(out), dict(site=hex(SITE), cave=hex(CAVE), bytes=len(payload), offset_seconds=-KST_SECONDS,
                            applies='only when WC24 universal time is unavailable (fallback path)',
                            signature_checks_preserved=True, service_urls_unchanged=True,
                            source_sha256=parent_sha256, output_sha256=hashlib.sha256(out).hexdigest())


# --- Revision 28: universal time from the console clock --------------------------------
# Real-console result (2026-11-17): v27 changed nothing. The library function below does
# not fail on this console: it asks KD for the stored RTC/UTC difference (ioctl 0x18,
# which the 2026-11-02 diagnostic saw succeed) and returns difference + raw RTC counter,
# so v27's fallback is never reached. The same diagnostic read KD's universal time as
# "not set" (-30): the stored difference is not a synchronised value, and the time built
# from it is wrong whatever the console clock is set to. The whole function is replaced:
# universal time = console clock (OSGetTime, seconds since 2000) - 9 hours. With a correct
# Korean clock this equals what a synchronised KD would return.
UNIVERSAL = 0x8007bc58        # NWC24 library: s32 GetUniversalTime(s64 *seconds)
UNIVERSAL_BYTES = 0x140
UNIVERSAL_SHA256 = '0a5679d959ed7330cba3d5131dd074c514a2651c0fc28caab91249018c2e9486'
DIV64 = 0x8017a764            # 64-bit signed divide (r3:r4 / r5:r6), the call the original made
UNIVERSAL_SOURCE = f'''
    stwu r1,-16(r1)
    mflr r0
    stw r0,20(r1)
    stw r31,12(r1)
    mr. r31,r3
    li r3,-3               # the original's result for a null pointer
    beq done
    bl os_get_time
    lis r6,0x8000
    lwz r6,0x00F8(r6)
    srwi r6,r6,2           # ticks per second
    li r5,0
    bl div64               # r3:r4 = seconds since 2000, console clock
    lis r5,OFFSET_HI
    ori r5,r5,OFFSET_LO
    addc r4,r4,r5
    addze r3,r3
    stw r3,0(r31)
    stw r4,4(r31)
    li r3,0
done:
    lwz r0,20(r1)
    lwz r31,12(r1)
    mtlr r0
    addi r1,r1,16
    blr
'''


EPOCH_2000 = 946684800       # the library's universal time counts seconds from 1970


def patch_universal(raw, parent_sha256, unix_epoch=True):
    if hashlib.sha256(raw).hexdigest() != parent_sha256: raise ValueError('News v27 executable identity differs')
    at = to_file(raw, UNIVERSAL, UNIVERSAL_BYTES)
    if hashlib.sha256(raw[at:at + UNIVERSAL_BYTES]).hexdigest() != UNIVERSAL_SHA256: raise ValueError('Universal-time function differs')
    # The original makes exactly these two calls; reuse their targets.
    if raw[at + 0xc8:at + 0xcc] != branch(UNIVERSAL + 0xc8, OS_GET_TIME) or raw[at + 0xdc:at + 0xe0] != branch(UNIVERSAL + 0xdc, DIV64):
        raise ValueError('Universal-time call targets differ')
    if unix_epoch:
        offset = EPOCH_2000 - KST_SECONDS
        source = UNIVERSAL_SOURCE.replace('OFFSET_HI', hex(offset >> 16)).replace('OFFSET_LO', hex(offset & 0xffff))
    else:   # build-v28 only: seconds since 2000, which the library's date conversion reads as 1996 (unused)
        source = UNIVERSAL_SOURCE.replace('    lis r5,OFFSET_HI\n    ori r5,r5,OFFSET_LO\n    addc r4,r4,r5\n    addze r3,r3',
                                          f'    addic r4,r4,-{KST_SECONDS}\n    addme r3,r3')
        if 'OFFSET_HI' in source: raise ValueError('v28 source form')
    payload = assemble(source, UNIVERSAL, dict(os_get_time=OS_GET_TIME, div64=DIV64))
    if len(payload) > UNIVERSAL_BYTES: raise ValueError('Replacement exceeds the function')
    out = bytearray(raw); out[at:at + len(payload)] = payload
    return bytes(out), dict(function=hex(UNIVERSAL), bytes=len(payload), offset_seconds=-KST_SECONDS, unix_epoch=unix_epoch,
                            source='console clock (OSGetTime); KD time difference no longer used by the channel',
                            signature_checks_preserved=True, service_urls_unchanged=True,
                            source_sha256=parent_sha256, output_sha256=hashlib.sha256(out).hexdigest())

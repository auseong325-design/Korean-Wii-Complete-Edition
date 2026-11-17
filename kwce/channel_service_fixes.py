"""In-place executable edits for two service-side mismatches seen on hardware (2026-11-16).

Wii Room 354405: the channel posts ``miiinfo.cgi`` and accepts only ``code`` 1 or 2 in the
``MiiInfo`` reply (checker 0x8004b454, error type 5). The public WiiLink room server answers
``code`` 0 (room-server a7a744a ``url2/related.py``; live reply checked anonymously), so the
channel stops with 354400 + 5. The checker now treats 0 as 1 (stored), everything else as before.

Votes 239001: DLTaskManager shows this fixed number whenever its error class is 0 or >= 7
(``convertToDLTaskErr`` maps most NWC24 results to 7), which hides the cause. The number now is
23900 - mLastNWC24Err (shown as 0239NN, NN = the NWC24 result without its sign). Behaviour is
otherwise unchanged; this is a readout, not a fix.

Votes 023945 (v23, from v22): the readout showed NWC24 result -45 = VERIFY_SIGNATURE. WiiLink's
``image/mapN.bin`` result maps are signed with a key the patched channel does not carry (every other
public votes file verifies), so a real Wii's KD rejects them; Dolphin does not verify. Voting and
predictions are unaffected. v23 skips the dialog only for -45: the category-3 debug block, identical
to the category-1/2 block, is merged into it and its six words hold the check.

All edits keep section table, sizes and every other byte.
"""
import hashlib, struct
from .ppc_patch import to_file

ROOM_SITE = 0x8004b468
ROOM_NEW = (0x80860000,   # lwz    r4,0(r6)        reply code
            0x2c040000,   # cmpwi  r4,0
            0x4082000c,   # bne    +12
            0x38800001,   # li     r4,1            server's 0 ("thanks") = accepted
            0x90860000,   # stw    r4,0(r6)
            0x3804ffff,   # addi   r0,r4,-1
            0x28000001,   # cmplwi r0,1            code 1 or 2
            0x40810034,   # ble    0x8004b4b8      ok
            0x60000000)   # nop                    else error type 5 with r4 = code
ROOM_OLD = (0x80860000, 0x38000000, 0x2c040001, 0x41800010, 0x2c040002, 0x41810008, 0x38000001, 0x2c000000, 0x40820030)

VOTES_SITE = 0x80076870
VOTES_OLD = (0x806d8bc0, 0x3ca08023, 0x3cc00004, 0x38800007, 0x38630080, 0x38a50df8, 0x38c6a599)
VOTES_NEW = (0x80c30010,   # lwz    r6,0x10(r3)    this->mLastNWC24Err (r3 is still `this` here)
             0x806d8bc0,   # lwz    r3,-0x7440(r13)
             0x3ca08023,   # lis    r5,0x8023
             0x38800007,   # li     r4,7
             0x38630080,   # addi   r3,r3,0x80
             0x38a50df8,   # addi   r5,r5,0xdf8    L"%06d"
             0x20c65d5c)   # subfic r6,r6,23900


def _edit(raw, parent_sha256, site, old, new, label):
    if hashlib.sha256(raw).hexdigest() != parent_sha256: raise ValueError(f'{label} executable identity differs')
    at = to_file(raw, site, 4 * len(old))
    if raw[at:at + 4 * len(old)] != struct.pack(f'>{len(old)}I', *old): raise ValueError(f'{label} site differs')
    out = bytearray(raw); out[at:at + 4 * len(new)] = struct.pack(f'>{len(new)}I', *new)
    return bytes(out), dict(site=f'{site:#010x}', bytes=4 * len(new), source_sha256=parent_sha256,
                            output_sha256=hashlib.sha256(out).hexdigest())


def patch_room_miiinfo(raw, parent_sha256):
    return _edit(raw, parent_sha256, ROOM_SITE, ROOM_OLD, ROOM_NEW, 'Wii Room')


def patch_votes_readout(raw, parent_sha256):
    return _edit(raw, parent_sha256, VOTES_SITE, VOTES_OLD, VOTES_NEW, 'Votes')


# --- Votes v23: no dialog for NWC24_ERR_VERIFY_SIGNATURE (-45) --------------------------------------
VOTES_QUIET = (
    # (site, old word, new word)
    (0x800766cc, 0x40800034, 0x4080001c),   # bge 0x80076700 -> bge 0x800766e8 (identical debug block)
    (0x800766d8, 0x48000198, 0x48000028),   # b   0x80076870 -> b   0x80076700 (class 0)
    (0x800766e0, 0x40800190, 0x40800020),   # bge 0x80076870 -> bge 0x80076700 (class >= 7)
    (0x80076700, 0x3c608021, 0x80c30010),   # lwz    r6,0x10(r3)    mLastNWC24Err
    (0x80076704, 0x3863a640, 0x2c06ffd3),   # cmpwi  r6,-45
    (0x80076708, 0x3863056c, 0x418201b0),   # beq    0x800768b8     return without a dialog
    (0x8007670c, 0x4cc63182, 0x806d8bc0),   # lwz    r3,-0x7440(r13)
    (0x80076710, 0x4808a9a9, 0x48000168),   # b      0x80076878     v22 readout continues
)


def patch_votes_quiet_signature(raw, parent_sha256):
    if hashlib.sha256(raw).hexdigest() != parent_sha256: raise ValueError('Votes executable identity differs')
    out = bytearray(raw)
    for site, old, new in VOTES_QUIET:
        at = to_file(raw, site, 4)
        if struct.unpack_from('>I', raw, at)[0] != old: raise ValueError(f'Votes site {site:#x} differs')
        struct.pack_into('>I', out, at, new)
    return bytes(out), dict(sites=[f'{s:#010x}' for s, _, _ in VOTES_QUIET], bytes=4 * len(VOTES_QUIET),
                            suppressed_nwc24_result=-45, source_sha256=parent_sha256,
                            output_sha256=hashlib.sha256(out).hexdigest())


# Votes build-v24 (full review 2026-11-17): "투표 지역 변경" launches the region-select hidden title
# 00010008-HALE (lis r4,0x4841 / addi r4,r4,0x4c45 at 0x80052988, OSLaunchTitle 0x80103abc). A Korean
# console has HALK, not HALE, so OSLaunchTitle failed and the channel showed message 1100 ("지역 설정을
# 확인할 수 없습니다 … Wii 메뉴로 돌아갑니다") and quit. Launch HALK instead.
VOTES_REGION_SELECT = ((0x80052990, 0x38844c45, 0x38844c4b),)


def patch_votes_region_select(raw, parent_sha256):
    if hashlib.sha256(raw).hexdigest() != parent_sha256: raise ValueError('Votes executable identity differs')
    out = bytearray(raw)
    for site, old, new in VOTES_REGION_SELECT:
        at = to_file(raw, site, 4)
        if struct.unpack_from('>I', raw, at)[0] != old: raise ValueError(f'Votes site {site:#x} differs')
        struct.pack_into('>I', out, at, new)
    return bytes(out), dict(sites=[f'{s:#010x}' for s, _, _ in VOTES_REGION_SELECT], bytes=4,
                            launched_title='00010008-48414c4b (HALK, Korean region select)', replaced='00010008-48414c45 (HALE)',
                            source_sha256=parent_sha256, output_sha256=hashlib.sha256(out).hexdigest())


# Votes build-v25: v24 changed only the "is HALE installed?" check. The launch itself is a second
# hard-coded OSLaunchTitle(0x00010008, 'HALE') at 0x8003b270 (lis/addi r4, bl 0x80102e8c); on a Korean
# console it failed silently and the channel returned to the Wii Menu (hardware + Dolphin, 1.0.6).
VOTES_REGION_LAUNCH = ((0x8003b278, 0x38844c45, 0x38844c4b),)


def patch_votes_region_launch(raw, parent_sha256):
    if hashlib.sha256(raw).hexdigest() != parent_sha256: raise ValueError('Votes executable identity differs')
    out = bytearray(raw)
    for site, old, new in VOTES_REGION_LAUNCH:
        at = to_file(raw, site, 4)
        if struct.unpack_from('>I', raw, at)[0] != old: raise ValueError(f'Votes site {site:#x} differs')
        struct.pack_into('>I', out, at, new)
    return bytes(out), dict(sites=[f'{s:#010x}' for s, _, _ in VOTES_REGION_LAUNCH], bytes=4,
                            launched_title='00010008-48414c4b (HALK)', source_sha256=parent_sha256,
                            output_sha256=hashlib.sha256(out).hexdigest())


# Votes build-v26: the channel's SDK OSLaunchTitle (0x80102a80..) checks the target TMD region against an
# area read from setting.txt through a table that knows only JP/US/EU (0x80276880; Korea -> -1). Any title
# that is not region-free fails "OSLaunchTitle(): Country code is not correct" and the SDK returns to the
# Wii Menu -- even 00010008-HALK and other Korean titles [Dolphin diagnostics launch-v1/v2]. The mismatch
# branch result (li r0,0 at 0x80102b8c) becomes a match (li r0,1); the firmware and company checks stay.
VOTES_LAUNCH_REGION = ((0x80102b8c, 0x38000000, 0x38000001),)


def patch_votes_launch_region(raw, parent_sha256):
    if hashlib.sha256(raw).hexdigest() != parent_sha256: raise ValueError('Votes executable identity differs')
    out = bytearray(raw)
    for site, old, new in VOTES_LAUNCH_REGION:
        at = to_file(raw, site, 4)
        if struct.unpack_from('>I', raw, at)[0] != old: raise ValueError(f'Votes site {site:#x} differs')
        struct.pack_into('>I', out, at, new)
    return bytes(out), dict(sites=[f'{s:#010x}' for s, _, _ in VOTES_LAUNCH_REGION], bytes=4,
                            bypassed='OSLaunchTitle country/region check (SDK area table JP/US/EU only)',
                            source_sha256=parent_sha256, output_sha256=hashlib.sha256(out).hexdigest())


# Votes build-v27 / v28 (user decision 2026-11-17: stay inside the WiiLink service, no Korea on the server).
# The server's regionID 1 means "the whole country" and 2.. are that country's provinces/states in order
# (WiiLink24/EVC database.go). A Korean SADR region number sent with a disguised country would be counted
# as some unrelated state, so the REGION getter returns 1 (whole country):
#   0x800509ec rlwinm r3,r3,16,24,31 -> li r3,1.
# v27 keeps the USA (49) country of v20+; v28 is the Japan edition: COUNTRY getter li r3,49 -> li r3,1.
VOTES_WHOLE_COUNTRY = ((0x800509ec, 0x5463863e, 0x38600001),)
VOTES_JAPAN = ((0x800509c8, 0x38600031, 0x38600001),)


def _apply(raw, parent_sha256, sites):
    if hashlib.sha256(raw).hexdigest() != parent_sha256: raise ValueError('Votes executable identity differs')
    out = bytearray(raw)
    for site, old, new in sites:
        at = to_file(raw, site, 4)
        if struct.unpack_from('>I', raw, at)[0] != old: raise ValueError(f'Votes site {site:#x} differs')
        struct.pack_into('>I', out, at, new)
    return bytes(out)


def patch_votes_whole_country(raw, parent_sha256):
    out = _apply(raw, parent_sha256, VOTES_WHOLE_COUNTRY)
    return out, dict(sites=['0x800509ec'], region_id=1, country_id=49, source_sha256=parent_sha256,
                     output_sha256=hashlib.sha256(out).hexdigest())


def patch_votes_japan(raw, parent_sha256):
    out = _apply(raw, parent_sha256, VOTES_JAPAN)
    return out, dict(sites=['0x800509c8'], region_id=1, country_id=1, source_sha256=parent_sha256,
                     output_sha256=hashlib.sha256(out).hexdigest())

"""Title-local Korean resource selection for the Kirby TV (VODF) executable.

The player maps SCGetLanguage 1..6 to config/EU/<xx>/, text/EU/<xx>/ and the
EU HOME Menu archives; every other language (0, 7, 8, 9) takes a default
branch. Only that default branch is extended: language 9 selects KR/KO/ and
the Korean HOME archives with HOME message column 9. Languages 0..8 execute
the original instructions. The console's language/area settings are never
read differently or changed.

New code lives in verified function-alignment padding (zero words after a
blr that no branch or pointer references), placed close enough for the
conditional branches it needs.
"""
import hashlib
import struct
from .ppc_patch import assemble, sections, to_file
from .wiiroom_formats import decompress_lz11, reencode_lz11_same_size

CONTENT_SHA256 = '42bb4d2ebed85aa16c978f6031f5e6429b4f610039876bddff1e0fa5340d65a5'
DOL_SHA256 = '5c13b38f7eb8cbfee0d4472778f8e8eb92d48229c2cd1c4e041f0ef06b760102'
FUNCTION_SHA256 = {
    (0x8004d980, 0x8004dec0): '3fdd48fd31c365571c1009b5f8d33a8bdbdd181b5db3588f621ae695eb7fb237',
    (0x80053270, 0x80053600): 'ca0724f4c60b14819bc149cd6231d224bcb4073d2fd747ce3147a8e7ed8b6266',
    (0x80050790, 0x80050d50): '49896877e9ff82ccfe90797e5872691ed2aa2ff5809a98640fc711d7e5c44367',
}
KOREAN_DIR = 'KR/KO/'
HOME_ARCHIVE = 'hbKO.arc'      # HomeButton3/hbKO.arc in content 6
HOME_MANUAL = 'nwKO.arc'       # HomeButton3/nwKO.arc in content 8
HOME_LANGUAGE = 9              # Korean column of the 10-column HOME CSVs

# (address, original word, purpose)
HOOKS = [
    (0x8004da3c, 0x48000060, 'config path: default branch (b 0x8004da9c)'),
    (0x80053390, 0x480001f8, 'ErrorStrings path: default branch (b 0x80053588)'),
    (0x800508c8, 0x480003dc, 'HOME archive: default branch (b 0x80050ca4)'),
    (0x80050d00, 0x3b9e00b4, 'HOME manual archive: addi r28,r30,180 (nwm_eng)'),
]


def _padding(dol):
    """Zero runs after blr in text sections: {address: length}."""
    runs = {}
    for index, off, va, size in sections(dol):
        if index >= 7:
            continue
        pos = off
        while pos < off + size:
            if dol[pos:pos + 4] == bytes(4) and dol[pos - 4:pos] == bytes.fromhex('4e800020'):
                start = pos
                while pos < off + size and dol[pos:pos + 4] == bytes(4):
                    pos += 4
                runs[va + start - off] = pos - start
            else:
                pos += 4
    return runs


def _referenced(dol, ranges):
    """Addresses in `ranges` that any direct branch targets or any word points at."""
    import bisect
    hits = set()
    spans = sorted(ranges)
    starts = [s for s, _ in spans]

    def inside(target):
        i = bisect.bisect_right(starts, target) - 1
        if i >= 0 and target < spans[i][0] + spans[i][1]:
            return spans[i][0]
        return None
    for index, off, va, size in sections(dol):
        for pos in range(off, off + size - 3, 4):
            word = int.from_bytes(dol[pos:pos + 4], 'big')
            if index >= 7:
                start = inside(word)
                if start is not None:
                    hits.add(start)
                continue
            opcode = word >> 26
            if opcode not in (16, 18):
                start = inside(word)
                if start is not None:
                    hits.add(start)
                continue
            mask, sign = (0xfffc, 0x8000) if opcode == 16 else (0x3fffffc, 0x2000000)
            delta = word & mask
            if delta & sign:
                delta -= 2 * sign
            target = delta if word & 2 else va + pos - off + delta
            start = inside(target)
            if start is not None:
                hits.add(start)
    return hits


def _ha(value):
    low = value & 0xffff
    return ((value + 0x8000) >> 16) & 0xffff, low - 0x10000 if low & 0x8000 else low


def plan(dol):
    """Choose caves deterministically and return {address: bytes} plus a record."""
    if hashlib.sha256(dol).hexdigest() != DOL_SHA256:
        raise ValueError('Only the pinned Kirby TV executable is supported')
    for (lo, hi), digest in FUNCTION_SHA256.items():
        if hashlib.sha256(dol[to_file(dol, lo):to_file(dol, hi)]).hexdigest() != digest:
            raise ValueError(f'Language function differs at {lo:#x}')
    for address, word, _ in HOOKS:
        if int.from_bytes(dol[to_file(dol, address):to_file(dol, address) + 4], 'big') != word:
            raise ValueError(f'Hook word differs at {address:#x}')
    runs = _padding(dol)
    used_by_code = _referenced(dol, [(a, n) for a, n in runs.items()])
    free = sorted((a, n) for a, n in runs.items() if a not in used_by_code)
    taken = set()

    def pick(anchor, length, limit=0x7000):
        best = None
        for address, size in free:
            if size < length or address in taken or abs(address - anchor) > limit:
                continue
            if best is None or abs(address - anchor) < abs(best - anchor):
                best = address
        if best is None:
            raise ValueError(f'No verified padding near {anchor:#x}')
        taken.add(best)
        return best

    # String storage (read-only data inside padding that never executes).
    strings = {}
    for name, text in (('dir', KOREAN_DIR), ('home', HOME_ARCHIVE), ('manual', HOME_MANUAL)):
        raw = text.encode('ascii') + b'\0'
        strings[name] = (pick(0x80050790, (len(raw) + 3) & ~3, limit=0x400000), raw)
    groups = {
        'config': (0x8004da9c, 3), 'text': (0x80053588, 3),
        'home': (0x80050ca4, 3), 'manual': (0x80050d04, 3),
    }
    caves = {name: [pick(anchor, 12) for _ in range(count)] for name, (anchor, count) in groups.items()}
    d_hi, d_lo = _ha(strings['dir'][0])
    h_hi, h_lo = _ha(strings['home'][0])
    m_hi, m_lo = _ha(strings['manual'][0])
    c, t, h, m = caves['config'], caves['text'], caves['home'], caves['manual']
    code = {}

    def put(address, source, symbols):
        payload = assemble(source, address, symbols)
        if len(payload) > 12:
            raise ValueError('Cave overflow')
        code[address] = payload
    # config/: lang 9 -> append KR/KO/ through the English case's own call
    put(c[0], 'cmpwi r0,9\nbne default\nb next', dict(default=0x8004da9c, next=c[1]))
    put(c[1], f'addi r3,r1,32\nlis r4,{d_hi}\nb next', dict(next=c[2]))
    put(c[2], f'addi r4,r4,{d_lo}\nb append', dict(append=0x8004da48))
    # text/: lang 9 -> r30 = KR/KO/ and continue the English case after its addi
    put(t[0], 'cmpwi r0,9\nbne default\nb next', dict(default=0x80053588, next=t[1]))
    put(t[1], f'lwz r0,88(r1)\nlis r30,{d_hi}\nb next', dict(next=t[2]))
    put(t[2], f'addi r30,r30,{d_lo}\nb resume', dict(resume=0x8005339c))
    # HOME archive: lang 9 -> HOME language 9 and hbKO.arc
    put(h[0], 'cmpwi r0,9\nbne default\nb next', dict(default=0x80050ca4, next=h[1]))
    put(h[1], f'li r0,{HOME_LANGUAGE}\nstw r0,420(r29)\nb next', dict(next=h[2]))
    put(h[2], f'lis r28,{h_hi}\naddi r28,r28,{h_lo}\nb resume', dict(resume=0x80050cb0))
    # HOME manual frame: nwKO.arc when the stored HOME language is 9
    put(m[0], 'lwz r27,420(r29)\ncmpwi r27,9\nb next', dict(next=m[1]))
    put(m[1], 'addi r28,r30,180\nbne resume\nb next', dict(resume=0x80050d04, next=m[2]))
    put(m[2], f'lis r28,{m_hi}\naddi r28,r28,{m_lo}\nb resume', dict(resume=0x80050d04))
    hooks = {
        0x8004da3c: assemble('b cave', 0x8004da3c, dict(cave=c[0])),
        0x80053390: assemble('b cave', 0x80053390, dict(cave=t[0])),
        0x800508c8: assemble('b cave', 0x800508c8, dict(cave=h[0])),
        0x80050d00: assemble('b cave', 0x80050d00, dict(cave=m[0])),
    }
    writes = dict(code)
    writes.update(hooks)
    for name, (address, raw) in strings.items():
        writes[address] = raw
    record = dict(
        function='SCGetLanguage default branches (config, ErrorStrings, HOME Menu)',
        korean_language=9, korean_directory=KOREAN_DIR, home_archive='HomeButton3/' + HOME_ARCHIVE,
        home_manual_archive='HomeButton3/' + HOME_MANUAL, home_message_column=HOME_LANGUAGE,
        other_languages_unchanged=True, console_settings_unchanged=True,
        hooks=[dict(address=hex(a), original=f'{w:08x}', purpose=p) for a, w, p in HOOKS],
        caves={k: [hex(x) for x in v] for k, v in caves.items()},
        strings={k: hex(v[0]) for k, v in strings.items()},
        padding_checked='zero words after blr; no branch target or pointer word inside',
        hardware_verified=False)
    return writes, record


def patch_dol(dol):
    writes, record = plan(dol)
    out = bytearray(dol)
    for address, payload in sorted(writes.items()):
        at = to_file(out, address, len(payload))
        if address not in (a for a, _, _ in HOOKS) and out[at:at + len(payload)] != bytes(len(payload)):
            raise ValueError(f'Cave not empty at {address:#x}')
        out[at:at + len(payload)] = payload
    changed = sum(1 for i in range(len(dol)) if dol[i] != out[i])
    record['changed_bytes'] = changed
    return bytes(out), record


def patch_content(content):
    """Patch the LZ11 content 1 in place of its own match structure."""
    if hashlib.sha256(content).hexdigest() != CONTENT_SHA256:
        raise ValueError('Only the pinned Kirby TV content 1 is supported')
    dol = decompress_lz11(content)
    edited, record = patch_dol(dol)
    packed = reencode_lz11_same_size(content, edited)
    record.update(dol_sha256=hashlib.sha256(edited).hexdigest(), content_sha256=hashlib.sha256(packed).hexdigest())
    return packed, record

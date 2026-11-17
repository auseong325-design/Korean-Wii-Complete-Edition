"""GameCube-only disc channel layout for the 43K System Menu (v518), menu memory only.

The 43K resource (content 0000009d.app) still ships Nintendo's original disc
banner `layout/common/diskBann.ash` (`my_DiskCh_a.brlyt` + 10 BRLANs): the
two-disc layout of the GameCube-capable menus, with the Wii disc at x=-66, the
GameCube disc at x=+94 and the GameCube panes visible (DVD panes hidden). The
decompiled 43J/43U/43E channel-title scene loads exactly these names. The
Korean menu instead loads `diskBann2.ash` (`my_DiskCh_a_R*`), where the Wii disc
is centred and the GameCube/DVD panes are hidden in a three-disc arrangement.

This patch only changes data the same code already reads:
* names 1-6 and the BRLYT name are shortened in place (each new NUL falls on a
  non-word-start byte). Names 2-6 stay at their addresses because the KWCE DVD
  hook binds them by address;
* names 7-10 are rewritten as a packed block right after name 6 and their four
  pointer-table entries are updated;
* "diskBann.ash" is written one byte after the old "diskBann2.ash" and the
  single `addi r5,r5,0x3a1c` that builds its address becomes `0x3a1d`.
Every rewritten 32-bit word and every original word used as a Priiloader hash
starts with a nonzero byte, so the old token parser (Priiloader 0.8.2) keeps all
bytes. No resource, NAND or console data is written. Applied by Priiloader.
"""
import hashlib
import struct

from .patches import MENU_SHA1

FILLER = b'K'
IN_PLACE = {  # address -> (43K name, original-layout name)
    0x81623864: ('my_DiskCh_a_R_Start.brlan', 'my_DiskCh_a_Start.brlan'),
    0x8162387E: ('my_DiskCh_a_R_DiskStart.brlan', 'my_DiskCh_a_DiskStart.brlan'),
    0x8162389C: ('my_DiskCh_a_R_DiskLoop.brlan', 'my_DiskCh_a_DiskLoop.brlan'),
    0x816238B9: ('my_DiskCh_a_R_DiskEnd.brlan', 'my_DiskCh_a_DiskEnd.brlan'),
    0x816238D5: ('my_DiskCh_a_R_DiskLost.brlan', 'my_DiskCh_a_DiskLost.brlan'),
    0x816238F2: ('my_DiskCh_a_R_DiskIn.brlan', 'my_DiskCh_a_DiskIn.brlan'),
    0x816239B0: ('my_DiskCh_a_R.brlyt', 'my_DiskCh_a.brlyt'),
}
MOVED = [  # (old address, 43K name, original-layout name), pointer-table order 7..10
    (0x8162390D, 'my_DiskCh_a_R_DiskEject.brlan', 'my_DiskCh_a_DiskEject.brlan'),
    (0x8162392B, 'my_DiskCh_a_R_Unknown.brlan', 'my_DiskCh_a_Unknown.brlan'),
    (0x81623947, 'my_DiskCh_a_R_UnknownLoop.brlan', 'my_DiskCh_a_UnknownLoop.brlan'),
    (0x81623967, 'my_DiskCh_a_R_UnknwnEject.brlan', 'my_DiskCh_a_UnknwnEject.brlan'),
]
BLOCK = (0x8162390B, 0x81623988)       # free bytes after the shortened name 6, up to the table
TABLE = 0x81623988                     # mscDiskAnimNames[10]
LAYOUT_POINTER = (0x8166B060, 0x816239B0)
ARCHIVE_OLD = (0x81623A1C, 'diskBann2.ash')
ARCHIVE_NEW = (0x81623A1D, 'diskBann.ash')
ARCHIVE_ADDI = (0x813B362C, 0x38A53A1C, 0x38A53A1D)  # addi r5,r5,0x3a1c -> 0x3a1d
# Word ranges written by the Priiloader entry (each starts and ends on unchanged neighbours
# whose original first byte is nonzero); see kwce.priiloader_hacks.gc_layout_entry.
PAIR_RANGES = [(0x81623870, 0x8162387C), (0x81623888, 0x8162389C), (0x816238A8, 0x816238B8),
               (0x816238C4, 0x816238D4), (0x816238E0, 0x816238F0), (0x816238FC, 0x816239B0),
               (0x816239B8, 0x816239C4), (0x81623A1C, 0x81623A28), (0x813B362C, 0x813B3630)]
ARCHIVE = 'layout/common/diskBann.ash'
LAYOUT = 'arc/blyt/my_DiskCh_a.brlyt'


def _sections(dol):
    out = []
    for i in range(18):
        off, addr, size = [struct.unpack_from('>I', dol, p + 4 * i)[0] for p in (0, 0x48, 0x90)]
        if size:
            out.append((off, addr, size))
    return out


def file_offset(dol, address, length=1):
    for off, addr, size in _sections(dol):
        if addr <= address and address + length <= addr + size:
            return off + address - addr
    raise ValueError('Address outside the menu DOL')


def _expect(menu, address, data, what):
    at = file_offset(menu, address, len(data))
    if menu[at:at + len(data)] != data:
        raise ValueError('43K disc layout data differs: ' + what)
    return at


def moved_layout():
    """Deterministic placement of names 7..10: NUL never on a word-start byte."""
    pos, placed = BLOCK[0], []
    for _, _, new in MOVED:
        raw = new.encode('ascii') + b'\0'
        while (pos + len(raw) - 1) % 4 == 0:
            pos += 1
        placed.append((pos, raw))
        pos += len(raw)
    if pos > BLOCK[1]:
        raise ValueError('Moved disc layout names do not fit')
    return placed


def patch_gc_only_layout(menu, *, require_original=True):
    """Return (patched DOL, record). `menu` may already carry other KWCE code patches."""
    if require_original and hashlib.sha1(menu).hexdigest() != MENU_SHA1:
        raise ValueError('Only the original 43K menu DOL')
    out = bytearray(menu)
    for address, (old, new) in IN_PLACE.items():
        at = _expect(menu, address, old.encode('ascii') + b'\0', old)
        if (address + len(new)) % 4 == 0 or new != old.replace('_R', '', 1):
            raise ValueError('Unsafe in-place layout name')
        out[at:at + len(new) + 1] = new.encode('ascii') + b'\0'
    for index, (address, old, _) in enumerate(MOVED):
        _expect(menu, address, old.encode('ascii') + b'\0', old)
        _expect(menu, TABLE + 4 * (6 + index), struct.pack('>I', address), 'animation pointer table')
    for index, address in enumerate(sorted(IN_PLACE)[:6]):
        _expect(menu, TABLE + 4 * index, struct.pack('>I', address), 'animation pointer table')
    start = file_offset(menu, BLOCK[0], BLOCK[1] - BLOCK[0])
    out[start:start + BLOCK[1] - BLOCK[0]] = FILLER * (BLOCK[1] - BLOCK[0])
    for index, (address, raw) in enumerate(moved_layout()):
        at = file_offset(menu, address, len(raw))
        out[at:at + len(raw)] = raw
        struct.pack_into('>I', out, file_offset(menu, TABLE + 4 * (6 + index), 4), address)
    _expect(menu, LAYOUT_POINTER[0], struct.pack('>I', LAYOUT_POINTER[1]), 'layout name pointer')
    old_at = _expect(menu, ARCHIVE_OLD[0], ARCHIVE_OLD[1].encode('ascii') + b'\0', ARCHIVE_OLD[1])
    raw = ARCHIVE_NEW[1].encode('ascii') + b'\0'
    if (ARCHIVE_NEW[0] + len(raw) - 1) % 4 == 0 or ARCHIVE_NEW[0] + len(raw) > ARCHIVE_OLD[0] + len(ARCHIVE_OLD[1]) + 1:
        raise ValueError('Unsafe archive name placement')
    at = old_at + ARCHIVE_NEW[0] - ARCHIVE_OLD[0]
    out[at:at + len(raw)] = raw
    _expect(menu, ARCHIVE_ADDI[0], struct.pack('>I', ARCHIVE_ADDI[1]), 'archive name addi')
    struct.pack_into('>I', out, file_offset(menu, ARCHIVE_ADDI[0], 4), ARCHIVE_ADDI[2])
    changed = [i for i in range(len(menu)) if menu[i] != out[i]]
    covered = set()
    for a, b in PAIR_RANGES:
        f = file_offset(menu, a, b - a)
        covered.update(range(f, f + b - a))
    if not set(changed) <= covered:
        raise ValueError('Changed bytes outside the reviewed Priiloader ranges')
    record = dict(feature='GameCube-only disc channel: original two-disc layout (diskBann.ash)',
                  system_menu='4.3K v518', names_in_place=len(IN_PLACE), names_moved=len(MOVED),
                  pointer_entries_changed=len(MOVED), code_words_changed=1, bytes_changed=len(changed),
                  dvd_hook_names_kept_at_original_addresses=True, resource_written=False, nand_writes=False,
                  dvd_panes_visible=False, gc_panes_visible=True)
    return bytes(out), record


def resolved_names(dol):
    """Read back the 10 animation names, the layout name and the archive name from a DOL."""
    def cstr(address):
        at = file_offset(dol, address)
        return dol[at:dol.index(b'\0', at)].decode('ascii')
    table = [struct.unpack_from('>I', dol, file_offset(dol, TABLE + 4 * i, 4))[0] for i in range(10)]
    layout = struct.unpack_from('>I', dol, file_offset(dol, LAYOUT_POINTER[0], 4))[0]
    addi = struct.unpack_from('>I', dol, file_offset(dol, ARCHIVE_ADDI[0], 4))[0]
    archive = (0x81620000 + (addi & 0xFFFF))  # lis r5,0x8162 precedes the addi
    return [cstr(a) for a in table], cstr(layout), cstr(archive)


def check_resource(resource):
    """Confirm the console resource ships every original-layout file this patch names."""
    from .formats import U8, ash_decompress
    outer = U8(resource)
    inner = U8(ash_decompress(outer.get(ARCHIVE)))
    names = {n.rsplit('/', 1)[-1] for n in inner.files}
    wanted = [new for _, new in IN_PLACE.values()] + [new for _, _, new in MOVED]
    missing = sorted(n for n in wanted if n not in names)
    if missing:
        raise ValueError('Original disc layout files missing: ' + ', '.join(missing))
    return dict(archive=ARCHIVE, files=len(names), layout_sha256=hashlib.sha256(inner.get(LAYOUT)).hexdigest())

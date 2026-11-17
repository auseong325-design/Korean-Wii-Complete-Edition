"""Country disguise for the Everybody Votes Channel (id votes, TID 0001000148414a45).

A real Korean Wii reports country 136 (Korea). The public RiiConnect24 / WiiLink EVC
service never lists 136 in its ``countryCodes`` table (references/access-source/const.go),
so the channel stops with "country not available". This presents the channel to the
service as country 49 (USA) -- the same limited, in-place approach News build-v22 uses
(map 136->49 at the single value-producing function, nothing else; see
docs/channels/news.md). Participating as another country is accepted by the user.

Where the country comes from (verified by disassembly of content 1, build-v17/v18):

  * SYSCONF ``IPL.SADR`` is read by the reader at ``0x8010db60`` (returns the raw address
    word; COUNTRY is the top byte ``(word>>24)&0xFF``, REGION is ``(word>>16)&0xFF``). Its
    only callers are the two one-line wrappers below.
  * COUNTRY getter ``0x800509b4``: ``bl reader; srwi r3,r3,24`` -> returns the country byte.
  * REGION getter ``0x800509d8``: ``bl reader; rlwinm r3,r3,16,24,31`` -> returns the region byte.

Every country consumer routes through the COUNTRY getter: the saved country byte at
obj+8 / obj+9 that fills the ``%03d`` in every content and CGI URL (``/first_data.bin``,
``/%03d/voting.bin``, the map / question / result tiles, ``vote.cgi?...countryID=``), the
worldwide-graph and national setup (``0x80072bf8``), the save region-name load
(``0x80074698``) and the settings compare (``0x80078690``). The REGION getter and the
reader's own validity / cache logic are left byte-for-byte unchanged, so ``regionID`` and
the region-name table keep the console's real region.

Why this hook and not the others:

  * Mapping at the COUNTRY getter is the single narrowest choke point -- strictly narrower
    than the shared reader (which also feeds the region getter and carries the IPL.SADR
    validity / write-back logic) and far narrower than patching the ~10 URL / save / graph
    call sites one by one.
  * It is the exact analogue of the News v22 precedent (map 136->49 at the one function
    that produces the value).

How it is applied (revision 19 -- DO NOT SHIP, boot-crashes): the getter's ``srwi r3,r3,24``
at ``0x800509c8`` was replaced with a branch to a 36-byte cave at ``0x800064bc``.
[직접 확인 2026-10-30, Dolphin] That cave is NOT dead: it is the last 36 bytes of text0
(``.init``), the zero terminators of the ``_rom_copy_info`` / ``_bss_init_info`` /
``_eti_init_info`` tables that ``__init_data`` walks until it meets a zero entry. Code written
there is read as a table entry, so the boot stops with ``Invalid write to 0x5463463e`` (the
``srwi`` word used as an address) at a PC in 0x8000xxxx. Never use the zero tail of text0.

How it is applied (revision 20, the shipped one): the same ``srwi`` is replaced in place by
``li r3,49``. The WAD is a Korean-console build (TMD region 4), so on every console that can
launch it the country byte is 136; returning 49 unconditionally is the same result as the
136->49 mapping, with NO cave, NO new section and exactly 4 changed bytes. The reader call
before it (``bl reader``) still runs, so its validity / cache logic is unchanged.

Language is deliberately NOT remapped. A Korean console (system language 9) already
resolves to EVC display language English (1) through the channel's own SCGetLanguage
mapping (``0x80037714``: language > 6 -> 1), and the public USA (49) feed serves English,
so the disguised channel shows English content. [직접 확인 2026-10-30, public static GET on
http://vt.wii.rc24.xyz: ``/first_data.bin`` lists country 49 with supported languages
English(1)/Spanish(4)/FrenchCanadian(8); ``/049/voting.bin`` carries text in exactly those
languages; ``/136/voting.bin`` is a 513-byte stub.]

This module is a pure function over the channel DOL bytes: no console data, key, ticket or
save is read, and nothing contacts a server.
"""
import hashlib

from .ppc_patch import assemble, to_file

# Virtual addresses inside content 1 (the channel DOL). build-v17 == build-v18 for c1.
GETTER_SRWI = 0x800509C8   # `srwi r3,r3,0x18` inside the country getter at 0x800509b4
RESUME = 0x800509CC        # the getter's `mtlr r0`; the cave returns here
CAVE = 0x800064BC          # 36-byte unreferenced text0 section-tail padding
CAVE_SIZE = 36

FROM_COUNTRY = 136         # Korea (console real country)
TO_COUNTRY = 49            # USA (what the service is shown)

# Exact bytes we overwrite. A base whose bytes differ is refused, never patched blind.
ORIG_SRWI = bytes.fromhex('5463463e')              # srwi r3,r3,0x18
ORIG_SRWI_SHA = hashlib.sha256(ORIG_SRWI).hexdigest()
ORIG_CAVE_SHA = hashlib.sha256(bytes(CAVE_SIZE)).hexdigest()


def code():
    """Return ``(cave_bytes, branch_bytes)``: the cave body and the 4-byte hook branch.

    The cave reproduces the replaced ``srwi`` (so the country byte is still extracted),
    then maps only 136 -> 49 and branches back into the getter. It touches r3 and cr0
    only; cr0 is caller-volatile across the surrounding ``bl``, so clobbering it is safe,
    and the getter's saved LR (in r0, reloaded before the hook) is never touched.
    """
    # One assembly unit so the local `keep` label resolves; `resume` is an absolute symbol.
    cave = assemble(
        'srwi r3,r3,24\n'                  # country = IPL.SADR byte 0 (the replaced insn)
        'cmplwi r3,%d\n' % FROM_COUNTRY +
        'bne keep\n'
        'li r3,%d\n' % TO_COUNTRY +
        'keep:\n'
        'b resume\n',
        CAVE, {'resume': RESUME})
    branch = assemble('b cave\n', GETTER_SRWI, {'cave': CAVE})
    if len(cave) > CAVE_SIZE or len(branch) != 4:
        raise ValueError('Country bridge does not fit its cave')
    return cave, branch


def code_constant():
    """Revision 20: the one replacement instruction, ``li r3,49`` (no cave)."""
    insn = assemble('li r3,%d\n' % TO_COUNTRY, GETTER_SRWI, {})
    if len(insn) != 4:
        raise ValueError('Constant country instruction must be exactly one word')
    return insn


def patch_constant(dol):
    """Return a new DOL whose country getter returns 49, changing exactly one instruction.

    Boot-safe by construction: no cave, no section, same length and section table; only the
    4 bytes of ``srwi r3,r3,24`` at 0x800509c8 change. The reader call stays untouched.
    """
    buf = bytearray(dol)
    at = to_file(buf, GETTER_SRWI)
    if hashlib.sha256(bytes(buf[at:at + 4])).hexdigest() != ORIG_SRWI_SHA:
        raise ValueError('Unexpected country-getter instruction; base DOL changed')
    length = len(dol)
    buf[at:at + 4] = code_constant()
    if len(buf) != length:
        raise ValueError('Country constant changed DOL length')
    return bytes(buf)


def patch(dol):
    """Return a new DOL with the disguise applied, verifying the exact originals first.

    In-place only: one instruction in the country getter and bytes inside the dead cave.
    No section is added; the section table and the overall length are unchanged.
    """
    buf = bytearray(dol)
    srwi_at = to_file(buf, GETTER_SRWI)
    cave_at = to_file(buf, CAVE, CAVE_SIZE)
    if hashlib.sha256(bytes(buf[srwi_at:srwi_at + 4])).hexdigest() != ORIG_SRWI_SHA:
        raise ValueError('Unexpected country-getter instruction; base DOL changed')
    if hashlib.sha256(bytes(buf[cave_at:cave_at + CAVE_SIZE])).hexdigest() != ORIG_CAVE_SHA:
        raise ValueError('Dead cave is not empty; base DOL changed')
    cave, branch = code()
    length = len(dol)
    buf[cave_at:cave_at + len(cave)] = cave      # cave body (rest stays zero padding)
    buf[srwi_at:srwi_at + 4] = branch            # hook
    if len(buf) != length:
        raise ValueError('Country bridge changed DOL length')
    return bytes(buf)

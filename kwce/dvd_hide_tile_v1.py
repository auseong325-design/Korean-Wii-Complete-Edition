"""43K experimental memory-only DVD tile hiding; never changes title records."""
import hashlib
from pathlib import Path
from . import dvd_disc_banner_hook_v12 as base
from .dvd_disc_hook import _branch
from .ppc_patch import assemble, to_file

ROOT = Path(__file__).resolve().parents[1]
CAVE = 0x813BEC04
END = 0x813BF6A8  # unused Kitayama auto-test process_app_test
SITES = {0x813AB4C8: 0x813B1280, 0x813AB6C8: 0x813B12BC,
         0x813AB708: 0x813B12C4}
EVENT = 0x813AF5A4

SOURCE = '''
.globl _start
_start:
    li r3,0
    blr
hide_check:
    stwu r1,-32(r1)
    mflr r0
    stw r0,36(r1)
    cmpwi r3,0
    beq 2f
    lwz r4,0x1c(r3)
    lwz r5,0x20(r3)
    lis r3,0x8109
    lwz r3,-0x6f74(r3)
    cmpwi r3,0
    beq 2f
    bl getTitleID
    lis r0,1
    ori r0,r0,1
    cmpw r3,r0
    bne 2f
    lis r0,0x4b44
    ori r0,r0,0x5644
    cmpw r4,r0
    bne 2f
    li r3,1
    b 3f
2:  li r3,0
3:  lwz r0,36(r1)
    mtlr r0
    addi r1,r1,32
    blr
.macro DRAW label,target
\\label:
    stwu r1,-32(r1)
    mflr r0
    stw r0,36(r1)
    stw r31,28(r1)
    mr r31,r3
    bl hide_check
    cmpwi r3,0
    bne 4f
    mr r3,r31
    bl \\target
4:  lwz r31,28(r1)
    lwz r0,36(r1)
    mtlr r0
    addi r1,r1,32
    blr
.endm
DRAW hide_thumbnail,thumbnail
DRAW hide_cursor,cursor
DRAW hide_balloon,balloon
hide_event:
    mr r28,r3
    bl hide_check
    cmpwi r3,0
    beq 5f
    b event_done
5:
    mr r3,r28
    cmpwi r27,2
    b event_resume
'''
SYMBOLS = dict(getTitleID=0x81337740, thumbnail=0x813B1280,
               cursor=0x813B12BC, balloon=0x813B12C4,
               event_done=0x813AF76C, event_resume=EVENT+4)


def compiled():
    code = assemble(SOURCE, CAVE, SYMBOLS)
    if len(code) > END-CAVE or len(code) % 4:
        raise ValueError('DVD hiding code exceeds its reserved area')
    labels = {}
    for name in ('hide_thumbnail', 'hide_cursor', 'hide_balloon', 'hide_event'):
        if name.startswith('hide_') and name != 'hide_event':
            marker = SOURCE.replace('DRAW '+name+',', '.long 0x4b41ffff\nDRAW '+name+',')
        else:
            marker = SOURCE.replace('hide_event:', '.long 0x4b41ffff\nhide_event:')
        probe = assemble(marker, CAVE, SYMBOLS)
        at = probe.find(bytes.fromhex('4b41ffff'))
        if at < 0 or at % 4: raise ValueError('Missing DVD hiding entry')
        labels[name] = CAVE + at
    return code, labels


def patch(menu):
    original = (ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    off = to_file(menu, CAVE)
    oldoff = to_file(original, CAVE)
    if menu[off:off+END-CAVE] != original[oldoff:oldoff+END-CAVE]:
        raise ValueError('DVD hiding cave is not original 43K code')
    for at, target in SITES.items():
        if menu[to_file(menu, at):to_file(menu, at)+4] != _branch(at, target, True):
            raise ValueError('DVD hiding draw call differs')
    if menu[to_file(menu, EVENT):to_file(menu, EVENT)+4] != bytes.fromhex('2c1b0002'):
        raise ValueError('DVD hiding event instruction differs')
    data, record = base.patch_dvd_banner_hook(menu)
    result = bytearray(data)
    code, labels = compiled()
    result[off:off+len(code)] = code
    for at, name in zip(SITES, ('hide_thumbnail','hide_cursor','hide_balloon')):
        result[to_file(result,at):to_file(result,at)+4] = _branch(at, labels[name], True)
    result[to_file(result,EVENT):to_file(result,EVENT)+4] = _branch(EVENT, labels['hide_event'])
    record.update(hide_tile=True, hide_cave=hex(CAVE), hide_bytes=len(code),
                  hide_source_sha256=hashlib.sha256(SOURCE.encode()).hexdigest())
    return bytes(result), record

"""Disc channel -> KWCE DVD player (43K v518 System Menu, instruction words only).

Behaviour: when the disc channel shows an unreadable/unknown disc (the state a
DVD-Video disc ends in) and the DVD player channel is on the Wii Menu, the
"시작" button is enabled; pressing it starts the DVD player through the normal
channel launch path (fade-out, cleanup, play record), by pointing the channel
title scene at the player's tile just before reserveNextScene runs.

Code lives in the unused debug scene KitayamaTest::calcNormal (0x740 bytes;
only created by a debug scene ID), whose entry now returns 0. Four call sites:
  isEnableToExecute entry      -> b  kwce_is_enable
  reserveNextScene entry       -> b  kwce_reserve
  mDiskState = INVALID_IDLE    -> bl kwce_set_invalid_idle  (+ changeStartButton)
  mDiskState = INVALID_EJECT   -> bl kwce_set_invalid_eject (+ changeStartButton)
Addresses come from the wii-ipl 43K symbol map and are checked against the
original instruction words before patching.
"""
import hashlib,struct
from .ppc_patch import assemble,to_file
from .patches import MENU_SHA1

DVD_TITLE=0x000100014B445644  # 00010001-KDVD
CAVE=0x813BD5C8; CAVE_SIZE=0x740
SITES={  # address: expected original word
    0x813B8D9C:0x9421FFE0,  # isEnableToExecute: stwu r1,-0x20(r1)
    0x813B8844:0x9421FFE0,  # reserveNextScene:  stwu r1,-0x20(r1)
    0x813B8298:0x901A0074,  # updateDiskState: stw r0,0x74(r26)  (r0 = 16, INVALID_IDLE)
    0x813B8334:0x901A0074,  # updateDiskState: stw r0,0x74(r26)  (r0 = 17, INVALID_EJECT)
}
SYMBOLS=dict(getSceneID=0x813B1564,getTitleID=0x81337740,changeStartButton=0x813B8ED0,
             is_enable_body=0x813B8DA0,reserve_body=0x813B8848)
CHANNEL_MANAGER=0x8108908C  # System::smArg.mpChannelManager (smArg 0x81089008 + 0x84)

def _cave_source():
    hi,lo=DVD_TITLE>>32,DVD_TITLE&0xffffffff
    mgr_ha=(CHANNEL_MANAGER+0x8000)>>16;mgr_lo=CHANNEL_MANAGER-(mgr_ha<<16)
    return f'''
    .globl _start
_start:                         # KitayamaTest::calcNormal: debug scene, returns immediately
    li r3,0
    blr

# int kwce_find_dvd(void): (page<<8)|index of the DVD player tile, or -1
kwce_find_dvd:
    stwu r1,-32(r1)
    mflr r0
    stw r0,36(r1)
    stw r31,28(r1)
    stw r30,24(r1)
    li r31,0                    # page
1:  li r30,0                    # index
2:  lis r3,{mgr_ha}
    lwz r3,{mgr_lo}(r3)
    mr r4,r31
    mr r5,r30
    bl getTitleID
    lis r0,{hi>>16}
    ori r0,r0,{hi&0xffff}
    cmpw r3,r0
    bne 3f
    lis r0,{lo>>16}
    ori r0,r0,{lo&0xffff}
    cmpw r4,r0
    bne 3f
    slwi r3,r31,8
    or r3,r3,r30
    b 9f
3:  addi r30,r30,1
    cmpwi r30,12
    blt 2b
    addi r31,r31,1
    cmpwi r31,4
    blt 1b
    li r3,-1
9:  lwz r30,24(r1)
    lwz r31,28(r1)
    lwz r0,36(r1)
    mtlr r0
    addi r1,r1,32
    blr

# int kwce_disk_dvd(ChannelTitle* this): tile index if the disc channel shows an unknown disc
kwce_disk_dvd:
    lwz r0,0x74(r3)             # mDiskState
    cmpwi r0,16                 # DISK_STATE_INVALID_IDLE
    li r0,-1
    bne 8f
    stwu r1,-16(r1)
    mflr r0
    stw r0,20(r1)
    stw r31,12(r1)
    mr r31,r3
    lis r3,{mgr_ha}
    lwz r3,{mgr_lo}(r3)
    lwz r4,0x60(r31)            # mChanPage
    lwz r5,0x64(r31)            # mChanIndex
    bl getSceneID
    cmpwi r3,15                 # SCENE_DISK_CHANNEL
    li r3,-1
    bne 7f
    bl kwce_find_dvd
7:  lwz r31,12(r1)
    lwz r0,20(r1)
    mtlr r0
    addi r1,r1,16
    blr
8:  mr r3,r0
    blr

# bool ChannelTitle::isEnableToExecute(int page, int index)
kwce_is_enable:
    stwu r1,-32(r1)
    mflr r0
    stw r0,36(r1)
    stw r3,8(r1)
    stw r4,12(r1)
    stw r5,16(r1)
    bl kwce_disk_dvd
    cmpwi r3,0
    lwz r5,16(r1)
    lwz r4,12(r1)
    lwz r3,8(r1)
    lwz r0,36(r1)
    mtlr r0
    addi r1,r1,32
    blt 1f
    li r3,1                     # start button enabled: the DVD player will be launched
    blr
1:  stwu r1,-0x20(r1)           # original first instruction
    b is_enable_body

# void ChannelTitle::reserveNextScene()
kwce_reserve:
    stwu r1,-16(r1)
    mflr r0
    stw r0,20(r1)
    stw r31,12(r1)
    mr r31,r3
    bl kwce_disk_dvd
    cmpwi r3,0
    blt 1f
    srwi r4,r3,8
    clrlwi r5,r3,24
    stw r4,0x60(r31)            # the normal channel path now launches the DVD player tile
    stw r5,0x64(r31)
1:  mr r3,r31
    lwz r31,12(r1)
    lwz r0,20(r1)
    mtlr r0
    addi r1,r1,16
    stwu r1,-0x20(r1)           # original first instruction
    b reserve_body

# mDiskState = INVALID_IDLE / INVALID_EJECT, then redraw the start button
kwce_set_invalid_idle:
kwce_set_invalid_eject:
    stw r0,0x74(r26)            # original store (r26 = this)
    stwu r1,-144(r1)
    mflr r0
    stw r0,148(r1)
    stmw r3,8(r1)               # keep every register the switch could still use (r3-r31: 116 bytes)
    mr r3,r26
    bl changeStartButton
    lmw r3,8(r1)
    lwz r0,148(r1)
    mtlr r0
    lwz r0,0x74(r26)
    addi r1,r1,144
    blr
'''

def _assemble():
    code=assemble(_cave_source(),CAVE,SYMBOLS)
    if len(code)>CAVE_SIZE:raise ValueError('DVD hook exceeds the code cave')
    return code

def _labels(code):
    """Addresses of the entry labels (re-assembled with marker words to locate them)."""
    names=['kwce_is_enable','kwce_reserve','kwce_set_invalid_idle']
    src=_cave_source()
    out={}
    for name in names:
        probe=src.replace(f'\n{name}:',f'\n{name}:\n    .long 0x4b41ffff')  # unique marker
        blob=assemble(probe,CAVE,SYMBOLS);at=blob.find(bytes.fromhex('4b41ffff'))
        if at<0 or at%4:raise ValueError('label probe failed')
        out[name]=CAVE+at
    return out

def _branch(at,target,link=False):
    return assemble(f'    .globl _start\n_start:\n    {"bl" if link else "b"} target\n',at,dict(target=target))

def patch_dvd_hook(menu):
    """Return the menu DOL with the hook applied (the input may already carry other KWCE patches)."""
    out=bytearray(menu)
    for address,word in SITES.items():
        if struct.unpack_from('>I',menu,to_file(menu,address))[0]!=word:raise ValueError(f'Unexpected instruction at {address:#x}')
    code=_assemble();labels=_labels(code)
    cave=to_file(menu,CAVE)
    if menu[cave:cave+8]!=bytes.fromhex('9421fec07c0802a6'):raise ValueError('Code cave is not the original KitayamaTest::calcNormal')
    out[cave:cave+len(code)]=code
    for address,target,link in [(0x813B8D9C,labels['kwce_is_enable'],False),(0x813B8844,labels['kwce_reserve'],False),
                                (0x813B8298,labels['kwce_set_invalid_idle'],True),(0x813B8334,labels['kwce_set_invalid_idle'],True)]:
        out[to_file(menu,address):to_file(menu,address)+4]=_branch(address,target,link)
    return bytes(out),dict(feature='disc channel unknown disc -> DVD player channel',title_id=f'{DVD_TITLE:016x}',cave=hex(CAVE),
                           cave_bytes=len(code),sites=[hex(a) for a in SITES],menu_sha1=hashlib.sha1(menu).hexdigest())

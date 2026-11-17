"""43K memory-only DVD banner loader; reads KDVD banner through native async APIs.

Keeps the disc channel's page/index and existing launch hook. No NAND writes.
The original disc scene, eject handling and ordinary Wii/GC loading are restored
when the drive no longer reports BAD_DISK. The normal scene destructor owns the
loaded resources if the user exits or changes channel before an eject.
"""
import hashlib,struct
from . import dvd_disc_hook as old
from .ppc_patch import assemble,to_file

UPDATE=0x813B7A00
SYMBOLS=dict(old.SYMBOLS,OSReport=0x81507458,load_layout=0x813B917C,finished=0x8133BA54,check_data=0x8133BA10,
             create_module=0x813B57A8,create_disk=0x813B55BC,finish_binding=0x813699C8,
             destroy_layout=0x8136A194,delete_sound=0x8133A94C,delete_file=0x8133BB18,update_body=UPDATE+4,layout_calc=0x81369A98,find_pane=0x814F7E64)

def source(first_word):
    s=old._cave_source()
    anchor='    bl changeStartButton\n'
    assert s.count(anchor)==1
    s=s.replace(anchor,anchor+'    mr r3,r26\n    bl kwce_begin_banner\n')
    return s+f'''
# Called after entering INVALID_IDLE; the standard start/launch hook stays intact.
kwce_begin_banner:
    stwu r1,-48(r1)
    mflr r0
    stw r0,52(r1)
    stmw r29,36(r1)
    mr r31,r3
    bl kwce_disk_dvd
    cmpwi r3,0
    blt begin_end
    mr r29,r3
    lis r30,kwce_context@ha
    addi r30,r30,kwce_context@l
    lwz r0,0(r30)
    cmpw r0,r31
    bne begin_new
    lwz r0,8(r30)
    cmpwi r0,0
    bne begin_end
begin_new:
    stw r31,0(r30)
    lwz r0,0x218(r31)
    slwi r0,r0,2
    add r9,r31,r0
    mr r3,r31
    srwi r4,r29,8
    clrlwi r5,r29,24
    addi r6,r9,0x224
    addi r7,r9,0x22c
    addi r8,r9,0x234
    bl load_layout
    cmpwi r3,0
    beq begin_end
    stw r3,4(r30)
    lwz r0,0x218(r31)
    slwi r0,r0,2
    add r9,r31,r0
    stw r3,0x21c(r9)
    li r0,1
    stw r0,8(r30)
begin_end:
    lmw r29,36(r1)
    lwz r0,52(r1)
    mtlr r0
    addi r1,r1,48
    blr

# updateDiskState wrapper. r3/r4/r5 are restored before the original body.
kwce_update:
    stwu r1,-48(r1)
    mflr r0
    stw r0,52(r1)
    stw r3,8(r1)
    stw r4,12(r1)
    stw r5,16(r1)
    stmw r29,36(r1)
    mr r31,r3
    lis r30,kwce_context@ha
    addi r30,r30,kwce_context@l
    stw r31,16(r30)
update_no_trace:
    lwz r0,0(r30)
    cmpw r0,r31
    bne update_original
    lwz r0,0x74(r31)
    cmpwi r0,16
    bne update_forget
    lwz r29,0x218(r31)
    slwi r29,r29,2
    add r29,r31,r29
    lwz r3,0x21c(r29)
    lwz r0,4(r30)
    cmpw r3,r0
    bne update_forget
    bl finished
    cmpwi r3,0
    beq update_handled
    # Drive state is public menu state, not a console identity.
    lis r3,0x8109
    lwz r3,-0x6f50(r3)          # System::smArg.mpBS2Manager = 0x810890b0
    lwz r0,4(r3)
    cmpwi r0,7                 # BAD_DISK
    bne update_restore
    lwz r0,8(r30)
    cmpwi r0,2
    beq update_handled
    lwz r3,4(r30)
    bl check_data
    cmpwi r3,1
    bne update_restore
    mr r3,r31
    bl create_module
    lwz r3,0x23c(r31)
    cmpwi r3,0
    beq update_restore
    bl finish_binding
    lwz r3,0x254(r31)
    lwz r3,0x14(r3)
    lbz r0,0xcf(r3)
    rlwinm r0,r0,0,24,30
    stb r0,0xcf(r3)
    li r0,2
    stw r0,8(r30)
    b update_handled
update_restore:
    lwz r3,0x23c(r31)
    lwz r0,0x254(r31)
    cmpw r3,r0
    beq restore_file
    cmpwi r3,0
    beq restore_file
    bl destroy_layout
restore_file:
    li r0,0
    stw r0,0x23c(r31)
    stw r0,0x240(r31)
    stw r0,0x244(r31)
    stw r0,0x248(r31)
    lwz r3,4(r30)
    li r4,1
    bl delete_file
    lwz r3,0x22c(r29)
    cmpwi r3,0
    beq restore_sound_done
    li r4,1
    bl delete_sound
restore_sound_done:
    li r0,0
    stw r0,0x22c(r29)
    lwz r0,0x250(r31)
    stw r0,0x21c(r29)
    li r0,0
    stw r0,0x224(r29)
    stw r0,0x234(r29)
    stw r0,0x74(r31)
    li r0,14                   # force the native INIT transition after eject
    stw r0,0x78(r31)
    mr r3,r31
    bl create_disk
update_forget:
    li r0,0
    stw r0,0(r30)
    stw r0,4(r30)
    stw r0,8(r30)
update_original:
    li r12,0
    b update_return
update_handled:
    li r12,1
update_return:
    lmw r29,36(r1)
    lwz r5,16(r1)
    lwz r4,12(r1)
    lwz r3,8(r1)
    lwz r0,52(r1)
    mtlr r0
    addi r1,r1,48
    cmpwi r12,0
    bnelr
    .long {first_word:#x}
    b update_body

    .balign 4
kwce_context:
    .long 0,0,0,0,0,0,0,0

# The menu never binds G_DVD. After its normal animation pass, mirror the
# native Wii parent transforms with the original DVD x offset (-180), and
# recompute matrices without running animations a second time.
kwce_disk_calc:
    stwu r1,-48(r1)
    mflr r0
    stw r0,52(r1)
    stmw r27,28(r1)
    mr r31,r3
    bl layout_calc
    lwz r30,0x14(r31)
    lis r29,kwce_pairs@ha
    addi r29,r29,kwce_pairs@l
    li r28,3
copy_parent:
    mr r3,r30
    lwz r4,0(r29)
    li r5,1
    bl find_pane
    mr r27,r3
    mr r3,r30
    lwz r4,4(r29)
    li r5,1
    bl find_pane
    cmpwi r3,0
    beq copy_next
    cmpwi r27,0
    beq copy_next
    li r4,0x2c
    li r5,8
    mtctr r5
copy_float:
    lfsx f0,r3,r4
    stfsx f0,r27,r4
    addi r4,r4,4
    bdnz copy_float
    lfs f0,0x2c(r27)
    lis r4,kwce_offset@ha
    lfs f1,kwce_offset@l(r4)
    fsubs f0,f0,f1
    stfs f0,0x2c(r27)
    lbz r0,0xcd(r3)
    stb r0,0xcd(r27)
    lbz r0,0xcf(r3)
    stb r0,0xcf(r27)
copy_next:
    addi r29,r29,8
    addic. r28,r28,-1
    bne copy_parent
    mr r3,r30
    lis r4,kwce_dvd_face@ha
    addi r4,r4,kwce_dvd_face@l
    li r5,1
    bl find_pane
    mr r27,r3
    mr r3,r30
    lis r4,kwce_wii_face@ha
    addi r4,r4,kwce_wii_face@l
    li r5,1
    bl find_pane
    cmpwi r3,0
    beq copy_done
    cmpwi r27,0
    beq copy_done
    lfs f0,0x40(r3)
    stfs f0,0x40(r27)
copy_done:
    mr r3,r30
    addi r4,r31,0x298
    lwz r12,0(r3)
    lwz r12,0x10(r12)
    mtctr r12
    bctrl
    lmw r27,28(r1)
    lwz r0,52(r1)
    mtlr r0
    addi r1,r1,48
    blr
kwce_pairs:
    .long kwce_dvd_parent,kwce_wii_parent,kwce_dvd_ref,kwce_wii_ref,kwce_dvd_shadow,kwce_wii_shadow
kwce_offset: .float 180.0
kwce_dvd_parent: .asciz "N_DVD0"
kwce_wii_parent: .asciz "N_Wii0"
kwce_dvd_ref: .asciz "N_RefDVD"
kwce_wii_ref: .asciz "N_RefWii"
kwce_dvd_shadow: .asciz "SahdeDVD"
kwce_wii_shadow: .asciz "ShadeWii"
kwce_dvd_face: .asciz "DVDDisk"
kwce_wii_face: .asciz "WiiDisk"
    .balign 4
'''

def patch_dvd_banner_hook(menu):
    from pathlib import Path
    reference=(Path(__file__).resolve().parents[1]/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    at=to_file(menu,UPDATE);expected=reference[to_file(reference,UPDATE):to_file(reference,UPDATE)+4]
    if menu[at:at+4]!=expected:raise ValueError('DVD banner update entry differs')
    call=0x813B415C
    if menu[to_file(menu,call):to_file(menu,call)+4]!=old._branch(call,0x81369A98,True):raise ValueError('Native disc layout calc call differs')
    first=struct.unpack('>I',expected)[0]
    if first>>16!=0x9421:raise ValueError('Unexpected update prologue')
    src=source(first);code=assemble(src,old.CAVE,SYMBOLS)
    if len(code)>old.CAVE_SIZE:raise ValueError('DVD banner hook exceeds debug cave')
    # Let v1 validate all existing sites and the untouched cave first.
    out,record=old.patch_dvd_hook(menu);out=bytearray(out)
    cave=to_file(menu,old.CAVE);out[cave:cave+len(code)]=code
    names=['kwce_is_enable','kwce_reserve','kwce_set_invalid_idle','kwce_update','kwce_disk_calc'];labels={}
    for name in names:
        marked=assemble(src.replace('\n'+name+':','\n'+name+':\n    .long 0x4b41ffff'),old.CAVE,SYMBOLS)
        offset=marked.find(bytes.fromhex('4b41ffff'))
        if offset<0 or offset%4:raise ValueError('DVD banner label probe failed')
        labels[name]=old.CAVE+offset
    for address,name,link in [(0x813B8D9C,'kwce_is_enable',False),(0x813B8844,'kwce_reserve',False),
                              (0x813B8298,'kwce_set_invalid_idle',True),(0x813B8334,'kwce_set_invalid_idle',True),
                              (UPDATE,'kwce_update',False),(0x813B415C,'kwce_disk_calc',True)]:
        offset=to_file(menu,address);out[offset:offset+4]=old._branch(address,labels[name],link)
    record.update(hook_revision=9,feature='DVD player launch plus native async KDVD banner in the disc scene',
                  cave_bytes=len(code),sites=[*record['sites'],hex(UPDATE),hex(0x813B415C)],nand_writes=False)
    return bytes(out),record

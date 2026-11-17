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
             destroy_layout=0x8136A194,delete_file=0x8133BB18,update_body=UPDATE+4)

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
    lwz r0,0x74(r31)
    stw r0,20(r30)
    lis r3,0x8109
    lwz r3,-0x6f50(r3)
    lwz r0,4(r3)
    stw r0,24(r30)
    lwz r0,12(r30)
    addi r0,r0,1
    stw r0,12(r30)
    dcbf 0,r30
    cmpwi r0,120
    blt update_no_trace
    li r0,0
    stw r0,12(r30)
    bl kwce_find_dvd
    mr r7,r3
    lwz r4,0x74(r31)
    lis r3,0x8109
    lwz r3,-0x6f50(r3)
    lwz r5,4(r3)
    lwz r6,8(r30)
    lis r3,kwce_trace_text@ha
    addi r3,r3,kwce_trace_text@l
    crclr 6
    bl OSReport
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
    dcbf 0,r30
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
kwce_trace_text:
    .asciz "KWCE_DVDBNR state=%d drive=%d stage=%d tile=%d\\n"
    .balign 4
'''

def patch_dvd_banner_hook(menu):
    from pathlib import Path
    reference=(Path(__file__).resolve().parents[1]/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    at=to_file(menu,UPDATE);expected=reference[to_file(reference,UPDATE):to_file(reference,UPDATE)+4]
    if menu[at:at+4]!=expected:raise ValueError('DVD banner update entry differs')
    first=struct.unpack('>I',expected)[0]
    if first>>16!=0x9421:raise ValueError('Unexpected update prologue')
    src=source(first);code=assemble(src,old.CAVE,SYMBOLS)
    if len(code)>old.CAVE_SIZE:raise ValueError('DVD banner hook exceeds debug cave')
    # Let v1 validate all existing sites and the untouched cave first.
    out,record=old.patch_dvd_hook(menu);out=bytearray(out)
    cave=to_file(menu,old.CAVE);out[cave:cave+len(code)]=code
    names=['kwce_is_enable','kwce_reserve','kwce_set_invalid_idle','kwce_update'];labels={}
    for name in names:
        marked=assemble(src.replace('\n'+name+':','\n'+name+':\n    .long 0x4b41ffff'),old.CAVE,SYMBOLS)
        offset=marked.find(bytes.fromhex('4b41ffff'))
        if offset<0 or offset%4:raise ValueError('DVD banner label probe failed')
        labels[name]=old.CAVE+offset
    for address,name,link in [(0x813B8D9C,'kwce_is_enable',False),(0x813B8844,'kwce_reserve',False),
                              (0x813B8298,'kwce_set_invalid_idle',True),(0x813B8334,'kwce_set_invalid_idle',True),
                              (UPDATE,'kwce_update',False)]:
        offset=to_file(menu,address);out[offset:offset+4]=old._branch(address,labels[name],link)
    record.update(hook_revision=2,feature='DVD player launch plus native async KDVD banner in the disc scene',
                  cave_bytes=len(code),sites=[*record['sites'],hex(UPDATE)],nand_writes=False)
    return bytes(out),record

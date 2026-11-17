# Position independent, no calls and no use of the old menu stack.
# r3 = verified complete DOL in reserved MEM2. Only MEM1 targets accepted by
# the caller. Executed after SDK shutdown, with interrupts already disabled.
.text
.globl kwce_relocate
kwce_relocate:
    mr r31,r3
    lwz r30,0xe0(r31)
    li r29,0
section:
    slwi r28,r29,2
    add r27,r31,r28
    lwz r5,0x90(r27)
    cmpwi r5,0
    beq next
    lwz r4,0x48(r27)
    lwz r6,0(r27)
    add r6,r31,r6
    mr r7,r4
    mr r8,r5
    mtctr r5
copy:
    lbz r9,0(r6)
    stb r9,0(r7)
    addi r6,r6,1
    addi r7,r7,1
    bdnz copy
    bl flush
next:
    addi r29,r29,1
    cmpwi r29,18
    blt section
    lwz r4,0xd8(r31)
    lwz r5,0xdc(r31)
    cmpwi r5,0
    beq launch
    mr r7,r4
    mr r8,r5
    li r9,0
    mtctr r5
zero:
    stb r9,0(r7)
    addi r7,r7,1
    bdnz zero
    bl flush
launch:
    sync
    isync
    li r3,0
    li r4,0
    mtctr r30
    bctr
flush:
    # Include the first/last partial cache lines.
    add r8,r4,r5
    rlwinm r7,r4,0,0,26
flush_d:
    dcbf 0,r7
    addi r7,r7,32
    cmplw r7,r8
    blt flush_d
    sync
    rlwinm r7,r4,0,0,26
flush_i:
    icbi 0,r7
    addi r7,r7,32
    cmplw r7,r8
    blt flush_i
    sync
    isync
    blr

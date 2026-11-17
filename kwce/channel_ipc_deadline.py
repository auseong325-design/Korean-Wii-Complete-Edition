"""Bound small WC24 IPC calls without abandoning IOS-owned stack buffers.

The channel's SDK used IOS_Ioctl and could sleep before reaching SOStartupEx's
deadline. This adapter retains native request/result semantics and uses its IOS
async ABI. Persistent aligned buffers remain occupied until BOTH the late ioctl
and async close callbacks complete. A timeout is an IPC error, never success.
"""
import hashlib
import json
import struct
from pathlib import Path
from .ppc_patch import assemble, sections, to_file

ROOT = Path(__file__).resolve().parents[1]


def code(row, polls=300, native_ioctls=(), long_ioctls=()):
    start = int(row['cave'], 16)
    symbols = {k: int(row[k], 16) for k in
               ('ioctl_async', 'close_async', 'disable', 'restore', 'sleep')}
    symbols.update(native_ioctl=int(row['ioctl'],16)+4,
                   native_close=int(row['close'],16)+4)
    # Commands that must NOT be bounded: a long-running call (e.g. the News
    # download ioctl) reaches IOS with small buffers, so the size test below
    # would wrongly bound it and the 30s cap returns -42 (= error 107242).
    # Route those to the native synchronous path -- exactly retail semantics,
    # so this adds no new section and cannot corrupt memory or boot. r5 holds
    # the ioctl command at entry and is not clobbered before the size checks.
    exempt = ''.join(f'    cmplwi r5,{int(c)}\n    beq ioctl_native\n'
                     for c in native_ioctls)
    # Commands that need a LONGER but still finite bound (News v24: the download ioctl gets
    # 10 minutes instead of 30 s, so a stalled download ends in 107242 instead of an endless
    # 'downloading' screen, as hardware showed with v23's unbounded native path). r25 = command.
    longcap = ''.join(f'    cmplwi r25,{int(c)}\n    bne long_skip_{i}\n    li r30,{int(n)}\nlong_skip_{i}:\n'
                      for i, (c, n) in enumerate(long_ioctls))
    if any(not 0 < int(n) <= 32767 for _, n in long_ioctls):
        raise ValueError('long poll count must fit li')
    # state: busy, fd, ioctl_done, close_done, detached, result, close_queued.
    # Input/output are cache-line aligned and are never caller stack addresses.
    source = f'''
ioctl_entry:
{exempt}    cmplwi r7,32
    bgt ioctl_native
    cmplwi r9,256
    bgt ioctl_native
    stwu r1,-128(r1)
    mflr r0
    stw r0,132(r1)
    stmw r24,80(r1)
    mr r24,r4
    mr r25,r5
    mr r26,r6
    mr r27,r7
    mr r28,r8
    mr r29,r9
    lis r31,state@ha
    addi r31,r31,state@l
    bl disable
    lwz r0,0(r31)
    cmpwi r0,0
    bne occupied
    li r0,1
    stw r0,0(r31)
    stw r24,4(r31)
    li r0,0
    stw r0,8(r31)
    stw r0,12(r31)
    stw r0,16(r31)
    stw r0,20(r31)
    stw r0,24(r31)
    bl restore
    li r10,0
    addi r11,r31,64
copy_in:
    cmplw r10,r27
    bge clear_output
    lbz r0,0(r26)
    stb r0,0(r11)
    addi r26,r26,1
    addi r11,r11,1
    addi r10,r10,1
    b copy_in
clear_output:
    addi r11,r31,96
    li r10,256
    li r0,0
clear_next:
    stb r0,0(r11)
    addi r11,r11,1
    addi r10,r10,-1
    cmpwi r10,0
    bne clear_next
    mr r3,r24
    mr r4,r25
    li r5,0
    cmpwi r27,0
    beq no_input
    addi r5,r31,64
no_input:
    mr r6,r27
    li r7,0
    cmpwi r29,0
    beq no_output
    addi r7,r31,96
no_output:
    mr r8,r29
    lis r9,ioctl_callback@ha
    addi r9,r9,ioctl_callback@l
    mr r10,r31
    bl ioctl_async
    cmpwi r3,0
    blt enqueue_failed
    li r30,{polls}
{longcap}wait_result:
    bl disable
    lwz r0,8(r31)
    cmpwi r0,0
    bne completed
    cmpwi r30,0
    beq timed_out
    bl restore
    # 100ms, full 64-bit tick argument. Original SDK bus clock contract.
    lis r3,0x8000
    lwz r4,248(r3)
    srwi r4,r4,2
    lis r3,0x1062
    ori r3,r3,0x4dd3
    mulhwu r4,r3,r4
    srwi r4,r4,6
    mulli r4,r4,100
    li r3,0
    bl sleep
    addi r30,r30,-1
    b wait_result
timed_out:
    li r0,1
    stw r0,16(r31)
    bl restore
    li r3,-42
    b ioctl_return
completed:
    bl restore
    lwz r30,20(r31)
    cmpwi r30,0
    blt enqueue_failed
    li r10,0
    addi r11,r31,96
copy_out:
    cmplw r10,r29
    bge completed_ok
    lbz r0,0(r11)
    stb r0,0(r28)
    addi r11,r11,1
    addi r28,r28,1
    addi r10,r10,1
    b copy_out
completed_ok:
    li r0,0
    stw r0,0(r31)
    li r3,0
    b ioctl_return
enqueue_failed:
    li r0,0
    stw r0,0(r31)
    li r3,-42
    b ioctl_return
occupied:
    bl restore
    li r3,-42
ioctl_return:
    lmw r24,80(r1)
    lwz r0,132(r1)
    mtlr r0
    addi r1,r1,128
    blr
ioctl_native:
    stwu r1,-16(r1)
    b native_ioctl
close_entry:
    lis r12,state@ha
    addi r12,r12,state@l
    lwz r0,0(r12)
    cmpwi r0,0
    beq close_native
    lwz r0,16(r12)
    cmpwi r0,0
    beq close_native
    lwz r0,4(r12)
    cmpw r4,r0
    bne close_native
    # A timed-out call still owns its private buffers. Close without blocking.
    stwu r1,-32(r1)
    mflr r0
    stw r0,36(r1)
    mr r3,r4
    lis r4,close_callback@ha
    addi r4,r4,close_callback@l
    mr r5,r12
    bl close_async
    cmpwi r3,0
    li r3,0
    bge close_return
    li r3,-42
close_return:
    lwz r0,36(r1)
    mtlr r0
    addi r1,r1,32
    blr
close_native:
    stwu r1,-16(r1)
    b native_close
ioctl_callback:
    stw r3,20(r4)
    li r0,1
    stw r0,8(r4)
    b release_if_detached
close_callback:
    # Keep ownership if close failed; never reuse potentially IOS-owned storage.
    cmpwi r3,0
    blt callback_return
    li r0,1
    stw r0,12(r4)
release_if_detached:
    lwz r0,16(r4)
    cmpwi r0,0
    beq callback_return
    lwz r0,8(r4)
    cmpwi r0,0
    beq callback_return
    lwz r0,12(r4)
    cmpwi r0,0
    beq callback_return
    li r0,0
    stw r0,0(r4)
callback_return:
    li r3,0
    blr
    .balign 32
state:
    .space 352,0
'''
    blob = assemble(source, start, symbols)
    # Marker addresses are derived from fixed, uniquely assembled instruction
    # sequences; no build assumes a hard-coded offset into an assembly listing.
    close_marker = assemble('lis r12,state@ha\naddi r12,r12,state@l', start,
                            {'state': start+len(blob)-352})
    close_off = blob.find(close_marker)
    if close_off < 0 or blob.find(close_marker, close_off+1) >= 0:
        raise ValueError('Unique close entry marker missing')
    return blob, dict(ioctl=start, close=start+close_off,
                      state=start+len(blob)-352)


def branch(at, target):
    delta = target-at
    if delta%4 or not -0x2000000 <= delta < 0x2000000:
        raise ValueError('IPC adapter branch range')
    return struct.pack('>I',0x48000000|(delta&0x3fffffc))


def patch(raw, channel, native_ioctls=(), long_ioctls=()):
    cfg=json.loads((ROOT/'configs/channel-ipc-deadline-v1.lock.json').read_text())
    row=cfg['channels'][channel];start=int(row['cave'],16);limit=row['cave_size']
    checks=[('cave',start,limit),('ioctl',int(row['ioctl'],16),0x48),
            ('close',int(row['close'],16),0x34)]
    checks += [(key,int(row[key],16),n) for key,n in
               [('ioctl_async',32),('close_async',32),('disable',16),('restore',16),('sleep',16)]]
    for name,va,n in checks:
        off=to_file(raw,va,n)
        if hashlib.sha256(raw[off:off+n]).hexdigest()!=row[name+'_sha256']:
            raise ValueError('Pinned IPC '+name+' differs')
    # No original absolute pointer or direct branch targets the reclaimed range.
    for i,off,va,n in sections(raw):
        if not off or off+n>len(raw):continue
        words=struct.unpack('>'+str(n//4)+'I',raw[off:off+n//4*4])
        for j,w in enumerate(words):
            if i>=7 and start<=w<start+limit:raise ValueError('IPC slot data reference')
            if i<7 and w>>26 in (16,18):
                mask,sign=(0xfffc,0x8000)if w>>26==16 else(0x3fffffc,0x2000000)
                d=w&mask;d=d-2*sign if d&sign else d
                target=d if w&2 else va+j*4+d
                if start<=target<start+limit:raise ValueError('IPC slot branch reference')
            if i<7 and w>>26==15 and (w>>16&31)==0:
                reg=w>>21&31;hi=(w&65535)<<16
                for v in words[j+1:j+10]:
                    op=v>>26;rt=v>>21&31;ra=v>>16&31;lo=v&65535
                    if op in (14,32,34,36,38) and ra==reg:
                        target=(hi+(lo if lo<32768 else lo-65536))&0xffffffff
                        if start<=target<start+limit:raise ValueError('IPC slot address reference')
                    if op==24 and rt==reg and start<=hi+(v&65535)<start+limit:
                        raise ValueError('IPC slot immediate reference')
                    if op in (14,15,32,34,46) and rt==reg:break
                    if op in (24,25,31) and ra==reg:break
    blob,labels=code(row,cfg['polls'],native_ioctls,long_ioctls)
    if len(blob)>limit:raise ValueError('IPC adapter exceeds reviewed slot')
    result=bytearray(raw);off=to_file(raw,start,len(blob));result[off:off+len(blob)]=blob
    for name in ('ioctl','close'):
        va=int(row[name],16);off=to_file(raw,va)
        if raw[off:off+4]!=bytes.fromhex('9421fff0'):raise ValueError('IPC entry prologue')
        result[off:off+4]=branch(va,labels[name])
    return bytes(result),dict(timeout_seconds=cfg['polls']/10,bytes=len(blob),
        labels={k:hex(v)for k,v in labels.items()},input_limit=32,output_limit=256,
        native_request_and_result_semantics_preserved=True,
        late_reply_persistent_buffers=True,release_requires_ioctl_and_close=True,
        urls_credentials_signature_time_checks_unchanged=True,
        scope='WC24 small ioctl only; other IOS calls and HTTP are not globally bounded',
        native_ioctls=[int(c) for c in native_ioctls],
        hardware_verified=False,
        **({'long_ioctls':[[int(c),int(n),int(n)/10] for c,n in long_ioctls]} if long_ioctls else {}))

"""News foreground-load repair. Original signature/time/payload checks remain.

Five worker loops retried OpenLib BUSY/MUTEX/INPROGRESS forever, sleeping100ms.
Bound consecutive retries; first foreground request needs the current snapshot,
not all24 hourly snapshots. Native cache cleanup accepts the loaded prefix.
"""
import hashlib,json,struct
from pathlib import Path
from .ppc_patch import assemble,to_file

ROOT=Path(__file__).resolve().parents[1]
CAVE=0x801df210
LIMIT=200  # reviewed unused DVD debug-string slot, also used by old test variant
OPEN=0x80079024
RETRIES=[0x80041e30,0x800420f4,0x800422c0,0x8004246c,0x80042620]

def branch(site,target,link=False):
    distance=target-site
    if distance%4 or not -0x2000000<=distance<0x2000000:raise ValueError('News branch range')
    return struct.pack('>I',0x48000000|(distance&0x3fffffc)|int(link))

def code(retry_limit=300):
    source=f'''
retry_open:
    stwu r1,-16(r1)
    mflr r0
    stw r0,20(r1)
    bl open_lib
    lis r12,retry_count@ha
    lwz r11,retry_count@l(r12)
    cmpwi r3,-22
    beq busy
    cmpwi r3,-26
    beq busy
    cmpwi r3,-29
    beq busy
    li r11,0
    b store_count
busy:
    addi r11,r11,1
    cmplwi r11,{retry_limit}
    blt store_count
    li r11,0
    lis r3,-2
    ori r3,r3,23846
    stw r3,-28364(r13)  # SDK last error107226, same storage as native setter
    li r3,-31           # native network-error handling, not another retry
store_count:
    stw r11,retry_count@l(r12)
    lwz r0,20(r1)
    mtlr r0
    addi r1,r1,16
    blr
current_hour_mask:
    stwu r1,-64(r1)
    mflr r0
    stw r0,68(r1)
    addi r3,r1,8
    bl news_calendar
    lwz r0,16(r1)
    cmplwi r0,23
    li r3,1
    bgt mask_done
    slw r3,r3,r0
mask_done:
    lwz r0,68(r1)
    mtlr r0
    addi r1,r1,64
    blr
missing_cache_file:
    beq try_partial
    b cache_present
try_partial:
    cmpwi r29,0
    beq no_cache
    b cache_finish
no_cache:
    b cache_missing
retry_count:
    .long 0
'''
    payload=assemble(source,CAVE,dict(open_lib=OPEN,news_calendar=0x80076138,
        cache_present=0x80042f60,cache_finish=0x8004309c,cache_missing=0x80042ed8))
    if len(payload)>LIMIT:raise ValueError('News load hook exceeds reviewed slot')
    # Fixed labels are checked by assembler output length and branch destinations.
    return payload,dict(retry=CAVE,mask=CAVE+27*4,missing=CAVE+41*4)

def patch(raw):
    cfg=json.loads((ROOT/'configs/news-loading-v16.json').read_text())
    if hashlib.sha256(raw).hexdigest()!=cfg['executable_sha256']:raise ValueError('News v15 executable identity differs')
    at=to_file(raw,CAVE,LIMIT)
    if hashlib.sha256(raw[at:at+LIMIT]).hexdigest()!=cfg['cave_sha256']:raise ValueError('News debug slot differs')
    out=bytearray(raw);payload,labels=code(cfg['retry_limit'])
    # Assemble each entry marker independently; never assume C/ABI layout.
    for site in RETRIES:
        pos=to_file(out,site)
        if raw[pos:pos+4]!=branch(site,OPEN,True):raise ValueError('News retry call identity differs')
        out[pos:pos+4]=branch(site,labels['retry'],True)
    for site,old,new in [(0x80042044,0x3c800100,branch(0x80042044,labels['mask'],True)),
                         (0x80042048,0x38a4ffff,struct.pack('>I',0x7c651b78)),
                         (0x80042ed4,0x4082008c,branch(0x80042ed4,labels['missing']))]:
        pos=to_file(out,site)
        if int.from_bytes(raw[pos:pos+4],'big')!=old:raise ValueError('News foreground/cache instruction differs')
        out[pos:pos+4]=new
    out[at:at+len(payload)]=payload
    return bytes(out),dict(revision=16,cave=hex(CAVE),bytes=len(payload),retry_limit=cfg['retry_limit'],
        busy_wait_limit_seconds=30,foreground_hours=1,partial_cache_cleanup='native path after at least one loaded snapshot',
        signature_checks_preserved=True,timestamps_unchanged=True,service_urls_unchanged=True,
        source_sha256=hashlib.sha256(raw).hexdigest(),output_sha256=hashlib.sha256(out).hexdigest(),
        call_sites=[hex(v)for v in RETRIES],labels={k:hex(v)for k,v in labels.items()})

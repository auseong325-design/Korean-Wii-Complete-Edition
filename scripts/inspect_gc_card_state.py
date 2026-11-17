"""Read-only local synthetic-card diagnostics; never prints RAM/assets/IDs.

Bound to the project sandbox executable. Scans mapped RAM using an existing
local DOL guard; only emits scalar CARD status and integrity comparisons.
"""
import ctypes as C,ctypes.wintypes as W,subprocess,csv,io,struct,json,sys
from audit_sd import ROOT
sys.path.insert(0,str(ROOT))
from kwce.gc_native import dol_offset
from kwce.gc_fixture import checksum
k=C.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
k.ReadProcessMemory.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)]
k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]
class MBI(C.Structure):
    _fields_=[('base',C.c_void_p),('allocation',C.c_void_p),('allocation_protect',W.DWORD),('partition',W.WORD),('size',C.c_size_t),('state',W.DWORD),('protect',W.DWORD),('type',W.DWORD)]
k.VirtualQueryEx.argtypes=[W.HANDLE,C.c_void_p,C.POINTER(MBI),C.c_size_t];k.VirtualQueryEx.restype=C.c_size_t
p=subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True)
for row in csv.reader(io.StringIO(p.stdout)):
    if row and row[0].lower()=='dolphin.exe':pid=int(row[1]);break
else:raise SystemExit('No Dolphin')
h=k.OpenProcess(0x410,False,pid)
if not h:raise SystemExit('Read-only process access denied')
try:
    buf=C.create_unicode_buffer(32768);n=W.DWORD(len(buf))
    if not k.QueryFullProcessImageNameW(h,0,buf,C.byref(n)) or buf.value.lower() not in [str(ROOT/f'workspace/sandbox/gc-v{x}/Dolphin-x64/Dolphin.exe').lower() for x in [2,3,4,5]]:raise SystemExit('Not project sandbox Dolphin')
    def read(addr,n):
        b=C.create_string_buffer(n);got=C.c_size_t()
        if not k.ReadProcessMemory(h,addr,b,n,C.byref(got)) or got.value!=n:raise ValueError('RAM read failed')
        return b.raw
    original=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes();guard_address=0x1333510;at=dol_offset(original,0x81333510);guard=original[at:at+24]
    gc_flags='--gc-boot-flags' in sys.argv or '--gc-pad-status' in sys.argv
    if gc_flags:
        if buf.value.lower()!=str(ROOT/'workspace/sandbox/gc-v5/Dolphin-x64/Dolphin.exe').lower():raise SystemExit('GC SDK diagnostic requires v5')
        from audit_sd import PRIVATE,sha256
        catalog=json.loads((PRIVATE/'disc-catalog.json').read_text(encoding='utf-8'))
        row=next(r for r in catalog['files'] if r['name']=='GALJ01.iso')
        if sha256(ROOT/'workspace/sandbox/gc-v5/disc/GALJ01.iso')!=row['sha256']:raise SystemExit('Catalogued disc guard failed')
        with (ROOT/'workspace/sandbox/gc-v5/disc/GALJ01.iso').open('rb') as disc:
            header=disc.read(8)
            if header[:6]!=b'GALJ01' or header[7]!=1:raise SystemExit('Unsupported GC SDK revision')
            disc.seek(0x420);dol=int.from_bytes(disc.read(4),'big');disc.seek(dol);head=disc.read(256)
            section_offset=struct.unpack_from('>I',head,4)[0];section_address=struct.unpack_from('>I',head,0x4c)[0]
            disc.seek(dol+section_offset+256);guard=disc.read(24);guard_address=(section_address&0x1ffffff)+256
    cursor=0;matches=[]
    while True:
        m=MBI()
        if not k.VirtualQueryEx(h,cursor,C.byref(m),C.sizeof(m)):break
        base=m.base or 0
        if m.state==0x1000 and m.type==0x40000 and m.size>=0x2000000 and m.size<=0x20000000 and not m.protect&0x100:
            try:
                if read(base+guard_address,len(guard))==guard:matches.append(base)
            except ValueError:pass
        next_=base+m.size
        if next_<=cursor:break
        cursor=next_
    if not matches:raise SystemExit('No guarded menu RAM view')
    base=matches[0]
    def guest(a,n):
        if not 0x80000000<=a<=0x82000000-n:raise ValueError('Outside MEM1')
        return read(base+a-0x80000000,n)
    if '--gc-pad-status' in sys.argv:
        # Catalogued GALJ01 rev1 SDK diagnostic: derive SDA from local startup.
        with (ROOT/'workspace/sandbox/gc-v5/disc/GALJ01.iso').open('rb') as disc:
            disc.seek(dol);payload=disc.read(0x40000)
        bases=set()
        for i in range(0,len(payload)-40,4):
            word=int.from_bytes(payload[i:i+4],'big')
            if word&0xffff0000!=0x3da00000:continue
            for j in range(i+4,i+40,4):
                low=int.from_bytes(payload[j:j+4],'big')
                if low&0xffff0000 in [0x39ad0000,0x61ad0000]:bases.add(((word&65535)<<16)+(struct.unpack('>h',payload[j+2:j+4])[0] if low>>26==14 else low&65535))
        if len(bases)!=1:raise SystemExit('Game SDA guard failed')
        sda=bases.pop();fields={name:int.from_bytes(guest(sda+displacement,4),'big') for name,displacement in [('pending',-0x4298),('resetting',-0x42a8),('enabled',-0x42ac),('waiting',-0x42a0),('resetting_channel',-0x5a68)]}
        ram=guest(0x80000000,0x1800000);absent=bytes(10)+b'\xff';candidates=[];pos=0
        while True:
            pos=ram.find(absent,pos)
            if pos<0:break
            if pos>=12 and ram[pos+12:pos+23]==absent and ram[pos+24:pos+35]==absent:
                e=ram[pos-12:pos];candidates.append(dict(address=hex(0x80000000+pos-12),button=int.from_bytes(e[:2],'big'),error=int.from_bytes(e[10:11],'big',signed=True)))
            pos+=1
        lib=guest(0x804c1258,0x34);master=guest(0x804c128c,0x44)
        hsd=dict(master_button=int.from_bytes(master[:4],'big'),master_last=int.from_bytes(master[4:8],'big'))
        print(json.dumps(dict(read_only=True,PAD=fields,HSD=hsd,status_candidates=candidates[:20],candidate_count=len(candidates))));raise SystemExit(0)
    if '--gc-boot-flags' in sys.argv:
        print(json.dumps(dict(read_only=True,pad_boot_flags=hex(int.from_bytes(guest(0x800030e0,4),'big')),console_type=hex(int.from_bytes(guest(0x800030e6,2),'big')),video_mode=int.from_bytes(guest(0x800000cc,4),'big'))));raise SystemExit(0)
    if '--mios' in sys.argv:
        content=ROOT/'workspace/sandbox/gc-v5/user/Wii/title/00000001/00000101/content'
        tmd=(content/'title.tmd').read_bytes();count,boot=struct.unpack_from('>HH',tmd,0x140+0x9e)
        cid=next(struct.unpack_from('>I',tmd,0x140+0xa4+36*i)[0] for i in range(count) if struct.unpack_from('>H',tmd,0x140+0xa8+36*i)[0]==boot)
        arm=(content/f'{cid:08x}.app').read_bytes();head,off,size=struct.unpack_from('>III',arm,0);elf=arm[head+off:head+off+size]
        ph=struct.unpack_from('>I',elf,28)[0];ps,pn=struct.unpack_from('>HH',elf,42);matches=[]
        for i in range(pn):
            typ,off,addr,phys,filesz,memsz,flags,align=struct.unpack_from('>8I',elf,ph+ps*i)
            if typ==1 and 0<addr<0x1800000 and filesz>=32:matches.append(dict(address=hex(addr),prefix_matches=guest(0x80000000+addr,32)==elf[off:off+32]))
        print(json.dumps(dict(read_only=True,MIOS_load_segments=matches,semaphore=hex(int.from_bytes(guest(0x800030f8,4),'big')),stub_haxx_present=guest(0x80001804,8)==b'STUBHAXX')));raise SystemExit(0)
    expected_encoding=int.from_bytes(guest(0x8166db1a,2),'big');cards=[]
    for slot in range(2):
        control=guest(0x8112ffc8+slot*0x118,0x118)
        state=dict(slot='AB'[slot],attached=int.from_bytes(control[:4],'big'),result=int.from_bytes(control[4:8],'big',signed=True),size_mbits=int.from_bytes(control[8:10],'big'),expected_encoding=expected_encoding)
        for offset in range(0x70,0x94,4):
            ptr=int.from_bytes(control[offset:offset+4],'big')
            if not 0x80000000<=ptr<0x81ff6000:continue
            header=guest(ptr,512)
            if int.from_bytes(header[0x22:0x24],'big') not in [4,8,16,32,64,128]:continue
            state.update(header_found=True,header_device=int.from_bytes(header[0x20:0x22],'big'),header_size=int.from_bytes(header[0x22:0x24],'big'),header_encoding=int.from_bytes(header[0x24:0x26],'big'),header_checksum_valid=struct.unpack_from('>HH',header,0x1fc)==checksum(header[:0x1fc]));break
        cards.append(state)
    print(json.dumps(dict(read_only=True,guarded_RAM_views=len(matches),cards=cards)))
finally:k.CloseHandle(h)

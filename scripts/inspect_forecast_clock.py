"""Read-only guarded UI clock diagnostics; never prints RAM or console data."""
import ctypes as C
from ctypes import wintypes as W
import struct, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dolphin_ui import Driver
from kwce.channels import load_library
from kwce.ppc_patch import to_file


def main():
    import argparse,json
    ap=argparse.ArgumentParser();ap.add_argument('--snapshot',choices=['main','globe','settings']);args=ap.parse_args()
    driver=Driver()
    if driver.target.profile not in('forecast-review-v1','forecast-v2'):raise SystemExit('Local weather verification profiles only')
    driver.current();k=driver.k
    k.ReadProcessMemory.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)]
    class MBI(C.Structure):
        _fields_=[('base',C.c_void_p),('allocation',C.c_void_p),('allocation_protect',W.DWORD),
                  ('partition',W.WORD),('size',C.c_size_t),('state',W.DWORD),('protect',W.DWORD),('type',W.DWORD)]
    k.VirtualQueryEx.argtypes=[W.HANDLE,C.c_void_p,C.POINTER(MBI),C.c_size_t];k.VirtualQueryEx.restype=C.c_size_t
    h=k.OpenProcess(0x410,False,driver.process.pid)
    if not h:raise SystemExit('Read-only process access denied')
    try:
        if driver.created(h)!=driver.process.created:raise ValueError('Process changed')
        def read(a,n):
            b=C.create_string_buffer(n);got=C.c_size_t()
            if not k.ReadProcessMemory(h,a,b,n,C.byref(got))or got.value!=n:raise ValueError('Read failed')
            return b.raw
        load_library();from libWiiPy.title import Title
        import json
        revision=json.loads((ROOT/'workspace/sandbox'/driver.target.profile/'active-build.json').read_text())['revision']
        title=Title();title.load_wad((ROOT/f'workspace/channels/forecast/build-v{revision}/forecast-ko-personal-test.wad').read_bytes())
        dol=title.get_content_by_index(1);at=to_file(dol,0x8003c7b4,24);guard=dol[at:at+24]
        cursor=0;matches=[]
        while True:
            m=MBI()
            if not k.VirtualQueryEx(h,cursor,C.byref(m),C.sizeof(m)):break
            base=m.base or 0
            if m.state==0x1000 and m.type==0x40000 and 0x2000000<=m.size<=0x20000000 and not m.protect&0x100:
                try:
                    if read(base+0x3c7b4,24)==guard:matches.append(base)
                except ValueError:pass
            nxt=base+m.size
            if nxt<=cursor:break
            cursor=nxt
        if not matches:raise ValueError('No guarded Forecast MEM1 view')
        base=matches[0]
        def guest(a,n):
            if not 0x80000000<=a<=0x82000000-n:raise ValueError('Outside MEM1')
            return read(base+a-0x80000000,n)
        # Only ordinary UI time text and scalar format/clock states are emitted.
        buf=guest(0x801f7370,64)
        end=next((i for i in range(0,len(buf),2)if buf[i:i+2]==b'\0\0'),len(buf))
        text=buf[:end].decode('utf-16-be',errors='replace')
        if any(c not in '0123456789: /오전후' for c in text):text='[non-clock UI buffer]'
        # r13 is initialized to 0x80330000 (signed low adjustment below).
        rows=__import__('json').loads((ROOT/'workspace/private/forecast-review-instruction-index.json').read_text())
        init=[(m,o)for a,m,o in rows if 0x80004220<=a<0x80004240]
        sda=0x80330000
        for m,o in init:
            if m in('addi','ori')and o.startswith('r13, r13,'):
                val=int(o.split(', ')[-1],0);sda=(sda+val if m=='addi'else sda|val)&0xffffffff
        fields={}
        for alias,offset,n in [('ui_language',-0x6a0a,1),('clock_counter',-0x6998,4),('clock_enabled',-0x6985,1),('clock_hide_state',-0x6986,1),('clock_hide_input',-0x7378,1),('clock_object_present',-0x6958,4)]:
            fields[alias]=int.from_bytes(guest(sda+offset,n),'big')
            if alias.endswith('_present'):fields[alias]=bool(fields[alias])
        for alias,offset in [('forecast_view',-0x6b58),('forecast_page',-0x6b60),('forecast_transition',-0x6b5c)]:
            value=int.from_bytes(guest(sda+offset,4),'big')
            fields[alias]=value if value<=32 else '[not a bounded UI enum]'
        # Match only the known channel UI class vtable, never scan for IDs.
        memory=guest(0x80000000,0x1800000)
        objects=[i for i in range(0,len(memory)-0x200,4)if memory[i:i+4]==bytes.fromhex('8019a064')]
        fields['UI_objects']=len(objects)
        if len(objects)==1:
            obj=memory[objects[0]:objects[0]+0x200]
            fields['clock_alpha']=int.from_bytes(obj[0x9c:0xa0],'big')
            overlay=int.from_bytes(obj[0xa0:0xa4],'big')
            fields['UI_overlay_state']=overlay if overlay<=32 else '[not a bounded UI enum]'
            def code_class(ptr):
                if not 0x80000000<=ptr<0x81ffffc0:return None
                vt=int.from_bytes(guest(ptr,4),'big')
                try:to_file(dol,vt,16)
                except ValueError:return None
                return hex(vt)
            classes={}
            for offset in(0xac,0xb8,0xc8):
                ptr=int.from_bytes(obj[offset:offset+4],'big')
                classes[hex(offset)]=code_class(ptr)
                if 0x80000000<=ptr<0x81ffffc0:
                    node=guest(ptr,0x40)
                    for child_off in range(0,0x40,4):
                        tag=code_class(int.from_bytes(node[child_off:child_off+4],'big'))
                        if tag:classes[f'{offset:x}/{child_off:x}']=tag
            fields['program_UI_class_tags']=classes
            methods={}
            def method_tag(ptr):
                if not 0x80000000<=ptr<0x81fffff4:return None
                adjust,kind,target=struct.unpack('>III',guest(ptr,12))
                if kind!=0xffffffff:return None
                try:to_file(dol,target,4)
                except ValueError:return None
                return hex(target)
            methods['root/c8']=method_tag(int.from_bytes(obj[0xc8:0xcc],'big'))
            child=int.from_bytes(obj[0xb8:0xbc],'big')
            if 0x80000000<=child<0x81ffff00:
                methods['child-b8/ac']=method_tag(int.from_bytes(guest(child+0xac,4),'big'))
            fields['program_UI_method_tags']=methods
            def classify(value):
                if value<=32:return value
                if value==0xffffffff:return '[sentinel]'
                try:
                    to_file(dol,value,4)
                    return '[program address '+hex(value)+']'
                except ValueError:pass
                if 0x80000000<=value<0x82000000:return '[UI heap pointer]'
                return '[unclassified]'
            ptr=int.from_bytes(obj[0xc8:0xcc],'big')
            fields['UI_c8_storage']=classify(ptr)
            child=int.from_bytes(obj[0xb8:0xbc],'big')
            if 0x80000000<=child<0x81ffff00:fields['UI_child_active_callback']=classify(int.from_bytes(guest(child+0xac,4),'big'))
            if 0x80000000<=ptr<0x81ffffc0:
                fields['UI_c8_record_categories']=[classify(v)for v in struct.unpack('>16I',guest(ptr,64))]
            fields['clock_callback_selected']=int.from_bytes(obj[0x6c:0x70],'big')==0x8003c784
            for offset in(0xa8,0xac,0xb0,0xb4,0xb8,0xbc,0xc0,0xc4,0xc8,0xcc,0xd0):
                value=int.from_bytes(obj[offset:offset+4],'big')
                fields[f'UI_state_{offset:x}']=value if value<=32 else '[not a bounded UI enum]'
            if args.snapshot:
                private=ROOT/'workspace/private';n=1
                while(private/f'forecast-ui-object-{args.snapshot}-{n}.json').exists():n+=1
                address=0x80000000+objects[0];raw=guest(address,0x1000)
                # Kept locally only. Tool output never contains RAM bytes,
                # pointers, strings or unclassified object fields.
                children={}
                for offset in range(0xa8,0x200,4):
                    ptr=int.from_bytes(raw[offset:offset+4],'big')
                    if 0x80000000<=ptr<0x81fffe00:
                        child=guest(ptr,0x100)
                        if 0x80000000<=int.from_bytes(child[:4],'big')<0x80200000:
                            children[str(offset)]=child.hex()
                (private/f'forecast-ui-object-{args.snapshot}-{n}.json').write_text(json.dumps(dict(object=raw.hex(),children=children)))
                fields['private_UI_snapshot_saved']=True
        summary={key:fields[key]for key in('ui_language','clock_alpha','clock_hide_state','UI_objects')}
        summary['view']={'[program address 0x8000ef08]':'forecast','[program address 0x8000f660]':'globe'}.get(fields.get('UI_c8_storage'),'other')
        print(__import__('json').dumps(dict(read_only=True,UI_clock_text=text,**summary),ensure_ascii=False))
    finally:k.CloseHandle(h)


if __name__=='__main__':main()

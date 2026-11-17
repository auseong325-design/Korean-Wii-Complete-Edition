"""Locate public setting-name references, emitting addresses/counts only."""
import json,struct,sys
from audit_sd import ROOT,PRIVATE
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from capstone import Cs,CS_ARCH_PPC,CS_MODE_32,CS_MODE_BIG_ENDIAN

def main():
    title=load_library().title.Title();title.load_wad((ROOT/'workspace/channels/nintendo/access-build-v4/nintendo-local-test.wad').read_bytes());data=title.get_content_by_index(1)
    sections=[tuple(struct.unpack_from('>I',data,base+4*i)[0]for base in[0,0x48,0x90])for i in range(18)]
    def addr(off):return next((a+off-o for o,a,n in sections if o<=off<o+n),None)
    targets={};report={}
    for key in ['IPL.LNG','IPL.SADR']:
        off=data.find(key.encode());a=addr(off);pointers=[addr(i)for i in range(len(data)-3)if data[i:i+4]==struct.pack('>I',a)]
        targets[a]=key
        for p in pointers:
            if p:targets[p]=key+'-pointer'
        report[key]=dict(string_address=hex(a),pointer_addresses=[hex(p)for p in pointers if p],code_references=[])
    md=Cs(CS_ARCH_PPC,CS_MODE_32|CS_MODE_BIG_ENDIAN);md.skipdata=True
    for o,a,n in sections[:7]:
        regs={};function=a
        for x in md.disasm(data[o:o+n],a):
            op=x.mnemonic;args=[v.strip()for v in x.op_str.split(',')]
            if op=='stwu'and args[0]=='r1':function=x.address
            try:
                if op in ['li','lis']:regs[args[0]]=(int(args[1],0)<<(16 if op=='lis'else 0))&0xffffffff
                elif op=='addi':regs[args[0]]=(regs[args[1]]+int(args[2],0))&0xffffffff
                elif op=='ori':regs[args[0]]=regs[args[1]]|int(args[2],0)
                elif op=='mr':regs[args[0]]=regs[args[1]]
                elif args and args[0].startswith('r')and op not in ['stw','stb','sth','stwu','stmw']:regs.pop(args[0],None)
                if op in ['addi','ori','mr']and regs.get(args[0])in targets:
                    target=targets[regs[args[0]]];key=target.split('-')[0];report[key]['code_references'].append(dict(address=hex(x.address),function=hex(function),kind=target))
            except(KeyError,ValueError):
                if args:regs.pop(args[0],None)
    (PRIVATE/'nintendo-locale-references.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

if __name__=='__main__':main()

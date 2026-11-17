"""Report derived validator metadata; keep executable/disassembly local."""
import json,re,struct,sys
from audit_sd import ROOT,PRIVATE
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from capstone import Cs,CS_ARCH_PPC,CS_MODE_32,CS_MODE_BIG_ENDIAN

def main():
    title=load_library().title.Title();title.load_wad((ROOT/'workspace/channels/nintendo/access-build-v4/nintendo-local-test.wad').read_bytes())
    data=title.get_content_by_index(1);md=Cs(CS_ARCH_PPC,CS_MODE_32|CS_MODE_BIG_ENDIAN);md.skipdata=True;instructions=[]
    for s in range(7):
        off,addr,size=(struct.unpack_from('>I',data,a+4*s)[0]for a in [0,0x48,0x90])
        instructions.extend(md.disasm(data[off:off+size],addr))
    candidates=json.loads((PRIVATE/'nintendo-format-constraints.json').read_text());candidates.extend([dict(address=a,exact=True)for a in [0x80035e50,0x80035eb0]]);report=[]
    for c in candidates:
        i=next(i for i,v in enumerate(instructions)if v.address==c['address']);start=i
        while not c.get('exact')and start>0 and i-start<30:
            if instructions[start].mnemonic=='stwu' and instructions[start].op_str.startswith('r1, -'):break
            start-=1
        regs={'r3':'argument0','r4':'argument1','r5':'argument2'};events=[]
        for x in instructions[start:start+400]:
            if x.address>c['address']and x.mnemonic=='blr':
                events.append(dict(return_value=regs.get('r3','unknown')));break
            args=[a.strip()for a in x.op_str.split(',')];op=x.mnemonic
            if op in ['lwz','lhz','lbz']and len(args)==2:
                m=re.fullmatch(r'(-?(?:0x[0-9a-f]+|\d+))\((r\d+)\)',args[1])
                if m:
                    base=regs.get(m[2],m[2]);regs[args[0]]=f'{base}.field[{int(m[1],0)}]'
                else:regs.pop(args[0],None)
            elif op=='mr'and len(args)==2:regs[args[0]]=regs.get(args[1],args[1])
            elif op=='li'and len(args)==2:regs[args[0]]='constant('+args[1]+')'
            elif op=='bl':
                if re.fullmatch(r'0x[0-9a-f]+',args[0]):
                    events.append(dict(call=int(args[0],0),arguments=[regs.get('r'+str(j),'unknown')for j in range(3,6)]))
                    regs['r3']='callResult('+args[0]+')'
            elif op in ['cmpw','cmplw','cmpwi','cmplwi']:
                events.append(dict(compare=[regs.get(a,a)for a in args[-2:]],at=x.address))
            elif args and re.fullmatch(r'r\d+',args[0])and op not in ['stw','stb','sth','stwu','stmw','stfd']:
                regs.pop(args[0],None)
        report.append(dict(candidate=hex(c['address']),events=events[:65]))
    (PRIVATE/'nintendo-header-semantics.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report[-2:]))

if __name__=='__main__':main()

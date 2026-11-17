"""Summarize header-validation constraints locally without emitting binary/code."""
import json,re,struct,sys
from audit_sd import ROOT,PRIVATE
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from capstone import Cs,CS_ARCH_PPC,CS_MODE_32,CS_MODE_BIG_ENDIAN

def number(s):
 try:return int(s,0)
 except ValueError:return None

def main():
 t=load_library().title.Title();t.load_wad((ROOT/'workspace/channels/nintendo/access-build-v2/nintendo-local-test.wad').read_bytes())
 data=t.get_content_by_index(1);md=Cs(CS_ARCH_PPC,CS_MODE_32|CS_MODE_BIG_ENDIAN);md.skipdata=True;result=[]
 for section in range(7):
  offset=struct.unpack_from('>I',data,4*section)[0];address=struct.unpack_from('>I',data,0x48+4*section)[0];size=struct.unpack_from('>I',data,0x90+4*section)[0]
  if not size:continue
  instructions=list(md.disasm(data[offset:offset+size],address))
  for i,ins in enumerate(instructions):
   m=re.fullmatch(r'(r\d+), 2\((r\d+)\)',ins.op_str)
   if ins.mnemonic!='lbz'or not m:continue
   if not any(j.mnemonic=='cmplwi'and j.op_str==m[1]+', 6'for j in instructions[i+1:i+5]):continue
   fields={};constants={};constraints=[];base=m[2];aliases={base};returned=False
   for j in instructions[i:i+600]:
    args=[s.strip()for s in j.op_str.split(',')]
    if returned and j.mnemonic in ['stwu','mflr']:break
    if j.mnemonic=='blr':returned=True
    if j.mnemonic in ['lwz','lhz','lbz']and len(args)==2:
     a=re.fullmatch(r'(-?(?:0x[0-9a-f]+|\d+))\((r\d+)\)',args[1])
     if a and a[2]not in aliases:a=None
     if a:fields[args[0]]=(int(a[1],0),j.mnemonic);constants.pop(args[0],None)
     else:fields.pop(args[0],None);constants.pop(args[0],None)
    elif j.mnemonic in ['li','lis']and len(args)==2:
     n=number(args[1]);fields.pop(args[0],None)
     if n is not None:constants[args[0]]=n<<(16 if j.mnemonic=='lis'else 0)
    elif j.mnemonic=='addi'and len(args)==3:
     n=number(args[2]);fields.pop(args[0],None)
     if args[1]in constants and n is not None:constants[args[0]]=constants[args[1]]+n
     else:constants.pop(args[0],None)
    elif j.mnemonic=='mr'and len(args)==2:
     if args[1]in aliases:aliases.add(args[0])
     else:aliases.discard(args[0])
     if args[1]in fields:fields[args[0]]=fields[args[1]]
     if args[1]in constants:constants[args[0]]=constants[args[1]]
    elif j.mnemonic in ['cmpwi','cmplwi','cmpw','cmplw']:
     a,b=args[-2:]
     if a in fields:
      n=number(b)if j.mnemonic.endswith('i')else constants.get(b)
      if n is not None:constraints.append(dict(field=fields[a][0],width=fields[a][1],compared_to=n))
   result.append(dict(address=ins.address,base=base,comparisons=constraints))
 (PRIVATE/'nintendo-format-constraints.json').write_text(json.dumps(result,indent=2))
 print(json.dumps([dict(candidate=i,comparisons=r['comparisons'][:24],comparison_count=len(r['comparisons']))for i,r in enumerate(result)]))

if __name__=='__main__':main()

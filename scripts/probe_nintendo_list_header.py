"""Bounded local interpretation of a header predicate on synthetic bytes only.

No executable bytes, disassembly, original NAND, or machine identifiers leave
this process. The interpreter has no system calls or writable host memory.
"""
import json,pathlib,re,struct,sys
from audit_sd import ROOT,PRIVATE
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library

def main():
    lib=load_library()
    from libWiiPy.archive import decompress_lz77
    from capstone import Cs,CS_ARCH_PPC,CS_MODE_32,CS_MODE_BIG_ENDIAN
    title=lib.title.Title();title.load_wad((ROOT/'workspace/channels/nintendo/access-build-v5/nintendo-local-test.wad').read_bytes());exe=title.get_content_by_index(1)
    md=Cs(CS_ARCH_PPC,CS_MODE_32|CS_MODE_BIG_ENDIAN);md.skipdata=True;instructions={}
    for s in range(7):
        o,a,n=(struct.unpack_from('>I',exe,b+4*s)[0]for b in[0,0x48,0x90])
        instructions.update({i.address:i for i in md.disasm(exe[o:o+n],a)})
    original=decompress_lz77(b'LZ77'+(ROOT/'workspace/sandbox/nintendo-test-v1/local-feed/dllist.bin').read_bytes())
    def probe(data):
        memory=0x10000000;regs={f'r{i}':0 for i in range(32)};regs['r3']=memory;cr={};pc=0x80035f60;last_field=None;failure_field=None;carry=0
        def signed(n):return n if n<0x80000000 else n-0x100000000
        def val(a):return regs[a]if a in regs else int(a,0)
        def put(reg,n):regs[reg]=n&0xffffffff
        for steps in range(5000):
            ins=instructions[pc];op=ins.mnemonic;args=[a.strip()for a in ins.op_str.split(',')];pc+=4
            if op=='blr':return dict(result=regs['r3'],steps=steps+1,last_field=last_field,failure_field=failure_field)
            if op in ['lbz','lhz','lwz']:
                m=re.fullmatch(r'(-?(?:0x[0-9a-f]+|\d+))\((r\d+)\)',args[1]);at=(val(m[2])+int(m[1],0))&0xffffffff;off=at-memory;n={'lbz':1,'lhz':2,'lwz':4}[op]
                if not 0<=off<=len(data)-n:return dict(error='synthetic-memory-bounds',offset=off)
                put(args[0],int.from_bytes(data[off:off+n],'big'));last_field=off
            elif op in ['cmpwi','cmplwi','cmpw','cmplw']:
                key=args[0]if len(args)==3 else'cr0';a,b=map(val,args[-2:])
                if op in ['cmpwi','cmpw']:a,b=signed(a&0xffffffff),signed(b&0xffffffff)
                cr[key]=(a>b)-(a<b)
            elif op in ['beq','bne','blt','bgt','ble','bge']:
                key=args[0]if len(args)==2 else'cr0';c=cr[key];take={'beq':c==0,'bne':c!=0,'blt':c<0,'bgt':c>0,'ble':c<=0,'bge':c>=0}[op]
                if take:pc=int(args[-1],0)
            elif op=='b':pc=int(args[0],0)
            elif op in ['li','lis']:
                put(args[0],val(args[1])<<(16 if op=='lis'else 0))
                # This predicate returns 0 on success and 1 on rejection.
                # Recording the final `li r3,0` as a failure falsely blamed
                # the last field of an otherwise valid synthetic header.
                if args[0]=='r3'and val(args[1])==1:failure_field=last_field
            elif op=='mr':put(args[0],val(args[1]))
            elif op in ['addi','add','mulli','subf','subfic','ori','or','and','xor','srwi','slwi']:
                a,b=val(args[1]),val(args[2]);n={'addi':lambda:a+b,'add':lambda:a+b,'mulli':lambda:a*b,'subf':lambda:b-a,'subfic':lambda:b-a,'ori':lambda:a|b,'or':lambda:a|b,'and':lambda:a&b,'xor':lambda:a^b,'srwi':lambda:a>>b,'slwi':lambda:a<<b}[op]();put(args[0],n)
                if op=='subfic':carry=int(b>=a)
            elif op=='subfe':
                a,b=val(args[1]),val(args[2]);n=b-a+carry-1;put(args[0],n);carry=int(n>=0)
            elif op=='cntlzw':put(args[0],32-val(args[1]).bit_length())
            elif op=='neg':put(args[0],-val(args[1]))
            elif op=='nop':pass
            else:return dict(error='unsupported-operation',operation=op,steps=steps)
        return dict(error='instruction-budget')
    bad=bytearray(original);bad[2]=0
    report=dict(synthetic_header=probe(original),invalid_version=probe(bytes(bad)))
    if report['synthetic_header'].get('result') != 0 or report['synthetic_header'].get('failure_field') is not None:
        raise ValueError('Synthetic valid-header control rejected')
    if report['invalid_version'].get('result') != 1 or report['invalid_version'].get('failure_field') != 2:
        raise ValueError('Invalid-version control not rejected at version')
    target=PRIVATE/'nintendo-header-predicate-probe-v2.json'
    if target.exists():
        if json.loads(target.read_text()) != report:
            raise FileExistsError('Existing v2 probe report differs; preserved')
    else:
        target.write_text(json.dumps(report,indent=2))
    print(json.dumps(report))

if __name__=='__main__':main()

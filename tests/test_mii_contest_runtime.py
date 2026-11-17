"""Fast unit tests for the Mii Contest wave-2 runtime specialty translation and new outputs.

These exercise the DOL patch builder, the shipped build-v26 / access-build-v21 / hardware-v1
artifacts and the by-code fail-safe translation semantics. They do NOT launch Dolphin and do NOT
run the multi-minute full build.

build-v27 / access-build-v22 / hardware-v2 (in-place cave rework): the content-1 DOL header,
section count, image bounds and bss must equal build-v25's (a new high section panicked at boot in
Dolphin, so this catches that regression class without an emulator), only the cave and the call-site
word may differ, and the shipped stub + converter bytes are EXECUTED by a minimal PowerPC
interpreter against UTF-16BE skill slots (the slots' real encoding).
"""
import json,struct,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from kwce.channels import load_library
from kwce.ppc_patch import sections,to_file
from kwce.mii_contest_runtime import (build_specialty_dict,build_table,build_blob,
                                       patch_specialty_runtime,SECTION_VA,SKILL_ENGLISH,
                                       SKILL_REVIEWED_ID,ADDITION_PARSE,DISPATCH_SITE,SKILL_NAME_CAP)
from kwce import mii_contest_runtime as RT

BASE=ROOT/'workspace/channels/mii-contest'


def _content(wad,index):
    t=load_library().title.Title();t.load_wad(Path(wad).read_bytes());return t,t.get_content_by_index(index)


class SpecialtyDictionary(unittest.TestCase):
    def test_dictionary_matches_server_codes_and_reviewed_korean(self):
        md=build_specialty_dict(ROOT)
        self.assertEqual(sorted(md),list(range(1,20)))
        add=json.loads((BASE/'references/server-source/first/addition.json').read_text(encoding='utf-8'))
        server={s['code']:s['name'] for s in add['regions'][1]['1']['skills']}
        reviewed=json.loads((ROOT/'configs/mii-contest-reviewed-ko.json').read_text(encoding='utf-8'))['reviewed_messages']
        for code,(english,korean) in md.items():
            self.assertEqual(english,server[code],f'code {code} English must match server data')
            self.assertEqual(english,SKILL_ENGLISH[code])
            self.assertEqual(korean,reviewed[str(SKILL_REVIEWED_ID[code])],f'code {code} Korean must be the reviewed name')

    def test_every_name_fits_the_slot(self):
        for code,(english,korean) in build_specialty_dict(ROOT).items():
            self.assertLessEqual(len(english.encode('ascii')),SKILL_NAME_CAP)
            self.assertLessEqual(len(korean.encode('utf-8')),SKILL_NAME_CAP-1)


class DolPatch(unittest.TestCase):
    def setUp(self):
        self.t,self.exe=_content(BASE/'build-v25/mii-contest-ko-ui-test.wad',1)
        self.md=build_specialty_dict(ROOT)

    def test_patch_is_deterministic(self):
        a,_=patch_specialty_runtime(self.exe,self.md)
        b,_=patch_specialty_runtime(self.exe,self.md)
        self.assertEqual(a,b)

    def test_redirects_only_the_dispatch_site(self):
        patched,rec=patch_specialty_runtime(self.exe,self.md)
        word=struct.unpack_from('>I',patched,to_file(patched,DISPATCH_SITE,4))[0]
        self.assertEqual(word,0x48000001|((SECTION_VA-DISPATCH_SITE)&0x03fffffc))  # bl SECTION_VA
        self.assertEqual(rec['reused_routine']['addition_parse'],hex(ADDITION_PARSE))
        self.assertEqual(rec['mc_stub'],hex(SECTION_VA))
        # below the appended section, only the dispatch site and the new section's three DOL
        # header table words (offset/addr/size for the chosen slot) differ
        base_len=len(self.exe);slot=rec['dol_section_slot']
        header={4*slot,0x48+4*slot,0x90+4*slot}
        diffs=[i for i in range(0,base_len,4) if patched[i:i+4]!=self.exe[i:i+4]]
        self.assertEqual(set(diffs),header|{to_file(self.exe,DISPATCH_SITE,4)})

    def test_new_section_sits_above_bss(self):
        patched,_=patch_specialty_runtime(self.exe,self.md)
        bss_end=struct.unpack_from('>I',patched,0xd8)[0]+struct.unpack_from('>I',patched,0xdc)[0]
        secs=[(a,s) for i,o,a,s in sections(bytearray(patched)) if a==SECTION_VA]
        self.assertEqual(len(secs),1)
        self.assertGreaterEqual(SECTION_VA,bss_end)


class ShippedArtifacts(unittest.TestCase):
    def test_build_v26_region4_and_embedded_blob_regenerates(self):
        meta=json.loads((BASE/'build-v26/build-manifest.json').read_text())
        t,c1=_content(BASE/'build-v26/mii-contest-ko-ui-test.wad',1)
        self.assertEqual(t.tmd.region,4)
        self.assertIn(1,meta['changed_contents'])
        # the embedded stub+converter+table regenerate byte-identically
        tbl,_=build_table(build_specialty_dict(ROOT));blob,_=build_blob(tbl)
        off=next(o for i,o,a,s in sections(bytearray(c1)) if a==SECTION_VA)
        self.assertEqual(c1[off:off+len(blob)],blob)
        self.assertEqual(meta['specialty_runtime']['blob_sha256'],__import__('hashlib').sha256(blob).hexdigest())

    def test_access_build_v21_matches_manifest(self):
        meta=json.loads((BASE/'access-build-v21/build-manifest.json').read_text())
        wad=(BASE/'access-build-v21/mii-contest-local-test.wad').read_bytes()
        self.assertEqual(__import__('hashlib').sha256(wad).hexdigest(),meta['wad_sha256'])
        self.assertEqual(meta['source_build'],'build-v26')
        self.assertEqual(len(meta['nas_url_ranges']),6)

    def test_hardware_v1_is_region4(self):
        meta=json.loads((BASE/'hardware-v1/hardware-manifest.json').read_text())
        self.assertEqual(meta['tmd_region'],4)
        self.assertEqual(meta['source_build'],'build-v26')
        t,_=_content(BASE/'hardware-v1/mii-contest-ko-hardware.wad',0)
        self.assertEqual(t.tmd.region,4)


class FailSafeSemantics(unittest.TestCase):
    """Reference model of the build-v26 CONVERT_C table format (it assumed UTF-8 slots; the channel's
    slots are UTF-16BE, see CaveExecution, which runs the shipped build-v27 machine code)."""
    BIAS=0x801c;STRIDE=0x40

    def _convert(self,obj,table):
        off=0;n=struct.unpack_from('>I',table,off)[0];off+=4
        for _ in range(n):
            code,el,kl=table[off],table[off+1],table[off+2];off+=3
            en=table[off:off+el];off+=el;ko=table[off:off+kl];off+=kl
            if not 1<=code<=254:continue
            slot=self.BIAS+code*self.STRIDE
            if obj[slot]==0:continue                      # not supplied
            if obj[slot:slot+el]!=en or obj[slot+el]!=0:continue  # unexpected -> leave
            obj[slot:slot+0x20]=bytes(0x20)
            obj[slot:slot+kl]=ko

    def test_translates_known_leaves_everything_else(self):
        table,_=build_table(build_specialty_dict(ROOT))
        obj=bytearray(0x801c+256*0x40)
        def put(code,text):
            s=self.BIAS+code*self.STRIDE;b=text.encode('utf-8');obj[s:s+len(b)]=b
        put(3,'Athletics')      # supplied + matching -> translated
        put(7,'Dance')          # supplied + matching -> translated
        put(2,'Arts')           # supplied but WRONG english -> left
        # code 5 left empty (not supplied) -> stays empty
        country=0x18+136*0x80;obj[country:country+11]=b'South Korea'  # dynamic table -> untouched
        self._convert(obj,table)
        def read(code):
            s=self.BIAS+code*self.STRIDE;return bytes(obj[s:obj.index(0,s)]).decode('utf-8')
        self.assertEqual(read(3),'운동')
        self.assertEqual(read(7),'춤')
        self.assertEqual(read(2),'Arts')                 # fail-safe: mismatch left as supplied
        self.assertEqual(obj[self.BIAS+5*self.STRIDE],0) # empty slot untouched
        self.assertEqual(bytes(obj[country:country+11]),b'South Korea')  # dynamic untouched


# ------------------------------------------------------------------------------------------------
# build-v27 / access-build-v22 / hardware-v2: in-place cave, header and bounds identical to build-v25
# ------------------------------------------------------------------------------------------------
M32=0xffffffff


def _s32(v):
    return v-(1<<32) if v&0x80000000 else v


def _mask(mb,me):
    m=0
    for i in range(32):
        if(mb<=me and mb<=i<=me)or(mb>me and(i>=mb or i<=me)):m|=1<<(31-i)
    return m


class MiniPPC:
    """Just enough 32-bit PowerPC to execute the shipped stub + converter; anything else raises."""

    def __init__(self):
        self.regions=[];self.r=[0]*32;self.lr=0;self.ctr=0;self.cr=[0]*8;self.pc=0;self.hooks={};self.steps=0

    def map(self,base,data):
        self.regions.append((base,bytearray(data)));return self.regions[-1][1]

    def _at(self,addr,n):
        for base,buf in self.regions:
            if base<=addr and addr+n<=base+len(buf):return buf,addr-base
        raise MemoryError(f'unmapped access {addr:#x}+{n} at pc {self.pc:#x}')

    def load(self,addr,n):
        buf,o=self._at(addr,n);return int.from_bytes(buf[o:o+n],'big')

    def store(self,addr,n,value):
        buf,o=self._at(addr,n);buf[o:o+n]=(value&((1<<8*n)-1)).to_bytes(n,'big')

    def _cmp(self,crf,a,b):
        self.cr[crf]=8 if a<b else 4 if a>b else 2

    def _taken(self,bo,bi):
        if not bo&4:self.ctr=(self.ctr-1)&M32
        ctr_ok=bool(bo&4)or((self.ctr!=0)!=bool(bo&2))
        cond_ok=bool(bo&16)or(bool(self.cr[bi>>2]&(8>>(bi&3)))==bool(bo&8))
        return ctr_ok and cond_ok

    def run(self,pc,ret,limit=200000):
        self.pc=pc;self.lr=ret
        while self.pc!=ret:
            self.steps+=1
            if self.steps>limit:raise RuntimeError('instruction limit')
            hook=self.hooks.get(self.pc)
            if hook:hook(self);self.pc=self.lr;continue
            self.step()

    def step(self):
        w=self.load(self.pc,4);op=w>>26;nxt=(self.pc+4)&M32;r=self.r
        d,a,b=(w>>21)&31,(w>>16)&31,(w>>11)&31
        simm=(w&0xffff)-0x10000 if w&0x8000 else w&0xffff;uimm=w&0xffff;base=r[a]if a else 0
        if op==14:r[d]=(base+simm)&M32                                   # addi / li
        elif op==15:r[d]=(base+(simm<<16))&M32                           # addis / lis
        elif op==10:self._cmp((w>>23)&7,r[a],uimm)                       # cmplwi
        elif op==11:self._cmp((w>>23)&7,_s32(r[a]),simm)                 # cmpwi
        elif op==21:                                                     # rlwinm
            sh=b;v=r[d];rot=((v<<sh)|(v>>(32-sh)))&M32 if sh else v
            r[a]=rot&_mask((w>>6)&31,(w>>1)&31)
            if w&1:self._cmp(0,_s32(r[a]),0)
        elif op==24:r[a]=r[d]|uimm                                       # ori
        elif op in(32,34,40):r[d]=self.load((base+simm)&M32,{32:4,34:1,40:2}[op])   # lwz lbz lhz
        elif op==35:ea=(r[a]+simm)&M32;r[d]=self.load(ea,1);r[a]=ea      # lbzu
        elif op in(36,38,44):self.store((base+simm)&M32,{36:4,38:1,44:2}[op],r[d])  # stw stb sth
        elif op in(37,39,45):ea=(r[a]+simm)&M32;self.store(ea,{37:4,39:1,45:2}[op],r[d]);r[a]=ea  # stwu stbu sthu
        elif op in(46,47):                                               # lmw / stmw
            ea=(base+simm)&M32
            for k in range(d,32):
                if op==46:r[k]=self.load(ea,4)
                else:self.store(ea,4,r[k])
                ea+=4
        elif op==18:                                                     # b / bl
            li=w&0x3fffffc;li=li-0x4000000 if li&0x2000000 else li
            if w&1:self.lr=nxt
            nxt=(li if w&2 else self.pc+li)&M32
        elif op==16:                                                     # bc
            bd=w&0xfffc;bd=bd-0x10000 if bd&0x8000 else bd;target=(bd if w&2 else self.pc+bd)&M32
            if w&1:self.lr=nxt
            if self._taken(d,a):nxt=target
        elif op==19 and(w>>1)&0x3ff==16:                                 # bclr
            target=self.lr&~3
            if w&1:self.lr=nxt
            if self._taken(d,a):nxt=target
        elif op==31:
            xo=(w>>1)&0x3ff;rc=None
            if xo==266:r[d]=(r[a]+r[b])&M32;rc=d                         # add
            elif xo==40:r[d]=(r[b]-r[a])&M32;rc=d                        # subf
            elif xo==444:r[a]=r[d]|r[b];rc=a                             # or / mr
            elif xo==87:r[d]=self.load((base+r[b])&M32,1)                # lbzx
            elif xo==215:self.store((base+r[b])&M32,1,r[d])              # stbx
            elif xo==0:self._cmp((w>>23)&7,_s32(r[a]),_s32(r[b]))        # cmpw
            elif xo==32:self._cmp((w>>23)&7,r[a],r[b])                   # cmplw
            elif xo in(339,467):                                         # mfspr / mtspr (LR, CTR)
                spr=a|(b<<5)
                if spr not in(8,9):raise NotImplementedError(f'spr {spr}')
                if xo==339:r[d]=self.lr if spr==8 else self.ctr
                elif spr==8:self.lr=r[d]
                else:self.ctr=r[d]
            else:raise NotImplementedError(f'xo {xo} at {self.pc:#x}: {w:08x}')
            if rc is not None and w&1:self._cmp(0,_s32(r[rc]),0)
        else:raise NotImplementedError(f'opcode {op} at {self.pc:#x}: {w:08x}')
        self.pc=nxt


OBJ=0x81000000;STACK_TOP=0x81200000;BUF=0x81300000;BUF_LEN=0x1234;PARSE_RET=0x5a5a
RET_SITE=DISPATCH_SITE+4


def _slot(code):
    return RT.SKILL_TABLE_BIAS+code*RT.SKILL_SLOT_STRIDE


def _utf16_slot(text):
    """What the channel's store routine leaves: 64 zero bytes, then <=31 UTF-16BE units."""
    raw=text.encode('utf-16-be')[:2*RT.SLOT_UNITS];return raw+bytes(RT.SLOT_BYTES-len(raw))


def _execute(content1,code_base,code_size,supplied):
    """Call the hook the way the dispatcher does; the fake parser fills slots like the real one."""
    cpu=MiniPPC();at=to_file(content1,code_base,code_size)
    cpu.map(code_base,content1[at:at+code_size])
    obj=cpu.map(OBJ,bytes((i*37+11)&0xff for i in range(0x10000)))   # non-zero noise everywhere
    cpu.map(STACK_TOP-0x1000,bytes(0x1000));cpu.r[1]=STACK_TOP-0x800
    cpu.r[3],cpu.r[4],cpu.r[5]=OBJ,BUF,BUF_LEN;seen={}

    def parse(c):
        seen['args']=(c.r[3],c.r[4],c.r[5])
        for code in range(1,256):obj[_slot(code):_slot(code)+0x40]=bytes(0x40)
        for code,text in supplied.items():obj[_slot(code):_slot(code)+0x40]=_utf16_slot(text)
        seen['after_parse']=bytes(obj);c.r[3]=PARSE_RET
    cpu.hooks[ADDITION_PARSE]=parse
    cpu.run(code_base,RET_SITE)
    return cpu,obj,seen


class CaveLayout(unittest.TestCase):
    """The regression the lead hit (new section above bss) is caught here without Dolphin."""

    @classmethod
    def setUpClass(cls):
        cls.v25=_content(BASE/'build-v25/mii-contest-ko-ui-test.wad',1)[1]
        cls.md=build_specialty_dict(ROOT)

    def _assert_same_boot_layout(self,dol,label):
        ref,mine=RT.dol_layout(self.v25),RT.dol_layout(dol)
        self.assertEqual(mine['section_count'],ref['section_count'],f'{label}: DOL section count')
        self.assertEqual((mine['image_lo'],mine['image_hi']),(ref['image_lo'],ref['image_hi']),f'{label}: image bounds')
        self.assertEqual((mine['bss'],mine['bss_size'],mine['entry']),(ref['bss'],ref['bss_size'],ref['entry']),f'{label}: bss/entry')
        self.assertEqual(mine['sections'],ref['sections'],f'{label}: section table')
        self.assertEqual(dol[:0x100],self.v25[:0x100],f'{label}: DOL header bytes')
        self.assertEqual(len(dol),len(self.v25),f'{label}: content-1 length')

    def test_patched_dol_keeps_build_v25_section_count_and_image_bounds(self):
        patched,rec=RT.patch_specialty_cave(self.v25,self.md)
        self._assert_same_boot_layout(patched,'patch')
        self.assertFalse(rec['new_dol_section'])
        self.assertEqual(rec['section_count'],10)

    def test_shipped_v27_access_v22_hardware_v2_keep_build_v25_layout(self):
        for label,wad in (('build-v27','build-v27/mii-contest-ko-ui-test.wad'),
                          ('access-build-v22','access-build-v22/mii-contest-local-test.wad'),
                          ('hardware-v2','hardware-v2/mii-contest-ko-hardware.wad')):
            self._assert_same_boot_layout(_content(BASE/wad,1)[1],label)

    def test_build_v26_is_the_known_bad_layout(self):
        # Documents why v26 was rejected: one more text section, image end past bss end, in the stack.
        ref,v26=RT.dol_layout(self.v25),RT.dol_layout(_content(BASE/'build-v26/mii-contest-ko-ui-test.wad',1)[1])
        self.assertEqual(v26['section_count'],ref['section_count']+1)
        self.assertGreater(v26['image_hi'],ref['bss']+ref['bss_size'])

    def test_only_the_cave_and_the_call_site_change(self):
        patched,rec=RT.patch_specialty_cave(self.v25,self.md)
        cave=to_file(self.v25,RT.CAVE_VA,4);site=to_file(self.v25,DISPATCH_SITE,4)
        diffs=[i for i in range(len(self.v25)) if patched[i]!=self.v25[i]]
        self.assertTrue(diffs)
        for i in diffs:
            self.assertTrue(cave<=i<cave+rec['blob_bytes'] or site<=i<site+4,f'unexpected change at {i:#x}')
        word=struct.unpack_from('>I',patched,site)[0]
        self.assertEqual(word,0x48000001|((RT.CAVE_VA-DISPATCH_SITE)&0x03fffffc))    # bl CAVE_VA
        self.assertEqual(patched,RT.patch_specialty_cave(self.v25,self.md)[0])        # deterministic

    def test_cave_is_empty_trk_slots_inside_text0_and_unreferenced(self):
        RT.verify_cave(self.v25)                       # raises if not zero / bounded / unreferenced
        self.assertEqual(RT.cave_references(self.v25),[])
        text0=next(s for s in sections(self.v25) if s[0]==0)
        self.assertTrue(text0[2]<=RT.CAVE_VA<RT.CAVE_END<=text0[2]+text0[3])
        lay=RT.dol_layout(self.v25)
        self.assertLess(RT.CAVE_END,lay['bss'])        # inside the loaded image, far below bss/stack
        self.assertEqual((RT.CAVE_VA,RT.CAVE_END),(0x80005988,0x80005d88))
        _,rec=RT.build_cave_blob(RT.build_table16(self.md)[0])
        self.assertLessEqual(rec['blob_bytes'],RT.CAVE_END-RT.CAVE_VA)
        broken=bytearray(self.v25);broken[to_file(broken,RT.CAVE_VA+0x100,1)]=1
        with self.assertRaises(ValueError):RT.verify_cave(bytes(broken))

    def test_utf16_table_fits_the_slots(self):
        _,rows=RT.build_table16(self.md)
        self.assertEqual([r['code'] for r in rows],list(range(1,20)))
        for r in rows:
            self.assertLessEqual(r['en_chars'],RT.SLOT_UNITS)
            self.assertLessEqual(r['ko_units'],RT.SLOT_UNITS-1)


class CaveExecution(unittest.TestCase):
    """Runs the SHIPPED build-v27 cave bytes (stub + converter + table) on UTF-16BE skill slots."""

    @classmethod
    def setUpClass(cls):
        cls.c1=_content(BASE/'build-v27/mii-contest-ko-ui-test.wad',1)[1]
        cls.md=build_specialty_dict(ROOT)
        add=json.loads((BASE/'references/server-source/first/addition.json').read_text(encoding='utf-8'))
        cls.server={s['code']:s['name'] for s in add['regions'][1]['1']['skills']}

    def _expect(self,after_parse,translated):
        exp=bytearray(after_parse)
        for code in translated:exp[_slot(code):_slot(code)+0x40]=_utf16_slot(self.md[code][1])
        return bytes(exp)

    def test_dispatch_site_calls_the_cave_stub(self):
        site=to_file(self.c1,DISPATCH_SITE,4)
        self.assertEqual(struct.unpack_from('>I',self.c1,site)[0],0x48000001|((RT.CAVE_VA-DISPATCH_SITE)&0x03fffffc))

    def test_shipped_blob_regenerates(self):
        meta=json.loads((BASE/'build-v27/build-manifest.json').read_text())
        blob,rec=RT.build_cave_blob(RT.build_table16(self.md)[0])
        at=to_file(self.c1,RT.CAVE_VA,len(blob))
        self.assertEqual(self.c1[at:at+len(blob)],blob)
        self.assertEqual(meta['specialty_runtime']['blob_sha256'],rec['blob_sha256'])
        self.assertEqual(self.c1[at+len(blob):to_file(self.c1,RT.CAVE_END,1)],bytes(RT.CAVE_END-RT.CAVE_VA-len(blob)))

    def test_full_server_vocabulary_becomes_reviewed_korean(self):
        cpu,obj,seen=_execute(self.c1,RT.CAVE_VA,RT.CAVE_END-RT.CAVE_VA,self.server)
        self.assertEqual(seen['args'],(OBJ,BUF,BUF_LEN))          # parser got the caller's r3..r5
        self.assertEqual(cpu.r[3],PARSE_RET)                     # parser's return value preserved
        self.assertEqual(cpu.r[1],STACK_TOP-0x800)               # stack balanced
        self.assertEqual(bytes(obj),self._expect(seen['after_parse'],range(1,20)))
        s=_slot(3);self.assertEqual(bytes(obj[s:s+4]).decode('utf-16-be'),'운동')

    def test_fail_safe_leaves_unexpected_slots_and_everything_else(self):
        supplied={1:'Acting',2:'Arts',3:'athletics',4:'Comedy ',6:'Cooking',7:'Dance',
                  13:'Música',19:'Writing',20:'Acting',40:'South Korea'}   # code 5 not supplied
        cpu,obj,seen=_execute(self.c1,RT.CAVE_VA,RT.CAVE_END-RT.CAVE_VA,supplied)
        self.assertEqual(bytes(obj),self._expect(seen['after_parse'],[1,6,7,19]))
        self.assertEqual(bytes(obj[_slot(5):_slot(5)+0x40]),bytes(0x40))
        self.assertEqual(bytes(obj[_slot(2):_slot(2)+8]).decode('utf-16-be'),'Arts')
        self.assertEqual(cpu.r[3],PARSE_RET)

    def test_nothing_supplied_changes_nothing(self):
        _,obj,seen=_execute(self.c1,RT.CAVE_VA,RT.CAVE_END-RT.CAVE_VA,{})
        self.assertEqual(bytes(obj),seen['after_parse'])

    def test_build_v26_code_never_matched_real_utf16_slots(self):
        # Executes the preserved v26 section: on the channel's real UTF-16BE slots it changes nothing.
        c1=_content(BASE/'build-v26/mii-contest-ko-ui-test.wad',1)[1]
        size=next(s for i,o,a,s in sections(bytearray(c1)) if a==SECTION_VA)
        _,obj,seen=_execute(c1,SECTION_VA,size,self.server)
        self.assertEqual(bytes(obj),seen['after_parse'])


class V27Artifacts(unittest.TestCase):
    def test_build_v27_region4_and_only_content1_differs_from_v26(self):
        meta=json.loads((BASE/'build-v27/build-manifest.json').read_text())
        wad=(BASE/'build-v27/mii-contest-ko-ui-test.wad').read_bytes()
        self.assertEqual(__import__('hashlib').sha256(wad).hexdigest(),meta['wad_sha256'])
        t27,_=_content(BASE/'build-v27/mii-contest-ko-ui-test.wad',0);t26,_=_content(BASE/'build-v26/mii-contest-ko-ui-test.wad',0)
        self.assertEqual(t27.tmd.region,4)
        self.assertEqual(meta['changed_contents'],[0,1,3,4,5])
        diff=[i for i in range(len(t27.tmd.content_records)) if t27.get_content_by_index(i)!=t26.get_content_by_index(i)]
        self.assertEqual(diff,[1])
        self.assertEqual(meta['specialty_runtime']['cave_va'],hex(RT.CAVE_VA))

    def test_access_build_v22_reproduces_from_build_v27(self):
        from reproduce_mii_contest_access import check
        meta=check(22)
        self.assertEqual(meta['source_build'],'build-v27')
        self.assertEqual(len(meta['nas_url_ranges']),6)

    def test_hardware_v2_is_region4_copy_of_build_v27(self):
        meta=json.loads((BASE/'hardware-v2/hardware-manifest.json').read_text())
        self.assertEqual((meta['tmd_region'],meta['source_build']),(4,'build-v27'))
        self.assertTrue(meta['dol_layout_equals_build_v25'])
        self.assertEqual((BASE/'hardware-v2/mii-contest-ko-hardware.wad').read_bytes(),
                         (BASE/'build-v27/mii-contest-ko-ui-test.wad').read_bytes())
        t,_=_content(BASE/'hardware-v2/mii-contest-ko-hardware.wad',0)
        self.assertEqual(t.tmd.region,4)


if __name__=='__main__':
    unittest.main()

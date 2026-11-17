"""Build a Nintendo-only SDK language bridge; never changes NAND locale."""
import argparse,hashlib,json,shutil,struct,sys
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--install',action='store_true');args=ap.parse_args()
    base=ROOT/'workspace/channels/nintendo';out=base/'access-build-v5'
    if not out.exists():
        src=base/'access-build-v4';meta=json.loads((src/'build-manifest.json').read_text());wad=src/'nintendo-local-test.wad'
        if sha256(wad)!=meta['wad_sha256']:raise ValueError('Source build changed')
        lib=load_library();title=lib.title.Title();title.load_wad(wad.read_bytes());exe=title.get_content_by_index(1)
        address=0x8021fa20;size=108
        sections=[tuple(struct.unpack_from('>I',exe,b+4*s)[0]for b in[0,0x48,0x90])for s in range(7)]
        offset=next(o+address-a for o,a,n in sections if a<=address and address+size<=a+n)
        from capstone import Cs,CS_ARCH_PPC,CS_MODE_32,CS_MODE_BIG_ENDIAN
        decoded=list(Cs(CS_ARCH_PPC,CS_MODE_32|CS_MODE_BIG_ENDIAN).disasm(exe[offset:offset+size],address))
        assert len(decoded)==27 and decoded[-1].mnemonic=='blr'
        assert any(i.mnemonic=='li'and i.op_str=='r4, 0xb'for i in decoded)
        assert any(i.mnemonic=='bl'and i.op_str=='0x8021eeb0'for i in decoded)
        assert any(i.mnemonic=='cmplwi'and i.op_str=='r0, 9'for i in decoded)
        assert any(i.mnemonic=='lbz'and i.op_str.startswith('r3,')and '(r1)'in i.op_str for i in decoded)
        patched=bytearray(exe);patched[offset:offset+8]=struct.pack('>II',0x38600001,0x4e800020)
        title.set_content(bytes(patched),1);result=title.dump_wad();out.mkdir();target=out/'nintendo-local-test.wad';target.write_bytes(result)
        meta.update(revision=5,wad_sha256=sha256(target),source_access_revision=4,source_access_sha256=sha256(wad),sdk_language_bridge=dict(address=address,size=8,source_function_sha256=hashlib.sha256(exe[offset:offset+size]).hexdigest(),channel_language_code=1,nand_language_code=9,nand_locale_modified=False,runtime_verified=False))
        (out/'build-manifest.json').write_text(json.dumps(meta,indent=2))
        print('Built Nintendo-only language bridge; original access build and NAND settings preserved')
    if args.install:
        stopped();meta=json.loads((out/'build-manifest.json').read_text());wad=out/'nintendo-local-test.wad'
        if sha256(wad)!=meta['wad_sha256']:raise ValueError('Bridge build changed')
        target=ROOT/'workspace/sandbox/nintendo-test-v1/user/Wii';backup=PRIVATE/'nintendo-test-before-access-v5'
        if backup.exists():raise SystemExit('Previous installed title preserved')
        shutil.copytree(target/'title/00010001/48415445',backup)
        title=load_library().title.Title();title.load_wad(wad.read_bytes());load_library().nand.EmuNAND(target).install_title(title)
        (base/'active-access.json').write_text(json.dumps(dict(revision=5)))
        print('Installed language bridge only in the stopped Nintendo local-test NAND')

if __name__=='__main__':main()

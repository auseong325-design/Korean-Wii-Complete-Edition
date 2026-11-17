"""Build the Korean Set Personal Data local test WAD (WiiLink SPD fork).

Inputs are hash-checked: pinned WiiLink source (configs/personal-data-references.lock.json),
libpatcher and ogg/vorbisidec (configs/personal-data-toolchain.lock.json), the
project devkitPPC/libogc/freetype root, the OFL font and WiiLink_SPD.wad (its
TMD header fields and its first content are kept). The compiler runs in the
fixed directory tools/personal-data-sandbox/build, wiped before every build,
so a rebuild produces the same bytes. Output folders are never overwritten;
--reproduce rebuilds into workspace/private and compares. Nothing is installed.

Revision 1 is the linked DOL as is (preserved; does not boot: nothing is mapped
at the 0x80003400 channel entry). Revision 2 passes the same linked DOL through
kwce/dvd_channel_boot.py channel_boot (32-byte branch section at 0x80003400,
the method used for the KDVD channel) and checks it with kwce/personal_data_boot.py.
"""
import argparse,hashlib,json,os,shutil,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce import personal_data_fork as fork
from kwce.personal_data_font import korean_font
from kwce.personal_data_format import korean_template
from kwce.dvd_channel_boot import channel_boot
from kwce.personal_data_boot import channel_entry,header_entry,sections as dol_sections
REVISIONS=[1,2]

BASH=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Git/bin/bash.exe'
SANDBOX=ROOT/'tools/personal-data-sandbox'
BUILD=SANDBOX/'build'
TOOLCHAIN=SANDBOX/'toolchain/opt/devkitpro/portlibs/ppc'
DKP=ROOT/'tools/devkitpro-root/opt/devkitpro'
CHANNEL=ROOT/'workspace/channels/personal-data'
WIILINK=CHANNEL/'references/wiilink-patcher/spd__WiiLink_SPD.wad'
WIILINK_SHA256='8b52c0cc7af3436a3053f8be2716aac12242186474b363a4eabd08397596002d'
TITLE='000100084843434a'
LIBS='-lpatcher -lfreetype -lpng16 -lbz2 -lbrotlidec -lbrotlicommon -lz -lfat -lwiiuse -lbte -lasnd -logc -lvorbisidec -logg -lm'
WAD_NAME='personal-data-ko-local-test.wad'

def sha256(data):return hashlib.sha256(data).hexdigest()
def msys(path):
    p=Path(path).resolve().as_posix();return '/'+p[0].lower()+p[2:]if p[1]==':'else p
def blob_sha1(raw):return hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()

def verify_inputs():
    refs=ROOT/'configs/personal-data-references.lock.json';lock=json.loads(refs.read_text(encoding='utf-8'))
    if lock['commit']!=fork.SOURCE_COMMIT:raise ValueError('Pinned SPD commit differs')
    for row in lock['files']:
        if sha256((ROOT/row['path']).read_bytes())!=row['sha256']:raise ValueError('Pinned SPD source differs: '+row['upstream_path'])
    tools=ROOT/'configs/personal-data-toolchain.lock.json';tl=json.loads(tools.read_text(encoding='utf-8'))
    for source in tl['sources']:
        for path,sha in source['files'].items():
            if blob_sha1((ROOT/source['dest']/path).read_bytes())!=sha:raise ValueError('Pinned libpatcher differs: '+path)
    for name in['lib/libogg.a','lib/libvorbisidec.a','include/tremor/ivorbisfile.h','include/ogg/ogg.h']:
        if not(TOOLCHAIN/name).is_file():raise ValueError('Run scripts/prepare_personal_data_toolchain.py first')
    for name in['devkitPPC/bin/powerpc-eabi-gcc.exe','libogc/lib/wii/libogc.a','portlibs/ppc/lib/libfreetype.a','portlibs/ppc/include/freetype2/ft2build.h']:
        if not(DKP/name).is_file():raise ValueError('Project devkitPro root incomplete: '+name)
    if sha256(WIILINK.read_bytes())!=WIILINK_SHA256:raise ValueError('WiiLink SPD WAD differs from acquisition record')
    locks={p:sha256((ROOT/p).read_bytes())for p in['configs/devkit.lock.json','configs/dvd-player-toolchain.lock.json',
           'configs/personal-data-references.lock.json','configs/personal-data-toolchain.lock.json','configs/personal-data-messages-v1-ko.json']}
    return locks

def wiilink_title():
    """WiiLink_SPD.wad declares a zero content size; parse the 64-byte aligned parts."""
    raw=WIILINK.read_bytes();hs,kind,ver,cs,crl,ts,ms,ds,fs=struct.unpack_from('>IHHIIIIII',raw,0)
    if ds or hs!=32 or crl:raise ValueError('Unexpected WiiLink SPD WAD header')
    align=lambda x:(x+63)//64*64;at=align(hs);at=align(at+cs);at=align(at+ts);at=align(at+ms)
    fixed=bytearray(raw);struct.pack_into('>I',fixed,0x18,len(raw)-at)
    lib=load_library();title=lib.title.Title();title.load_wad(bytes(fixed))
    if title.tmd.title_id!=TITLE or title.tmd.boot_index!=1 or len(title.tmd.content_records)!=2:raise ValueError('WiiLink SPD identity differs')
    contents=[title.get_content_by_index(i)for i in range(2)]  # SHA-1 checked against the TMD
    return title,contents

def make(cwd,args,log):
    env=dict(os.environ,DEVKITPRO=msys(DKP),DEVKITPPC=msys(DKP/'devkitPPC'))
    env.pop('PYTHONUTF8',None)
    path=':'.join(msys(p)for p in[ROOT/'tools/msys-make/usr/bin',DKP/'devkitPPC/bin',DKP/'tools/bin'])
    with log.open('a',encoding='utf-8')as f:
        f.write(f'## make {args} in {cwd.name}\n');f.flush()
        result=subprocess.run([str(BASH),'-c',f'export PATH="{path}:$PATH"; make {args}'],cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT)
    if result.returncode:raise SystemExit(f'make failed in {cwd.name}; see {log}')

def compile_dol(log,jobs):
    if BUILD.exists():shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)
    lib_src=BUILD/'libpatcher';shutil.copytree(ROOT/'workspace/channels/personal-data/references/libpatcher-3e51f23a',lib_src)
    make(lib_src,'',log)
    built=sorted(lib_src.rglob('libpatcher.a'))
    if len(built)!=1:raise SystemExit('libpatcher.a not produced')
    stage=BUILD/'stage';(stage/'include/libpatcher').mkdir(parents=True);(stage/'lib').mkdir()
    shutil.copy2(lib_src/'source/libpatcher.h',stage/'include/libpatcher/libpatcher.h');shutil.copy2(built[0],stage/'lib/libpatcher.a')
    tree=BUILD/'set-personal-data';shutil.copytree(fork.SOURCE,tree)
    font,font_record=korean_font()
    template,template_record=korean_template((fork.SOURCE/'data/title/pd_decrypted.dat').read_bytes())
    template_record['sha256']=sha256(template)
    record=fork.apply(tree,font,template)
    libdirs=f'$(PORTLIBS) {msys(TOOLCHAIN)} {msys(stage)}'
    make(tree,f"-j{jobs} LIBDIRS='{libdirs}' LIBS='{LIBS}'",log)
    dol=tree/'set-personal-data.dol';elf=tree/'set-personal-data.elf'
    if not dol.is_file():raise SystemExit('DOL not produced')
    return dol.read_bytes(),elf.read_bytes(),record,font_record,template_record

def assemble(dol):
    title,original=wiilink_title()
    tmd_before=dict(ios=title.tmd.ios_tid,region=title.tmd.region,version=title.tmd.title_version,boot=title.tmd.boot_index,
                    access=title.tmd.access_rights if hasattr(title.tmd,'access_rights')else None)
    title.set_content(dol,1);wad=title.dump_wad()
    check=load_library().title.Title();check.load_wad(wad)
    if check.tmd.title_id!=TITLE or check.get_content_by_index(0)!=original[0]or check.get_content_by_index(1)!=dol:raise ValueError('WAD content roundtrip')
    after=dict(ios=check.tmd.ios_tid,region=check.tmd.region,version=check.tmd.title_version,boot=check.tmd.boot_index,
               access=check.tmd.access_rights if hasattr(check.tmd,'access_rights')else None)
    if after!=tmd_before:raise ValueError('TMD header fields changed')
    return wad,after,sha256(original[1])

def channel_dol(linked):
    """Add the 0x80003400 channel entry (revision 2+) and prove nothing else moved."""
    dol,adapter=channel_boot(linked)
    if not adapter.get('required'):raise ValueError('Linked DOL unexpectedly starts at the channel entry')
    entry=channel_entry(dol)
    if int(entry['branch_target'],16)!=header_entry(linked)or header_entry(dol)!=0x80003400:raise ValueError('Channel entry does not reach the linked _start')
    before={(a,s):linked[o:o+s]for _,o,a,s in dol_sections(linked)}
    after={(a,s):dol[o:o+s]for _,o,a,s in dol_sections(dol)}
    if any(after.get(k)!=v for k,v in before.items())or len(after)!=len(before)+1:raise ValueError('Channel entry changed linked DOL sections')
    return dol,dict(adapter,linked_entry=hex(header_entry(linked)),check=entry)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,choices=REVISIONS,default=REVISIONS[-1]);ap.add_argument('--reproduce',action='store_true');ap.add_argument('--jobs',type=int,default=8)
    ap.add_argument('--trial',action='store_true',help='compile into workspace/private/personal-data-trial-N (no numbered build)')
    args=ap.parse_args();out=CHANNEL/f'build-v{args.revision}';expected=None
    if args.trial:
        n=1
        while(ROOT/f'workspace/private/personal-data-trial-{n}').exists():n+=1
        out=ROOT/f'workspace/private/personal-data-trial-{n}'
    elif args.reproduce:
        expected=(out/WAD_NAME).read_bytes();n=1
        while(ROOT/f'workspace/private/personal-data-reproduce-v{args.revision}-{n}').exists():n+=1
        out=ROOT/f'workspace/private/personal-data-reproduce-v{args.revision}-{n}'
    elif out.exists():raise SystemExit('Existing personal-data build preserved')
    locks=verify_inputs()
    logs=ROOT/'workspace/private';n=1
    while(logs/f'personal-data-build-v{args.revision}-{n}.log').exists():n+=1
    log=logs/f'personal-data-build-v{args.revision}-{n}.log';log.write_text('',encoding='utf-8')
    dol,elf,fork_record,font_record,template_record=compile_dol(log,args.jobs)
    linked=dol;boot=None
    if args.revision>=2:dol,boot=channel_dol(linked)
    wad,tmd,wiilink_dol=assemble(dol)
    out.mkdir(parents=True);(out/WAD_NAME).write_bytes(wad);(out/'boot.dol').write_bytes(dol);(out/'boot.elf').write_bytes(elf)
    catalog,count=fork.ko_catalog()
    manifest=dict(revision=args.revision,title_id=TITLE,base='WiiLink SPD (WiiLink24/set-personal-data, GPL-3.0)',upstream_commit=fork.SOURCE_COMMIT,
        wad_sha256=sha256(wad),wad_bytes=len(wad),dol_sha256=sha256(dol),dol_bytes=len(dol),wiilink_wad_sha256=WIILINK_SHA256,wiilink_dol_sha256=wiilink_dol,
        tmd=tmd,changed_contents=[1],preserved_contents=[0],catalog=dict(language='ko',messages=count,sha256=sha256(catalog),selected_for='CONF_LANG_KOREAN (9)'),
        font=font_record,pd_template=template_record,
        fork=fork_record,toolchain_locks=locks,build_dir='tools/personal-data-sandbox/build (wiped before each build)',
        service_endpoints=0,local_only=True,full_localization_complete=False,hardware_success_verified=False,
        licenses=dict(channel='GPL-3.0 (personal use, no public WAD distribution)',libpatcher='MIT',font='OFL-1.1',ogg_vorbisidec='BSD-3-Clause'))
    if boot is not None:
        manifest.update(linked_dol_sha256=sha256(linked),linked_dol_bytes=len(linked),channel_boot=boot,
            boot_elf='linked program without the 0x80003400 channel entry stub',
            supersedes='build-v1 (no DOL section at the 0x80003400 channel entry; Dolphin IntCPU panic at launch)')
    (out/'build-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    if expected is not None:
        same=expected==wad
        (out/'reproduction.json').write_text(json.dumps(dict(revision=args.revision,byte_identical=same,expected_sha256=sha256(expected),actual_sha256=sha256(wad)),indent=2)+'\n',encoding='utf-8')
        if not same:raise SystemExit('Personal-data reproduction differs; original preserved, private result retained')
        print('PASS: personal-data build-v%d byte-identical reproduction'%args.revision)
    else:print('Built %s: WAD %s, DOL %d bytes, %d catalog messages, font %d glyphs; not installed'%(out.relative_to(ROOT).as_posix(),manifest['wad_sha256'][:16],len(dol),count,font_record['glyphs']))
if __name__=='__main__':main()

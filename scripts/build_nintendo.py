"""Nintendo Channel Korean build. Revision 3+: full reviewed message table for every
USA BMG (UE/UF/US) and the console's Korean HOME Menu. v2 builder snapshot is kept in
workspace/channels/nintendo/build_nintendo_v2_snapshot.py.

Revisions 3..15 are built from the original WAD (v3/v4 here; v5..v15 by build_nintendo_banner_v9.py and its
predecessors on top of build-v4) and their code below is unchanged. Revision 16+ is DERIVED: it is made on
top of the stored parent build (v16 = build-v15), never from the original.

  build_nintendo.py --revision 16|17               # write build-v16 (content 6) / build-v17 (content 5) and verify
  build_nintendo.py --revision 16|17 --reproduce   # rebuild in memory, require identical WAD + manifest bytes

Revision 16 = build-v15 + the Korean HOME Menu for the DEFAULT language slot (content 6). A Korean console
(language 9) falls past the SDK's 0..6 into slot 0 (0x80048a60), the Japanese default, so it loaded
HomeButtonN/LZ77_homeBtn.arc (still the Japanese original: only ENG..SPA had been replaced) and message
column 0 of HomeButtonN/home*.csv (Japanese). kwce.home_menu.korean_default_home overwrites the two default
archives with the console's own Korean archives and the four message tables with Korean text in all seven
columns, in place: content 6 keeps its length and every other file its offset. Content 1 (executable) and
all other contents are byte-identical to build-v15.
Revision 17 = build-v16 + content 5 HomeButton3/home.csv, the ten-column table the executable really loads
(0x8004f394 reads home.csv from group 3 = content 5; the archives come from group 4 = content 6):
kwce.home_menu.korean_official_table_home copies the official Korean column 9 into columns 0..6, in place.
Test-bench note: access builds patch SCGetLanguage to always answer English (1), which hides the default
slot; to see these fixes on screen install the unpatched build itself (install_access_build.py).
"""
import argparse,copy,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,ChannelArchive,sha256
from kwce.channel_korean_font import korean_shared_fonts
from kwce.votes_resources import translate_bmg

OUTPUT='nintendo-ko-ui-test.wad'
DERIVED={16:15,17:16}   # revision -> parent revision (built on the stored parent build, not on the original WAD)
HOME_CONTENT=6          # revision 16 changes this content; revision 17 changes TABLE_CONTENT
TABLE_CONTENT=5
DERIVED_PROBLEM='A Korean console (language 9) uses HOME slot 0, the Japanese default; build-v15 only had ENG..SPA replaced, so the HOME Menu drew the Japanese archive and message column 0'
DERIVED_EXECUTABLE_READS='HomeButton2|3/LZ77_homeBtn.arc (default slot: language >= 7 -> 0, 0x80048a60) and message column 0 of HomeButton2|3/home_nosave.csv and home.csv (content 6)'
TABLE_PROBLEM='The executable loads HomeButton3/home.csv from group 3 = content 5 (0x8004f394), not the seven-column copies in content 6; slot 0 is the Japanese column of that official ten-column table, so the Korean HOME archive of build-v16 would have been paired with Japanese text'
TABLE_EXECUTABLE_READS='HomeButton3/home.csv in content 5 (group 3), column 0 for a Korean console (language 9 -> slot 0); archive HomeButton3/LZ77_homeBtn.arc stays in content 6 (group 4)'

def derived_build(revision):
    """Revision 16: build-v15 with only content 6 changed; revision 17: build-v16 with only content 5 changed
    (see the module docstring). Returns (wad, manifest dict)."""
    base=ROOT/'workspace/channels/nintendo';parent=DERIVED[revision];parent_dir=base/f'build-v{parent}'
    parent_meta=json.loads((parent_dir/'build-manifest.json').read_text(encoding='utf-8'));parent_wad=(parent_dir/OUTPUT).read_bytes()
    if sha256(parent_wad)!=parent_meta['wad_sha256']:raise ValueError(f'build-v{parent} WAD differs from its manifest; refusing to build on it')
    lib=load_library();title=lib.title.Title();title.load_wad(parent_wad)
    count=len(title.tmd.content_records);original=[title.get_content_by_index(i)for i in range(count)]
    from kwce.home_menu import korean_default_home,korean_official_table_home
    if revision==16:index,key,problem,reads=HOME_CONTENT,'home_default_fix',DERIVED_PROBLEM,DERIVED_EXECUTABLE_READS;fixed,record=korean_default_home(original[index])
    else:index,key,problem,reads=TABLE_CONTENT,'home_table_fix',TABLE_PROBLEM,TABLE_EXECUTABLE_READS;fixed,record=korean_official_table_home(original[index])
    title.set_content(fixed,index)
    wad=title.dump_wad();check=lib.title.Title();check.load_wad(wad);before=lib.title.Title();before.load_wad(parent_wad)
    identity=lambda t:(t.tmd.region,t.tmd.title_id,t.tmd.title_version,t.tmd.ios_tid,len(t.tmd.content_records))
    if identity(check)!=identity(before):raise ValueError('TMD identity changed')
    changed=[i for i in range(count)if check.get_content_by_index(i)!=original[i]]
    if changed!=[index]:raise ValueError(f'Expected only content {index} to change, got {changed}')
    meta=copy.deepcopy(parent_meta)
    meta.update({'revision':revision,'parent_revision':parent,'source_build':f'build-v{parent}','wad_sha256':sha256(wad),'runtime_verified':False,'installed':False,
        f'content_{index}_original_size_preserved':True,'changed_from_parent':changed,'changed_content_indices':changed,
        key:dict(problem=problem,executable_reads=reads,**record,**{f'other_content_{index}_files_unchanged':True,'content_1_unchanged':True,'hardware_verified':False})})
    return wad,meta

def derived_main(args):
    if args.revision not in DERIVED:raise SystemExit(f'Revision {args.revision} has no builder in this script (derived revisions: {sorted(DERIVED)})')
    wad,meta=derived_build(args.revision);out=ROOT/f'workspace/channels/nintendo/build-v{args.revision}'
    manifest=json.dumps(meta,ensure_ascii=False,indent=2).encode('utf-8')+b'\n'
    if args.reproduce:
        if not out.exists():raise SystemExit(f'build-v{args.revision} does not exist yet; run without --reproduce first')
        same=(out/OUTPUT).read_bytes()==wad and (out/'build-manifest.json').read_bytes()==manifest
        print(json.dumps(dict(reproduced_byte_identical=same,revision=args.revision,wad_sha256=sha256(wad))));raise SystemExit(0 if same else 1)
    if out.exists():raise SystemExit('Existing Nintendo build preserved')
    out.mkdir();(out/OUTPUT).write_bytes(wad);(out/'build-manifest.json').write_bytes(manifest)
    fix=meta['home_default_fix' if args.revision==16 else 'home_table_fix']
    files=[(r['file'],r['bytes_before'],r['bytes_after'])for r in fix['default_archives']+fix['dialog_csv']]if args.revision==16 else[(fix['file'],fix['bytes_before'],fix['bytes_after'])]
    print(json.dumps(dict(status='built',revision=args.revision,base=f'build-v{DERIVED[args.revision]}',wad_sha256=meta['wad_sha256'],
        changed_contents=meta['changed_from_parent'],files=files),indent=2))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True)
    ap.add_argument('--reproduce',action='store_true',help='revision 16+: rebuild in memory and require identical bytes');args=ap.parse_args()
    if args.revision>=16:return derived_main(args)
    if args.reproduce:raise SystemExit('--reproduce here covers revision 16+; v9..v15 reproduce with build_nintendo_banner_v9.py --reproduce --revision N')
    if not 3<=args.revision<=100:raise SystemExit('Revision bounds')
    base=ROOT/'workspace/channels/nintendo';out=base/f'build-v{args.revision}'
    if out.exists():raise SystemExit('Existing Nintendo build preserved')
    cfg=json.loads((ROOT/'configs/nintendo-messages-ko.json').read_text(encoding='utf-8'));source=base/'originals/nintendo-usa-wiilink-archive.wad'
    if sha256(source.read_bytes())!=cfg['source_sha256']:raise ValueError('Nintendo source differs')
    lib=load_library();title=lib.title.Title();title.load_wad(source.read_bytes());original=[title.get_content_by_index(i)for i in range(len(title.tmd.content_records))]
    archive=ChannelArchive(original[5]);count=0
    full=json.loads((ROOT/'configs/nintendo-messages-full-ko.json').read_text(encoding='utf-8'))['messages']
    mapping=dict(full);mapping.update(cfg['files']['5/message/promotion_message_UE.bmg'])
    # Korean-only build: the US English, French and Spanish tables all show Korean.
    for name in['message/promotion_message_UE.bmg','message/promotion_message_UF.bmg','message/promotion_message_US.bmg']:
        translated,n=translate_bmg(archive.get(name),mapping);count+=n;archive=ChannelArchive(archive.replace(name,translated))
    # Literal layout labels that the channel does not replace at run time.
    from kwce.channels import layout_sections,textbox,replace_textbox,rebuild_layout
    literals={'OK':'확인','OK#':'확인','Press the A Button to begin.':'A 버튼을 눌러 시작해 주세요.','Buy':'구입','Age Rating Information':'연령 등급 정보'};layout_count=0
    for name in[n for n in archive.files if n.startswith('layout/')and n.endswith('.arc')]:
        inner=ChannelArchive(archive.get(name));changed_inner=False
        for path in[p for p in inner.files if p.endswith('.brlyt')]:
            sections=layout_sections(inner.get(path));hit=False
            for i,sec in enumerate(sections):
                e=textbox(sec)
                if e and e[1]in literals:sections[i]=replace_textbox(sec,literals[e[1]]);hit=True;layout_count+=1
            if hit:inner=ChannelArchive(inner.replace(path,rebuild_layout(inner.get(path),sections)));changed_inner=True
        if changed_inner:archive=ChannelArchive(archive.replace(name,inner.compact()))
    content=archive.compact()
    if len(content)>len(original[5]):raise ValueError('Nintendo original content capacity exceeded')
    content+=bytes(len(original[5])-len(content));title.set_content(content,5)
    shared,font_record=korean_shared_fonts()
    if set(ChannelArchive(shared).files)!=set(ChannelArchive(original[3]).files):raise ValueError('Font archive mismatch')
    title.set_content(shared,3)
    banner=bytearray(original[0]);assert banner[0x80:0x84]==b'IMET'
    for language in range(10):
        at=0x40+0x5c+84*language;name='닌텐도 채널'.encode('utf-16-be');banner[at:at+84]=name+bytes(84-len(name))
    banner[0x630:0x640]=bytes(16);banner[0x630:0x640]=hashlib.md5(banner[0x40:0x640]).digest();title.set_content(bytes(banner),0);title.tmd.region=4
    from kwce.home_menu import korean_home_menu
    home,home_record=korean_home_menu(original[6]);title.set_content(home,6)
    from kwce.ppc_patch import utf16_slots
    exe_cfg=json.loads((ROOT/'configs/nintendo-executable-ko.json').read_text(encoding='utf-8'))
    rows=[(int(va,16),src,dst)for va,src,dst in exe_cfg['short']]+[(int(va,16),None,dst)for va,dst in exe_cfg['long'].items()]
    executable,exe_rows=utf16_slots(original[1],rows);title.set_content(executable,1)
    wad=title.dump_wad();check=lib.title.Title();check.load_wad(wad)
    changed=[i for i in range(len(original))if check.get_content_by_index(i)!=original[i]];assert set(changed)<={0,1,3,5,6},changed
    out.mkdir();(out/'nintendo-ko-ui-test.wad').write_bytes(wad)
    result=dict(revision=args.revision,home_menu=home_record,layout_literals=layout_count,executable_strings=len(exe_rows),full_messages_config_sha256=sha256((ROOT/'configs/nintendo-messages-full-ko.json').read_bytes()),title_id=title.tmd.title_id,wad_sha256=sha256(wad),translated_messages=count,changed_contents=changed,content_5_original_size_preserved=True,font_record=font_record,installed=False,runtime_verified=False)
    (out/'build-manifest.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()

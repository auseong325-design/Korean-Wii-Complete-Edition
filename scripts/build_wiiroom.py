"""Immutable partial Wii Room Korean/local HTTP test WAD, originals untouched."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,ChannelArchive,compress_lz10,sha256
from kwce.votes_resources import translate_bmg
from kwce.channel_korean_font import korean_shared_fonts
from kwce.opera_font import korean_opera_font
from kwce.wiiroom_formats import decompress_lz11,reencode_lz11_same_size,compress_lz10_optimal

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True);ap.add_argument('--reproduce',action='store_true');args=ap.parse_args()
    if args.revision not in [*range(1,38),*range(40,52),54,55,56,57,58,59,60,61]:raise SystemExit('Only revisions 1 to 37, 40 to 51, 54/55 (JP list-font fallback), 56/57 (tight Wii의 wordmark) and 58/59 (geometric wordmark) and 60/61 (restore v57 wordmark, retain weather and labels) are defined; failed 38/39 are reserved')
    out=ROOT/f'workspace/channels/wiiroom/build-v{args.revision}'
    expected=None
    if args.reproduce:
        expected=(out/'wiiroom-ko-local-test.wad').read_bytes();number=1
        while(ROOT/f'workspace/private/wiiroom-reproduce-v{args.revision}-{number}').exists():number+=1
        out=ROOT/f'workspace/private/wiiroom-reproduce-v{args.revision}-{number}'
    if out.exists():raise SystemExit('Existing Wii Room build preserved')
    # Revision 7+: reviewed Korean for every text slot (digit/punctuation-only slots keep the original).
    cfg_path=ROOT/('configs/wiiroom-messages-full-ko.json'if args.revision>=8 else'configs/wiiroom-messages-full-v7-ko.json'if args.revision==7 else'configs/wiiroom-messages-v1-ko.json'if args.revision<=5 and(ROOT/'configs/wiiroom-messages-v1-ko.json').exists()else'configs/wiiroom-messages-ko.json')
    if args.revision in(8,9):cfg_path=ROOT/'configs/wiiroom-messages-full-v8-ko.json'
    cfg=json.loads(cfg_path.read_text(encoding='utf-8'))
    message_overrides=None
    if args.revision>=58:
        # Revision 58+: 'Reset' -> 다시 시작 (channel restart), two-line '비슷한/동영상'.
        # The full config stays unchanged so 8-57 reproduce byte for byte.
        override_path=ROOT/'configs/wiiroom-messages-v58-ko.json';overrides=json.loads(override_path.read_text(encoding='utf-8'))
        if overrides['base']!=cfg_path.name or not set(overrides['messages'])<=set(cfg['messages']):raise ValueError('Wii Room v58 message overrides do not match the base config')
        cfg['messages'].update(overrides['messages']);message_overrides=dict(config=override_path.name,slots=sorted(overrides['messages'],key=int))
    source=ROOT/'workspace/channels/wiiroom/originals/wiiroom-english-wiilink-archive.wad'
    if sha256(source.read_bytes())!=cfg['source_sha256']:raise ValueError('Wii Room original changed')
    lib=load_library();from libWiiPy.archive import decompress_lz77
    title=lib.title.Title();title.load_wad(source.read_bytes());original=[title.get_content_by_index(i)for i in range(16)]
    if title.tmd.title_id!='000100014843494a'or title.tmd.boot_index!=15:raise ValueError('Unexpected title/boot index')
    a=ChannelArchive(original[2]);bmg,count=translate_bmg(decompress_lz77(a.get('msg/message.lex')),cfg['messages'])
    compressed=compress_lz10_optimal(bmg)
    if decompress_lz77(compressed)!=bmg:raise ValueError('Message LZ10 roundtrip')
    main_archive=ChannelArchive(a.replace('msg/message.lex',compressed));content=main_archive.compact()
    if len(content)>len(original[2]):raise ValueError('Main archive capacity exceeded')
    content+=bytes(len(original[2])-len(content));textures=None
    if args.revision>=8:
        # Revision 8+: Korean room menu, theatre, age filter and date textures.
        from kwce.wiiroom_visual import korean_textures
        content,textures=korean_textures(content,extended=args.revision>=10,branding=args.revision>=12,refined_help=args.revision>=14,native_wordmark=args.revision>=22)
    runtime_home_records=None
    if args.revision>=16:
        from kwce.wiiroom_home import korean_runtime_home
        content,runtime_home_records=korean_runtime_home(content)
        if len(content)>len(original[2]):raise ValueError('Room HOME archive capacity')
        content+=bytes(len(original[2])-len(content))
    manual_record=None
    if args.revision>=18:
        from kwce.wiiroom_manual import korean_manual
        content,controller,manual_record=korean_manual(content,original[4],legacy_wrapper=args.revision in(18,19),smooth=args.revision>=40)
        if args.revision in(44,45):
            from kwce.wiiroom_manual_csv_v44 import korean_network_slots
            content=korean_network_slots(content);manual_record['network_prompt_columns']=10
        if args.revision>=22:
            from kwce.wiiroom_visual import fit_archive_capacity
            content,extra=fit_archive_capacity(content,len(original[2]),textures['recompressed_layouts'])
            textures['recompressed_layouts'].extend(extra)
        if len(content)>len(original[2]):raise ValueError('Room guide archive capacity')
        content+=bytes(len(original[2])-len(content));title.set_content(controller,4)
    help_examples=None
    if args.revision>=24:
        from kwce.wiiroom_help_examples import korean_help_examples
        from kwce.wiiroom_visual import fit_archive_capacity
        content,help_examples=korean_help_examples(content,refined=args.revision>=28,polished=args.revision>=32)
        content,extra=fit_archive_capacity(content,len(original[2]),textures['recompressed_layouts'])
        textures['recompressed_layouts'].extend(extra)
        for p in help_examples['changed_layouts']:
            if p not in textures['recompressed_layouts']:textures['recompressed_layouts'].append(p)
    title.set_content(content,2)
    static_labels=None
    if args.revision>=32:
        from kwce.wiiroom_static import korean_static_labels
        content,static_labels=korean_static_labels(content,preserve_capacity=args.revision>=34)
        for p in static_labels['changed_layouts']:
            if p not in textures['recompressed_layouts']:textures['recompressed_layouts'].append(p)
        content,extra=fit_archive_capacity(content,len(original[2]),textures['recompressed_layouts'])
        textures['recompressed_layouts'].extend(extra);title.set_content(content,2)
    ui_refinement=None
    if args.revision>=36:
        from kwce.wiiroom_ui_v36 import refine_content
        content,ui_refinement=refine_content(content,original[2],geometric=args.revision in (58,59))
        for p in ui_refinement['changed_layouts']:
            if p not in textures['recompressed_layouts']:textures['recompressed_layouts'].append(p)
        content,extra=fit_archive_capacity(content,len(original[2]),textures['recompressed_layouts'])
        textures['recompressed_layouts'].extend(extra);title.set_content(content,2)
    weather=None
    if args.revision>=58:
        # Revision 58+: the room's weather board is a channel texture (not server data).
        from kwce.wiiroom_weather_v58 import korean_weather_board
        content,weather=korean_weather_board(content)
        content,extra=fit_archive_capacity(content,len(original[2]),textures['recompressed_layouts'])
        textures['recompressed_layouts'].extend(extra);title.set_content(content,2)
    strap=None
    if args.revision>=26:
        if args.revision>=36:
            from kwce.wiiroom_kart_strap import korean_kart_strap
            translated,strap=korean_kart_strap(original[13])
        else:
            from kwce.wiiroom_strap import korean_strap
            translated,strap=korean_strap(original[13])
        title.set_content(translated,13)
    fonts,font_record=korean_shared_fonts()
    if args.revision>=7:
        from kwce.channel_font import font_data
        characters={ord(c)for v in cfg['messages'].values()for c in v if ord(c)>=32 and c not in'　'}
        for name in ChannelArchive(fonts).files:
            raw=ChannelArchive(fonts).get(name);_,mapping,_=font_data(b'RFNT'+raw[4:])
            if not characters<=mapping.keys():raise ValueError(f'Translated glyph missing in {name}: '+''.join(sorted(chr(c)for c in characters-mapping.keys()))[:40])
    if set(ChannelArchive(fonts).files)!=set(ChannelArchive(original[9]).files):raise ValueError('Shared font names differ')
    jp_list_fallback=None
    if args.revision>=54:
        # Supply-data Japanese (news/room/category lists) renders '?' for kanji
        # because the Korean shared font has none. Append JIS level 1 kanji from
        # the channel's own original Japanese font as fallback glyphs.
        from kwce.wiiroom_jp_fallback import korean_list_fallback
        fonts,jp_list_fallback=korean_list_fallback(fonts,original[9])
    title.set_content(fonts,9);opera,opera_record=korean_opera_font(original[12]);title.set_content(opera,12)
    banner=bytearray(original[0])
    if banner[0x80:0x84]!=b'IMET':raise ValueError('Expected IMET')
    for i in range(10):
        at=0x40+0x5c+84*i;name='Wii의 방'.encode('utf-16-be');banner[at:at+84]=name+bytes(84-len(name))
    banner_records=None
    if args.revision>=12:
        from kwce.wiiroom_banner import korean_banner
        banner,banner_records=korean_banner(bytes(banner),native_wordmark=args.revision>=22,balanced=args.revision>=36,tight=args.revision>=56,geometric=args.revision in (58,59));banner=bytearray(banner)
        from kwce.home_menu import korean_home_menu,KOREAN_SHARED,SOURCES
        home,home_record=korean_home_menu(original[3],fix_dialogs=True,all_dialog_languages=True)
        home=ChannelArchive(home);korean=ChannelArchive(KOREAN_SHARED.read_bytes())
        for folder,source in SOURCES.items():home=ChannelArchive(home.replace(folder+'/LZ77_homeBtn.arc',korean.get(source)))
        title.set_content(home.compact(),3)
        if args.revision>=42:
            from kwce.wiiroom_manual_font_v42 import korean_prompt_fonts
            home,font_record_prompt=korean_prompt_fonts(title.get_content_by_index(3));title.set_content(home,3)
            home_record['manual_prompt_fonts']=font_record_prompt
        if args.revision>=46:
            from kwce.wiiroom_manual_override_v46 import korean_nwm_font_overrides
            controller,overrides=korean_nwm_font_overrides(title.get_content_by_index(4),title.get_content_by_index(3))
            title.set_content(controller,4);manual_record['prompt_font_overrides']=overrides
    banner[0x630:0x640]=bytes(16);banner[0x630:0x640]=hashlib.md5(banner[0x40:0x640]).digest();title.set_content(bytes(banner),0)
    raw=decompress_lz11(original[1]);old=b'http://prod.wiilink24.com/conf/first.bin';new=b'http://127.0.0.2/conf/first.bin'
    if raw.count(old+b'\0')!=1:raise ValueError('Expected unique first endpoint')
    edited=raw.replace(old,new+bytes(len(old)-len(new)))
    compatibility=None
    if args.revision==2:
        from kwce.wiiroom_compat import patch_resource_language
        compatible,compatibility=patch_resource_language(raw);edited=compatible.replace(old,new+bytes(len(old)-len(new)))
    if args.revision in(3,4):
        from kwce.wiiroom_compat import patch_null_open_diagnostic
        compatible,compatibility=patch_null_open_diagnostic(raw);edited=compatible.replace(old,new+bytes(len(old)-len(new)))
        if args.revision==4:
            from kwce.wiiroom_compat import patch_resource_language
            from kwce.ppc_patch import to_file
            language,_=patch_resource_language(raw);at=to_file(raw,0x80307fac);edited=edited[:at]+language[at:at+4]+edited[at+4:];compatibility['resource_language_slot']=0
    # Revision 9: v8 for real hardware; the first-config URL stays the WiiLink server.
    # Revisions 58/60 are hardware builds; 59/61 are their Dolphin local twins.
    hardware=args.revision in(9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,41,43,45,47,49,51,55,57,58,60)
    if args.revision>=5:
        from kwce.wiiroom_compat import patch_null_path_compat,patch_resource_language
        from kwce.ppc_patch import to_file
        compatible,compatibility=patch_null_path_compat(raw);language,_=patch_resource_language(raw);at=to_file(raw,0x80307fac);edited=compatible[:at]+language[at:at+4]+compatible[at+4:];compatibility['resource_language_slot']=0
        if not hardware:edited=edited.replace(old,new+bytes(len(old)-len(new)))
        if args.revision in(11,13,15,17,19,21,23,25,27):
            # The null-path workaround exists for Dolphin HostFS only. Real
            # hardware keeps the original NAND implementation and semantics.
            edited,compatibility=patch_resource_language(raw)
            compatibility['dolphin_null_path_workaround']=False
        if args.revision in(28,29):
            from kwce.wiiroom_compat import patch_null_open_missing
            edited,compatibility=patch_null_open_missing(raw)
            at=to_file(raw,0x80307fac);edited=edited[:at]+language[at:at+4]+edited[at+4:]
            compatibility['resource_language_slot']=0
            if not hardware:edited=edited.replace(old,new+bytes(len(old)-len(new)))
        if args.revision>=30:
            from kwce.wiiroom_compat import patch_korean_area
            edited,compatibility=patch_korean_area(raw)
            at=to_file(raw,0x80307fac);edited=edited[:at]+language[at:at+4]+edited[at+4:]
            compatibility['resource_language_slot']=0
            if not hardware:edited=edited.replace(old,new+bytes(len(old)-len(new)))
    socket_startup=None
    if args.revision>=48:
        from kwce.channel_socket_startup import patch as patch_socket
        edited,socket_startup=patch_socket(edited,'wiiroom')
    ipc_deadline=None
    if args.revision>=50:
        from kwce.channel_ipc_deadline import patch as patch_ipc
        edited,ipc_deadline=patch_ipc(edited,'wiiroom')
    packed=reencode_lz11_same_size(original[1],edited);title.set_content(packed,1);title.tmd.region=4
    wad=title.dump_wad();check=lib.title.Title();check.load_wad(wad)
    if expected is not None and wad!=expected:raise ValueError('Preserved WAD reproduction differs')
    changed=[i for i in range(16)if check.get_content_by_index(i)!=original[i]]
    if set(changed)!=({0,1,2,3,4,9,12,13}if args.revision>=26 else{0,1,2,3,4,9,12}if args.revision>=18 else{0,1,2,3,9,12}if args.revision>=12 else{0,1,2,9,12}):raise ValueError('Unexpected content change')
    check_archive=ChannelArchive(check.get_content_by_index(2))
    allowed={'msg/message.lex'}|set(textures['recompressed_layouts']if textures else[])
    if runtime_home_records:allowed.update(r['file']for r in runtime_home_records)
    if manual_record:
        allowed.add('hbm/manual.jpg')
        if manual_record.get('network_prompt_korean'):allowed.add('hbm/HomeButton3/network.csv')
    if weather:allowed.add(weather['file'])
    if any(a.get(p)!=check_archive.get(p)for p in a.files if p not in allowed):raise ValueError('Other resources changed')
    out.mkdir();(out/'wiiroom-ko-local-test.wad').write_bytes(wad)
    result=dict(revision=args.revision,title_id=title.tmd.title_id,boot_index=15,wad_sha256=sha256(wad),source_sha256=cfg['source_sha256'],translated_message_slots=count,total_message_slots=643,message_config=cfg_path.name,korean_textures=textures,changed_contents=changed,main_content_size_preserved=True,all_layouts_animations_preserved=textures is None,layout_textures_changed=bool(textures),executable_raw_size_preserved=True,executable_compressed_size=len(packed),original_executable_compressed_size=len(original[1]),resource_language_compatibility=compatibility,local_first_url=None if hardware else'http://127.0.0.2/conf/first.bin',target='hardware'if hardware else'dolphin-local-replay',shared_fonts=font_record,opera_font=opera_record,full_localization_complete=False,runtime_verified=False)
    if banner_records:result.update(banner_wordmarks=banner_records,korean_home=home_record)
    if runtime_home_records:result['runtime_home_messages']=runtime_home_records
    if manual_record:result['controller_guide']=manual_record
    if help_examples:result['help_examples']=help_examples
    if strap:result['wrist_strap']=strap
    if static_labels:result['static_labels']=static_labels
    if ui_refinement:result['ui_refinement']=ui_refinement
    if socket_startup:result['socket_startup']=socket_startup
    if ipc_deadline:result['ipc_deadline']=ipc_deadline
    if jp_list_fallback:result['jp_list_fallback']=jp_list_fallback
    if weather:result['weather_board']=weather
    if message_overrides:result['message_overrides']=message_overrides
    (out/'build-manifest.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items()if k not in('shared_fonts','opera_font')}))

if __name__=='__main__':main()

"""Votes message localization; offline build only, no NAND mutation.

Revision 11+ merges configs/votes-messages-extra-ko.json (all remaining
messages). Revision 12+ moves the Cmn player/result text boxes that use the
Hangul-less Vote_RodinNTLGPro_DB_40_I4A number font onto the layout's Revo
system font (index 0), which is the Korean shared font. Builder snapshots:
workspace/channels/votes/build_votes_ui_v10_snapshot.py and _v11_snapshot.py."""
import argparse
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,ChannelArchive,sha256
from kwce.votes_resources import decode_yaz0,encode_yaz0,translate_bmg,bmg_sections,bmg_message,render_bmg_translation
from kwce.channel_korean_font import korean_shared_fonts
from kwce.channel_font import font_data

NUMBER_ONLY={b'T_PercentL_00',b'T_PercentR_00',b'T_hittingR_02',b'T_balloon_00'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True);ap.add_argument('--reproduce',action='store_true');args=ap.parse_args()
    if not 11<=args.revision<=100:raise SystemExit('Revision bounds')
    base=ROOT/'workspace/channels/votes';out=base/f'build-v{args.revision}';expected=None
    if args.reproduce:
        # --reproduce rebuilds into workspace/private and requires the WAD + manifest to match build-vN.
        expected=((out/'votes-ko-ui-test.wad').read_bytes(),(out/'build-manifest.json').read_bytes());n=1
        while(ROOT/f'workspace/private/votes-ui-reproduce-v{args.revision}-{n}').exists():n+=1
        out=ROOT/f'workspace/private/votes-ui-reproduce-v{args.revision}-{n}'
    if out.exists():raise SystemExit('Existing Votes build preserved')
    config=json.loads((ROOT/'configs/votes-messages-ko.json').read_text(encoding='utf-8'))
    config['messages'].update(json.loads((ROOT/'configs/votes-messages-extra-ko.json').read_text(encoding='utf-8'))['messages'])
    source=base/'originals/votes-usa-wiilink-archive.wad'
    if sha256(source.read_bytes())!=config['source_sha256']:raise ValueError('Source mismatch')
    v1=base/'build-v1/votes-ko-metadata-test.wad';meta=json.loads(v1.with_name('build-manifest.json').read_text())
    if sha256(v1.read_bytes())!=meta['wad_sha256']:raise ValueError('Metadata build mismatch')
    lib=load_library();title=lib.title.Title();title.load_wad(v1.read_bytes());original=[title.get_content_by_index(i)for i in range(len(title.tmd.content_records))]
    archive=ChannelArchive(original[10]);path='Channel/Screen/Usa/Layout00.szs';nested=ChannelArchive(decode_yaz0(archive.get(path)))
    message=config['message_file'];old=nested.get(message);new,count=translate_bmg(old,config['messages'])
    # Check every message and original per-message attributes; control bytes are retained.
    before=bmg_sections(old);after=bmg_sections(new)
    bi=next(s for s in before if s[:4]==b'INF1');ai=next(s for s in after if s[:4]==b'INF1');bd=next(s for s in before if s[:4]==b'DAT1');ad=next(s for s in after if s[:4]==b'DAT1')
    stride=int.from_bytes(bi[10:12],'big');total=int.from_bytes(bi[8:10],'big')
    for i in range(total):
        at=16+i*stride;bv=bmg_message(bd,8+int.from_bytes(bi[at:at+4],'big'));av=bmg_message(ad,8+int.from_bytes(ai[at:at+4],'big'))
        assert bi[at+4:at+stride]==ai[at+4:at+stride]
        assert av==(render_bmg_translation(bv,config['messages'][str(i)])if str(i)in config['messages']else bv)
    assert all(a==b for a,b in zip(before,after)if a[:4]not in [b'INF1',b'DAT1'])
    nested=ChannelArchive(nested.replace(message,new));raw=nested.compact();packed=encode_yaz0(raw)
    archive=ChannelArchive(archive.replace(path,packed))
    import struct
    from kwce.channels import layout_sections,rebuild_layout
    cmn='Channel/Screen/Cmn/Layout00.szs';layouts=ChannelArchive(decode_yaz0(archive.get(cmn)));moved=[]
    # Revision 18+: the worldwide-result screen (국가별 그래프) shows the vote count with the Korean
    # unit 「표」 (message 72); its T_LineLCount_00/T_LineRCount_00 panes were left on the Hangul-less
    # number font, so 「표」 did not render. Move them onto the system font exactly as result.brlyt's
    # equivalents already were (the big "%" panes stay on the number font via NUMBER_ONLY).
    layout_targets=['blyt/player.brlyt','blyt/result.brlyt']
    if args.revision>=18:layout_targets.append('blyt/worldResult.brlyt')
    for name in layout_targets:
        sections=layout_sections(layouts.get(name))
        assert any(sec[:4]==b'fnl1'and b'RevoIpl_RodinNTLGPro_DB_32_I4.brfnt'in sec for sec in sections)
        for i,sec in enumerate(sections):
            # Revision 14+: digit/% only boxes keep the number font (the wider system font wrapped "%").
            if sec[:4]==b'txt1'and struct.unpack_from('>H',sec,0x52)[0]==1 and not(args.revision>=14 and sec[12:28].rstrip(b'\0')in NUMBER_ONLY):
                sec=bytearray(sec);struct.pack_into('>H',sec,0x52,0);sections[i]=bytes(sec);moved.append(name+':'+sec[12:28].rstrip(b'\0').decode('ascii'))
        layouts=ChannelArchive(layouts.replace(name,rebuild_layout(layouts.get(name),sections)))
    from kwce.votes_resources import encode_yaz0_lean
    archive=ChannelArchive(archive.replace(cmn,encode_yaz0_lean(layouts.compact())))
    for resource in archive.files:
        payload=archive.get(resource)
        if resource not in(path,cmn)and payload[:4]==b'Yaz0'and int.from_bytes(payload[4:8],'big')<100000:
            unpacked=decode_yaz0(payload);candidate=encode_yaz0(unpacked)
            if len(candidate)<len(payload):archive=ChannelArchive(archive.replace(resource,candidate))
    content=archive.compact()
    if len(content)>len(original[10]):raise ValueError('Original content size exceeded')
    content+=bytes(len(original[10])-len(content));title.set_content(content,10)
    shared,font_record=korean_shared_fonts();fonts=ChannelArchive(shared)
    if set(fonts.files)!=set(ChannelArchive(original[8]).files):raise ValueError('Shared font names differ')
    characters={ord(c)for value in config['messages'].values()for c in value if ord(c)>=32}
    for name in fonts.files:
        raw=fonts.get(name);_,mapping,_=font_data(b'RFNT'+raw[4:])
        if not characters<=mapping.keys():raise ValueError('Translated glyph missing')
    title.set_content(shared,8);extra={}
    if args.revision>=13:
        # Revision 13+: Korean menu tile/banner art, manual font, HOME Menu and manual.
        import hashlib
        from kwce.votes_visual import korean_menu_art
        from kwce.opera_font import korean_opera_font
        from kwce.home_menu import korean_home_menu
        from kwce.channel_manual import localize as localize_manual
        art,art_record=korean_menu_art(original[0]);art=bytearray(art)
        art[0x630:0x640]=bytes(16);art[0x630:0x640]=hashlib.md5(art[0x40:0x640]).digest();title.set_content(bytes(art),0)
        opera,opera_record=korean_opera_font(original[3]);title.set_content(opera,3)
        home,home_record=korean_home_menu(original[4]);title.set_content(home,4)
        manual_config=json.loads((ROOT/'configs/votes-manual-ko.json').read_text(encoding='utf-8'));outer=ChannelArchive(original[9])
        manual,manual_record=localize_manual(outer.get('html_US.arc'),manual_config,base/'work/manual-captures')
        title.set_content(ChannelArchive(outer.replace('html_US.arc',manual)).compact(),9)
        extra=dict(menu_art=art_record,manual_font=opera_record,home_menu=home_record,manual=manual_record)
    if args.revision>=16:
        # Revision 16+: save-data title and software keyboard labels (English slots of the
        # executable's per-language tables; a Korean console uses the English slot) and the
        # English save banner image. Caps/Shift stay as key names.
        from kwce.ppc_patch import utf16_slots
        from kwce.votes_visual import korean_save_banner
        rows=[(0x80238972,'Everybody Votes Channel','모두의 투표 채널'),(0x802550c8,'O.K.','확인'),(0x802550e8,'Quit','그만두기'),
              (0x8025515c,'Dictionary','예측 사전'),(0x80255174,'Language','언어 선택'),(0x802551f4,'Close','닫기'),
              (0x80255258,'More','더 보기'),(0x80255264,'Space','스페이스'),(0x80255270,'Back','뒤로'),(0x803f0498,'OK','확인')]
        executable,exe_rows=utf16_slots(original[1],rows);title.set_content(executable,1)
        c10=ChannelArchive(title.get_content_by_index(10));name='Channel/saveBannerData/voteBannerUS.tpl'
        banner_tpl,_=korean_save_banner(c10.get(name))
        if len(banner_tpl)!=len(c10.get(name)):raise ValueError('Save banner size changed')
        title.set_content(c10.replace(name,banner_tpl),10)
        extra.update(executable_strings=exe_rows,save_banner=name)
    wad=title.dump_wad();check=lib.title.Title();check.load_wad(wad)
    changed=[i for i in range(len(original))if check.get_content_by_index(i)!=original[i]]
    assert changed==([0,1,3,4,8,9,10]if args.revision>=16 else[0,3,4,8,9,10]if args.revision>=13 else[8,10]),changed
    out.mkdir(parents=True);(out/'votes-ko-ui-test.wad').write_bytes(wad)
    result=dict(revision=args.revision,number_font_boxes_moved_to_system_font=moved,title_id=title.tmd.title_id,wad_sha256=sha256(wad),translated_messages=count,total_messages=total,unchanged_message_bytes_verified=total-count,message_attributes_preserved=True,other_sections_preserved=True,changed_contents_from_v1=changed,content_10_original_size_preserved=len(content)==len(original[10]),hangul_font_ready=True,font_record=font_record,translated_character_coverage_verified=True,runtime_verified=False,installed=False,**extra)
    (out/'build-manifest.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    if expected is not None:
        if((out/'votes-ko-ui-test.wad').read_bytes(),(out/'build-manifest.json').read_bytes())!=expected:raise ValueError('Votes UI reproduction differs')
        print(f'Reproduced byte-identically: build-v{args.revision} (WAD + manifest) in {out}')
if __name__=='__main__':main()

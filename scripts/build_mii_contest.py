"""Mii Contest Korean build. Revision 8+ adds the console's Korean HOME Menu
(HomeButton3) and the Korean manual-browser font. Revision 9+ also localizes
the manual's common buttons, callout labels and badges
(configs/mii-contest-manual-images-ko.json). The v7 builder is kept in
workspace/channels/mii-contest/build_mii_contest_v7_snapshot.py."""
import argparse,hashlib,json,re,sys,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,ChannelArchive,sha256
from kwce.votes_resources import decode_yaz0,encode_yaz0,encode_yaz0_greedy,translate_bmg,bmg_sections,bmg_message,render_bmg_translation
from kwce.channel_korean_font import korean_shared_fonts
from kwce.channel_font import extend_font

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True);ap.add_argument('--reproduce',action='store_true');args=ap.parse_args()
    if not 8<=args.revision<=100:raise SystemExit('Revision bounds')
    base=ROOT/'workspace/channels/mii-contest';out=base/f'build-v{args.revision}';expected=None
    if args.reproduce:
        # --reproduce rebuilds into workspace/private/mii-contest-reproduce-vN-M and requires the
        # WAD and the manifest to be byte-identical to the preserved build-vN.
        expected=((out/'mii-contest-ko-ui-test.wad').read_bytes(),(out/'build-manifest.json').read_bytes());n=1
        while(ROOT/f'workspace/private/mii-contest-reproduce-v{args.revision}-{n}').exists():n+=1
        out=ROOT/f'workspace/private/mii-contest-reproduce-v{args.revision}-{n}'
    if out.exists():raise SystemExit('Existing Mii Contest build preserved')
    draft=json.loads((base/'draft/messages-ko.json').read_text(encoding='utf-8'));review=json.loads((ROOT/'configs/mii-contest-reviewed-ko.json').read_text(encoding='utf-8'));mapping=draft['messages'];mapping.update(review['reviewed_messages'])
    if args.revision>=10:mapping={k:v.replace('컨테스트','콘테스트')for k,v in mapping.items()}
    source=base/'originals/mii-contest-usa-wiilink-archive.wad'
    if sha256(source.read_bytes())!=draft['source_sha256']:raise ValueError('Source differs')
    lib=load_library();title=lib.title.Title();title.load_wad(source.read_bytes());original=[title.get_content_by_index(i)for i in range(len(title.tmd.content_records))]
    archive=ChannelArchive(original[4]);path='content4/Message/Bmg/Basic_US.szs';old=decode_yaz0(archive.get(path));new,count=translate_bmg(old,mapping)
    before=bmg_sections(old);after=bmg_sections(new);bi=next(s for s in before if s[:4]==b'INF1');ai=next(s for s in after if s[:4]==b'INF1');bd=next(s for s in before if s[:4]==b'DAT1');ad=next(s for s in after if s[:4]==b'DAT1');stride=int.from_bytes(bi[10:12],'big');total=int.from_bytes(bi[8:10],'big');changed=0
    for i in range(total):
        at=16+i*stride;bv=bmg_message(bd,8+int.from_bytes(bi[at:at+4],'big'));av=bmg_message(ad,8+int.from_bytes(ai[at:at+4],'big'))
        if av!=render_bmg_translation(bv,mapping[str(i)]):raise ValueError('Message verification')
        if bi[at+4:at+stride]!=ai[at+4:at+stride]:raise ValueError('Message attributes differ')
        if re.findall(r'\{CTRL\d+\}',mapping[str(i)])!=['{CTRL'+str(j)+'}'for j in range(len(re.findall(r'\{CTRL\d+\}',mapping[str(i)])))]:raise ValueError('Control token order differs')
        changed+=av!=bv
    bmg_width=None
    if args.revision==24:
        # Revision 24 only: message INF1 attribute +4 is the glyph horizontal scale in percent
        # (the program sets font width = value*0.01*FINF width, ignoring the layout width).
        # wbf1 Hangul is drawn wide, so narrow every message (the ticker ignores it; see v25).
        new=bytearray(new);ii=new.find(b'INF1');scaled=0
        for i in range(total):
            at=ii+16+i*stride;value=int.from_bytes(new[at+4:at+6],'big')
            if not 0<value<=200:continue
            new[at+4:at+6]=round(value*.92).to_bytes(2,'big');scaled+=1
        new=bytes(new);bmg_width=dict(factor=.92,scaled_messages=scaled)
    if args.revision>=28:
        # Revision 28+: '#' message boxes take the INF1 width attribute; the US table condenses
        # long English lines (e.g. message 923 at 70%), which squashed the much shorter Korean
        # lines on hardware (2026-10-29). Raise each <100% width to the English-fitted width.
        from kwce.mii_contest_width import widen
        from kwce.food_textfit import Metrics
        en_font=Metrics(ChannelArchive(original[5]).get('wbf1.brfna'))
        ko_font=Metrics(ChannelArchive(korean_shared_fonts()[0]).get('wbf1.brfna'))
        new,bmg_width=widen(new,old,en_font,ko_font)
    packed=encode_yaz0(new);archive=ChannelArchive(archive.replace(path,packed))
    from kwce.mii_contest_layout import localize_layouts
    archive,layout_record=localize_layouts(archive,json.loads((ROOT/'configs/mii-contest-layout-ko.json').read_text(encoding='utf-8'))['labels'],ROOT/'workspace/channels/forecast/references/NotoSansKR.ttf')
    if args.revision>=20:
        # Revision 20+: wbf1 Hangul looked squat in system-font boxes (not a 4:3 effect).
        from kwce.mii_contest_layout import upright_system_text
        # Revision 22+: the top-menu ticker still measured 1.02-1.08 wide; it is one line in a
        # 38-high box and its pane width follows the text, so it takes a stronger correction.
        ticker={('topMenuText_00.brlyt','T_title_0'):(.95,1.04),('topMenuText_00.brlyt','T_setsumei_0'):(.95,1.04)}if args.revision==22 else({('topMenuText_00.brlyt','T_title_0'):(.75,1.04),('topMenuText_00.brlyt','T_setsumei_0'):(.75,1.04)}if args.revision==23 else None)  # v23: width experiment (no effect)
        archive,layout_record['upright_system_text']=upright_system_text(archive,extra=ticker)
    from kwce.mii_contest_manual import localize_manual
    manual_images=json.loads((ROOT/'configs/mii-contest-manual-images-ko.json').read_text(encoding='utf-8'))['images']if args.revision>=9 else None
    archive,manual_record=localize_manual(archive,json.loads((ROOT/'configs/mii-contest-manual-ko.json').read_text(encoding='utf-8')),manual_images,base/'work/manual-captures')
    # This Korean-only alpha maps all language aliases to the same reviewed/draft English-derived table.
    for other in list(archive.files):
        if other!=path and '/Message/Bmg/'in other:archive=ChannelArchive(archive.replace(other,packed))
    font_path='content4/Message/Font/Miicontest_RodinNTLGPro_M_32_IA4.szs'
    font_raw=decode_yaz0(archive.get(font_path));font_new,button_font=extend_font(font_raw,''.join(mapping.values()),ROOT/'workspace/channels/forecast/references/NotoSansKR.ttf')
    archive=ChannelArchive(archive.replace(font_path,encode_yaz0_greedy(font_new)))
    # Korean HOME Menu: Mii uses HomeButton3 (byte-identical to the US shared copy).
    from libWiiPy.archive import decompress_lz77
    from kwce.home_menu import KOREAN_SHARED
    korean_home=decompress_lz77(ChannelArchive(KOREAN_SHARED.read_bytes()).get('Homebutton3/LZ77_homeBtn_KOR.arc'))
    home_packed=encode_yaz0_greedy(korean_home);home_files=[]
    for lang in['ENG','FRA','GER','ITA','NED','SPA']:
        name=f'content4/Basic/HBM/homeBtn_{lang}.szs'
        if name in archive.files:archive=ChannelArchive(archive.replace(name,home_packed));home_files.append(name)
    start=int.from_bytes(archive.data[12:16],'big');dedup=bytearray(archive.data[:start]);stored={}
    for name in archive.files:
        payload=archive.get(name);digest=sha256(payload)
        if digest not in stored:
            dedup.extend(bytes(-len(dedup)%32));stored[digest]=len(dedup);dedup.extend(payload)
        struct.pack_into('>II',dedup,archive.nodes[name]+4,stored[digest],len(payload))
    content=bytes(dedup);checked_archive=ChannelArchive(content)
    assert all(checked_archive.get(name)==archive.get(name)for name in archive.files)
    if len(content)>len(original[4]):raise ValueError('Original content capacity exceeded: '+str(len(content))+' > '+str(len(original[4])))
    content+=bytes(len(original[4])-len(content));title.set_content(content,4)
    shared,font_record=korean_shared_fonts()
    if args.revision>=25:
        # Revision 25+: the channel draws system-font text at the font's own aspect
        # (layout width and message width are not used everywhere, e.g. the top ticker),
        # so narrow the Hangul glyphs of this channel's own wbf1/wbf2 copy to 0.9.
        from kwce.korean_font_narrow import narrow_hangul
        fonts=ChannelArchive(shared);font_record['narrowed']=[]
        for name in sorted(fonts.files):
            narrowed,stats=narrow_hangul(fonts.get(name),.9);fonts=ChannelArchive(fonts.replace(name,narrowed));font_record['narrowed'].append(dict(font=name,sha256=sha256(narrowed),**stats))
        shared=fonts.data
        if args.revision>=28:
            from kwce.food_textfit import Metrics
            from kwce.mii_contest_width import HANGUL_NARROWED_ADVANCE
            if Metrics(ChannelArchive(shared).get('wbf1.brfna')).advance('가')!=HANGUL_NARROWED_ADVANCE:raise ValueError('Narrowed Hangul advance differs from the width model')
    title.set_content(shared,5)
    from kwce.opera_font import korean_opera_font
    opera,opera_record=korean_opera_font(original[3]);title.set_content(opera,3)
    from kwce.mii_contest_visual import korean_menu_art
    visual,menu_art=korean_menu_art(original[0],ROOT/'workspace/channels/forecast/references/NotoSansKR.ttf',title_style=args.revision)
    banner=bytearray(visual);assert banner[0x80:0x84]==b'IMET'
    for language in range(10):
        at=0x40+0x5c+84*language;name='Mii 콘테스트 채널'.encode('utf-16-be');banner[at:at+84]=name+bytes(84-len(name))
    banner[0x630:0x640]=bytes(16);banner[0x630:0x640]=hashlib.md5(banner[0x40:0x640]).digest();title.set_content(bytes(banner),0);title.tmd.region=4
    keyboard=[]
    if args.revision>=19:
        # Revision 19+: software keyboard labels in the English slots of the executable's
        # per-language tables (a Korean console uses the English slot). Caps/Shift stay.
        from kwce.ppc_patch import utf16_slots
        rows=[(0x8033e8d0,'Quit','그만두기'),(0x8033e944,'Dictionary','예측 사전'),(0x8033e95c,'Language','언어 선택'),
              (0x8033e9dc,'Close','닫기'),(0x8033ea40,'More','더 보기'),(0x8033ea4c,'Space','스페이스'),
              (0x8033ea58,'Back','뒤로'),(0x8042be88,'OK','확인')]
        executable,keyboard=utf16_slots(original[1],rows);title.set_content(executable,1)
    specialty_runtime=None
    if args.revision==27:
        # Revision 27 only (abandoned 2026-10-28 by user decision; kept so build-v27 regenerates):
        # the same by-code fail-safe specialty translation, written into an in-place
        # code cave inside text0 (the empty MetroTRK vector slots 0x1800..0x1B00, 0x80005988..
        # 0x80005d88) and comparing/writing the skill slots as UTF-16BE (their real encoding).
        # No DOL section is added: header, section table, bss and length equal revision 25's.
        from kwce.mii_contest_runtime import build_specialty_dict,patch_specialty_cave
        patched,specialty_runtime=patch_specialty_cave(title.get_content_by_index(1),build_specialty_dict(ROOT));title.set_content(patched,1)
    elif args.revision in (26,28):
        # Revision 26 (and 28, which picked this branch by mistake on 2026-10-29 and is ABANDONED --
        # never install or ship build-v28) kept so their builds regenerate. It panics at boot in Dolphin; its new
        # section above bss lies inside the boot stack (0x80430728..0x80440728). In-channel runtime
        # Korean translation of the server-supplied specialty vocabulary (fixed codes 1..19): a stub
        # on the AdditionParse call site rewrites each supplied skill name whose English still
        # matches the expected value; empty/unknown/mismatched slots and all dynamic data (contest
        # titles, Mii/artisan names) are left as supplied. See kwce/mii_contest_runtime.py.
        from kwce.mii_contest_runtime import build_specialty_dict,patch_specialty_runtime
        patched,specialty_runtime=patch_specialty_runtime(title.get_content_by_index(1),build_specialty_dict(ROOT));title.set_content(patched,1)
    wad=title.dump_wad();check=lib.title.Title();check.load_wad(wad)
    contents=[i for i in range(len(original))if check.get_content_by_index(i)!=original[i]];assert contents==([0,1,3,4,5]if args.revision>=19 else[0,3,4,5])
    out.mkdir(parents=True);(out/'mii-contest-ko-ui-test.wad').write_bytes(wad)
    result=dict(revision=args.revision,bmg_horizontal_scale=bmg_width,keyboard_strings=keyboard,home_menu=dict(files=home_files,source='console shared1 0x17 Homebutton3 KOR'),manual_font=opera_record,title_id=title.tmd.title_id,wad_sha256=sha256(wad),source_sha256=draft['source_sha256'],message_slots=total,changed_message_slots=changed,source_reviewed_slots=len(review['reviewed_messages']),changed_contents=contents,original_content_size_preserved=True,font_record=font_record,button_font=button_font,menu_art=menu_art,language_table_aliases_korean_only=True,quality='message-reviewed-local-alpha',manual=manual_record,layouts=layout_record,message_source_review_complete=True,review_complete=False,full_localization_complete=False,runtime_verified=False,specialty_runtime=specialty_runtime)
    if args.revision<26:result.pop('specialty_runtime')  # key added with r26; older manifests regenerate without it
    (out/'build-manifest.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    if expected is not None:
        if((out/'mii-contest-ko-ui-test.wad').read_bytes(),(out/'build-manifest.json').read_bytes())!=expected:raise ValueError('Mii Contest reproduction differs')
        print(f'Reproduced byte-identically: build-v{args.revision} (WAD + manifest) in {out}')
if __name__=='__main__':main()

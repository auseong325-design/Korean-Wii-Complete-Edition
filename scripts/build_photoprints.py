"""Korean Photo Prints Channel — local emulator build (create-once build-vN).

Both local and hardware builds start from the WiiLink Digicam_1_Japan service
patch on stock content 1 (forces Japanese language/personal-data/title-ID and
re-points the Fujifilm endpoints to WiiLink). This LOCAL build then redirects
those endpoints to http://127.0.0.2 so nothing leaves the emulator, applies the
Korean DOL literals, the title-local Korean-area bridge, Korean BRLYT text with
Hangul appended to the channel font, the Korean HOME Menu and the Korean banner
name. Reproducible byte-for-byte via --reproduce.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,ChannelArchive,layout_sections,textbox,replace_textbox,fit_korean_textbox,rebuild_layout,sha256
from kwce.wiiroom_formats import decompress_lz11,reencode_lz11_same_size
from kwce import bspatch
from kwce.photoprints_strings import translate_executable,rewrite_local_endpoints
from kwce.photoprints_compat import patch_korean_area
from kwce.photoprints_font import append_hangul
from kwce.photoprints_banner import korean_banner_name,DISPLAY_NAME
from kwce.home_menu import korean_home_menu,KOREAN_SHARED,SOURCES

TITLE='000100014843444a';BOOT=12
LZARCHIVES=['layout.arc.LZ','cursor.arc.LZ','Keyboard/sofkeybd.lz']
CACHE=ROOT/'workspace/private/photoprints-lzcache'


def _lz_recompress(raw_original,edited):
    """Return a raw 0x10 LZ stream for `edited`, cached by content hash."""
    load_library();from libWiiPy.archive import compress_lz77,decompress_lz77
    key=sha256(edited);CACHE.mkdir(parents=True,exist_ok=True);cached=CACHE/f'{key}.lz'
    if cached.exists():
        data=cached.read_bytes()
        if decompress_lz77(data)==edited:return data
    comp=compress_lz77(edited,1)
    if comp[:4]==b'LZ77':comp=comp[4:]           # keep the raw 0x10 stream the game expects
    if decompress_lz77(comp)!=edited:raise ValueError('LZ recompression roundtrip failed')
    cached.write_bytes(comp);return comp


def translate_brlyt_archive(data,messages):
    """Translate every matching txt1 textbox in one decompressed U8 archive."""
    archive=ChannelArchive(data);changed=0
    for name in list(archive.files):
        if not name.endswith('.brlyt'):continue
        sections=layout_sections(archive.get(name));touched=False
        for i,sec in enumerate(sections):
            tb=textbox(sec)
            if tb is None:continue
            ko=messages.get(tb[1])
            if ko is None:continue
            new=replace_textbox(sec,ko);new=fit_korean_textbox(new,ko)
            sections[i]=new;touched=True;changed+=1
        if touched:archive=ChannelArchive(archive.replace(name,rebuild_layout(archive.get(name),sections)))
    return archive.data,changed


def hangul_used(messages,exec_rows):
    s=set(DISPLAY_NAME)
    for v in messages.values():s|=set(v)
    for r in exec_rows:s|=set(r['ko'])
    return {c for c in s if 0xac00<=ord(c)<=0xd7a3 or 0x3130<=ord(c)<=0x318f}


def build(original_wad,local,revision):
    lib=load_library();title=lib.title.Title();title.load_wad(original_wad)
    if title.tmd.title_id!=TITLE or title.tmd.boot_index!=BOOT:raise ValueError('Photo Prints source identity differs')
    contents=[title.get_content_by_index(i) for i in range(len(title.tmd.content_records))]
    # v8+: text re-broken/shortened to fit each pane (scripts/fit_photoprints_messages.py);
    # v10: + price label without the server's priceUnit suffix.
    table='photoprints-messages-v10-ko.json' if revision>=10 else 'photoprints-messages-v8-ko.json' if revision>=8 else 'photoprints-messages-v1-ko.json'
    messages=json.loads((ROOT/'configs'/table).read_text(encoding='utf-8'))['messages']
    exec_cfg=json.loads((ROOT/'configs/photoprints-executable-v1-ko.json').read_text(encoding='utf-8'))
    record={}

    # content 1 — WiiLink service patch, then Korean literals + area bridge (+ local endpoints)
    patch=(ROOT/'workspace/channels/photoprints/references/wiilink-patcher/bsdiff__digicam__Digicam_1_Japan.bsdiff').read_bytes()
    wl_c1=bspatch.apply(contents[1],patch)
    dol=decompress_lz11(wl_c1)
    from kwce.photoprints_strings import ERROR_FONT_LITERALS
    dol,exec_rec=translate_executable(dol,skip=ERROR_FONT_LITERALS if revision>=6 else ())
    dol,area_rec=patch_korean_area(dol)
    if local:dol,ep_rec=rewrite_local_endpoints(dol);record['local_endpoints']=ep_rec
    new_c1=reencode_lz11_same_size(wl_c1,dol)
    title.set_content(new_c1,1);record['executable']=exec_rec;record['korean_area']=area_rec

    # content 2 — BRLYT Korean + Hangul font (+ Korean product-name textures at rev>=2)
    c2=ChannelArchive(contents[2]);arch_counts={}
    from libWiiPy.archive import decompress_lz77
    if revision>=8:
        # v8/v9: build the GLGR-preserving font first, then fit every pane with
        # its real advances (v8 = UI syllables, v9 = + KS X 1001 2,350).
        from kwce.photoprints_font import append_hangul_rfna
        from kwce import photoprints_textfit as tf
        chars=set(hangul_used(messages,exec_cfg['rows']))
        if revision>=9:chars|={chr(c) for c in range(0xAC00,0xD7A4) if len(chr(c).encode('euc_kr'))==2}
        rodan=c2.get('font_rodan_28.brfna')
        # v10: glyphs placed in nw4r's real cell window (v6-v9 clipped the right
        # edge of every glyph whose system left bearing is 2: 디 터 만 니 ...).
        font,font_rec=append_hangul_rfna(rodan,''.join(sorted(chars)),exact=revision>=10)
        font_rec['coverage']='ui_plus_ksx1001_2350' if revision>=9 else 'ui_subset'
        if revision>=10:
            from kwce.photoprints_font import glyph_ink_report
            first=font_rec['first_appended_glyph'];ink=glyph_ink_report(font,range(first,first+font_rec['added_glyphs']))
            if not ink['ok']:raise ValueError(f"Appended glyph ink check failed: {dict((k,len(v)) for k,v in ink.items() if isinstance(v,list))}")
            font_rec['ink_check']=dict(glyphs=ink['checked'],clipped=0,empty=0,overlap=0,window='[1,1+glyphWidth) x [1,1+cellHeight)')
        metrics,jp_metrics=tf.Metrics(font),tf.Metrics(rodan);fit={}
        for name in LZARCHIVES:
            edited,n,fit[name]=tf.translate_fitted(decompress_lz77(c2.get(name)),messages,metrics,jp_metrics)
            arch_counts[name]=n;recompress=n>0
            if name=='layout.arc.LZ':
                from kwce.photoprints_textures import redraw_product_names
                edited,tex_rec=redraw_product_names(edited,exact=revision>=10);record['textures']=tex_rec;recompress=True
            if recompress:c2=ChannelArchive(c2.replace(name,_lz_recompress(c2.get(name),ChannelArchive(edited).compact())))
        c2=ChannelArchive(c2.replace('font_rodan_28.brfna',font))
        title.set_content(c2.compact(),2);record['brlyt']=arch_counts;record['font']=font_rec
        record['text_fit']=dict(table=table,metric='nw4r TextWriter advances, 1-unit margin',min_scale_allowed=tf.MIN_SCALE,
            squeezed_panes=sum(v['squeezed_panes'] for v in fit.values()),min_scale=min(v['min_scale'] for v in fit.values()),
            line_budget='Japanese explicit lines (wrapped lines where the Japanese relied on wrapping)',debug_layouts_unfitted=list(tf.DEBUG_LAYOUTS))
        lzlist=[]
    else:
        lzlist=LZARCHIVES
    for name in lzlist:
        edited,n=translate_brlyt_archive(decompress_lz77(c2.get(name)),messages)
        arch_counts[name]=n;recompress=n>0
        if name=='layout.arc.LZ' and revision>=2:
            from kwce.photoprints_textures import redraw_product_names
            edited,tex_rec=redraw_product_names(edited);record['textures']=tex_rec;recompress=True
        if recompress and revision>=6:edited=ChannelArchive(edited).compact()  # drop replaced-file dead space (~0.9 MB)
        if recompress:c2=ChannelArchive(c2.replace(name,_lz_recompress(c2.get(name),edited)))
    if revision>=8:pass
    elif revision>=6:
        # syllables only; v7 adds the 2,350 KS X 1001 syllables for pd.dat names.
        from kwce.photoprints_font import append_hangul_rfna
        chars=set(hangul_used(messages,exec_cfg['rows']))
        if revision>=7:chars|={chr(c) for c in range(0xAC00,0xD7A4) if len(chr(c).encode('euc_kr'))==2}
        font,font_rec=append_hangul_rfna(c2.get('font_rodan_28.brfna'),''.join(sorted(chars)))
        font_rec['coverage']='ui_plus_ksx1001_2350' if revision>=7 else 'ui_subset'
        c2=ChannelArchive(c2.replace('font_rodan_28.brfna',font))
        title.set_content(c2.compact(),2);record['brlyt']=arch_counts;record['font']=font_rec
    else:
        # v1-v3 (kept reproducible): this append drops GLGR -> ArchiveFont fails -> boot crash 0x801bdf40.
        if revision>=3:
            font_chars=''.join(chr(c) for c in range(0xAC00,0xD7A4))
        else:
            font_chars=''.join(sorted(hangul_used(messages,exec_cfg['rows'])))
        font,font_rec=append_hangul(c2.get('font_rodan_28.brfna'),font_chars)
        font_rec['coverage']='full_hangul_11172' if revision>=3 else 'ui_subset'
        c2=ChannelArchive(c2.replace('font_rodan_28.brfna',font))
        title.set_content(c2.compact(),2);record['brlyt']=arch_counts;record['font']=font_rec

    # content 3 — Korean HOME Menu
    home,home_rec=korean_home_menu(contents[3],fix_dialogs=True,all_dialog_languages=True)
    home=ChannelArchive(home);korean=ChannelArchive(KOREAN_SHARED.read_bytes())
    for folder,path in SOURCES.items():
        base=folder+'/LZ77_homeBtn.arc'
        if base in home.files:home=ChannelArchive(home.replace(base,korean.get(path)))
    title.set_content(home.compact(),3);record['korean_home']=home_rec

    # content 0 — Korean banner name
    banner,banner_rec=korean_banner_name(contents[0])
    title.set_content(banner,0);record['banner']=banner_rec

    wad=title.dump_wad();check=lib.title.Title();check.load_wad(wad)
    changed=[i for i in range(len(contents)) if check.get_content_by_index(i)!=contents[i]]
    if changed!=[0,1,2,3]:raise ValueError(f'Unexpected Photo Prints content change: {changed}')
    record.update(revision=revision,title_id=TITLE,boot_index=BOOT,wad_sha256=hashlib.sha256(wad).hexdigest(),
        changed_contents=changed,local_only=bool(local),
        translated_brlyt=sum(arch_counts.values()),
        full_localization_complete=False,hardware_success_verified=False)
    return wad,record


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,default=10,choices=[1,2,3,6,7,8,9,10]);ap.add_argument('--reproduce',action='store_true');args=ap.parse_args()
    base=ROOT/'workspace/channels/photoprints';out=base/f'build-v{args.revision}';expected=None
    original=(base/'originals/digicam-japan-v1024.wad').read_bytes()
    if args.reproduce:
        expected=(out/'photoprints-ko-local-test.wad').read_bytes();n=1
        while(ROOT/f'workspace/private/photoprints-reproduce-v{args.revision}-{n}').exists():n+=1
        out=ROOT/f'workspace/private/photoprints-reproduce-v{args.revision}-{n}'
    if out.exists():raise SystemExit('Existing Photo Prints build preserved')
    wad,record=build(original,local=True,revision=args.revision)
    out.mkdir(parents=True);(out/'photoprints-ko-local-test.wad').write_bytes(wad)
    (out/'build-manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    if expected is not None and expected!=wad:raise ValueError('Photo Prints reproduction differs')
    print(('Reproduced byte-identically' if expected is not None else 'Built'),'Photo Prints v%d'%args.revision,
          ': BRLYT',record['translated_brlyt'],'DOL',record['executable']['applied'],'font+',record['font']['added_glyphs'],
          'endpoints',record.get('local_endpoints',{}).get('local_endpoints'),'sha',record['wad_sha256'][:12])
if __name__=='__main__':main()

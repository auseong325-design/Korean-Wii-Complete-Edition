"""Build an emulator-only Korean prototype from preserved local WAD copies."""
import argparse,hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import ChannelArchive,load_library,layout_sections,textbox,replace_textbox,fit_korean_textbox,rebuild_layout,sha256,compress_lz10,patch_utf16_literals
from kwce.channel_font import extend_font
from kwce.forecast_visual import layout_metrics,bitmap_captions,korean_banner_groups

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,default=1);ap.add_argument('--reproduce',action='store_true',help='rebuild to a fresh private folder and compare with the preserved WAD');ap.add_argument('--diagnostic-skip',choices=['time','home','clock','observation','periods'],help='bisect builds only');args=ap.parse_args()
    if not 1<=args.revision<=1000:raise SystemExit('Revision bounds')
    out=ROOT/f'workspace/channels/forecast/build-v{args.revision}'
    expected_wad=None
    if args.reproduce:
        expected_wad=(out/'forecast-ko-personal-test.wad').read_bytes();number=1
        while(ROOT/f'workspace/private/forecast-reproduce-v{args.revision}-{number}').exists():number+=1
        out=ROOT/f'workspace/private/forecast-reproduce-v{args.revision}-{number}'
    if out.exists():raise SystemExit('Existing channel build preserved')
    lib=load_library();from libWiiPy.archive import decompress_lz77
    source=ROOT/'workspace/channels/forecast/originals/forecast-usa-wiilink-archive.wad'
    acquisition=json.loads((source.parent/'acquisition.json').read_text());row=next(r for r in acquisition['files']if r['alias']==source.name)
    if sha256(source.read_bytes())!=row['sha256']:raise ValueError('Original WAD changed')
    title=lib.title.Title();title.load_wad(source.read_bytes())
    if title.tmd.title_id!='0001000248414645'or title.tmd.title_version!=7 or len(title.tmd.content_records)!=12:raise ValueError('Wrong Forecast source')
    # Hash verification is enabled; no title keys or ticket data are logged.
    originals=[title.get_content_by_index(i)for i in range(12)]
    config_path=ROOT/('configs/forecast-ko-v30.json'if args.revision<=60 and(ROOT/'configs/forecast-ko-v30.json').exists()else'configs/forecast-ko.json')
    config=json.loads(config_path.read_text(encoding='utf-8'))
    content=ChannelArchive(originals[9]);layout=ChannelArchive(decompress_lz77(content.get('weather_layout.arc.LZ')))
    mapping=config['labels'];pane_map=config['panes'];translated=[];remaining=[];texts=[]
    for name in list(layout.files):
        if not name.endswith('.brlyt'):continue
        data=layout.get(name);sections=layout_sections(data);stem=Path(name).stem;changes=0
        for i,section in enumerate(sections):
            entry=textbox(section)
            if entry is None:continue
            pane,text=entry
            key=stem+'/'+re.sub(r'(JP|US|GE|FR|SP|IT|DU)','',pane)
            replacement=pane_map.get(key)or mapping.get(text)or mapping.get(' '.join(text.split()))
            if replacement:
                sections[i]=layout_metrics(stem,pane,fit_korean_textbox(replace_textbox(section,replacement),replacement));texts.append(replacement);changes+=1
                translated.append(dict(layout=stem,pane=pane,source_sha256=sha256(text.encode('utf-16-be')),target=replacement))
            elif 'US'in pane and text and key not in config.get('preserved_panes',{}):remaining.append(dict(layout=stem,pane=pane,characters=len(text),source_sha256=sha256(text.encode('utf-16-be'))))
        if changes:layout=ChannelArchive(layout.replace(name,rebuild_layout(data,sections)))
    font=ROOT/'workspace/channels/forecast/references/NotoSansKR.ttf';font_records=[]
    dynamic=json.loads((ROOT/'configs/forecast-dynamic-ko.json').read_text(encoding='utf-8'))
    places=json.loads((ROOT/'configs/forecast-places-ko.json').read_text(encoding='utf-8'))['strings']
    characters=''.join(texts)+''.join(config['literals'].values())+''.join(dynamic['strings'].values())+''.join(dynamic['weekdays'].values())+'날씨 채널서울대한민국오류 코드오전오후기준'
    if args.revision>=98:characters+='북동남서무풍'
    # Only fonts that draw location names get the international place glyphs;
    # the clock/temperature fonts stay near their v12 size to bound memory use.
    place_fonts={'arc/font/font_weather.brfnt','font_weather_city.brfnt.LZ'}
    with_places=characters+''.join(places.values())
    for name in [n for n in layout.files if n.endswith('.brfnt')]:
        modified,record=extend_font(layout.get(name),with_places if name in place_fonts else characters,font);font_records.append(dict(file=name,**record));layout=ChannelArchive(layout.replace(name,modified))
    # LZ10 roundtrip avoids changing Nintendo's decompressor.
    data=layout.compact()
    if len(data)>0xffffff:raise ValueError('LZ10 size limit')
    packed=compress_lz10(data)
    if decompress_lz77(packed)!=data:raise ValueError('Compression roundtrip failed')
    content=ChannelArchive(content.replace('weather_layout.arc.LZ',packed))
    common,weather,bitmap_record=bitmap_captions(decompress_lz77(content.get('TPLCommon.tpl.LZ')),decompress_lz77(content.get('TPLWeather.tpl.LZ')),font)
    for name,data in [('TPLCommon.tpl.LZ',common),('TPLWeather.tpl.LZ',weather)]:
        packed=compress_lz10(data)
        if decompress_lz77(packed)!=data:raise ValueError('Caption texture compression roundtrip')
        content=ChannelArchive(content.replace(name,packed))
    for name in ['font_weather_city.brfnt.LZ','font_weather_time.brfnt.LZ','font_weather_timeWW.brfnt.LZ']:
        data=decompress_lz77(content.get(name));modified,record=extend_font(data,with_places if name in place_fonts else characters,font)
        packed=compress_lz10(modified)
        if decompress_lz77(packed)!=modified:raise ValueError('Font LZ10 roundtrip')
        font_records.append(dict(file=name,**record));content=ChannelArchive(content.replace(name,packed))
    runtime_home_record=None
    if args.revision>=101:
        from kwce.home_menu import korean_runtime_home_messages
        content,runtime_home_record=korean_runtime_home_messages(content)
    title.set_content(content.compact(),9)
    from kwce.channel_manual import localize as localize_manual
    manual_config=json.loads((ROOT/'configs/forecast-manual-ko.json').read_text(encoding='utf-8'))
    manual_outer=ChannelArchive(originals[10]);manual_arc,manual_record=localize_manual(manual_outer.get('html-us.arc'),manual_config,ROOT/'workspace/channels/forecast/work/manual-captures')
    capture_names=sorted({s['capture']for image in manual_config.get('images',{}).values()for s in image.get('shots',[])})
    manual_record['captures']=[dict(file=name,sha256=sha256((ROOT/'workspace/channels/forecast/work/manual-captures'/name).read_bytes()))for name in capture_names]
    title.set_content(ChannelArchive(manual_outer.replace('html-us.arc',manual_arc)).compact(),10)
    from kwce.opera_font import korean_opera_font
    opera_font,opera_record=korean_opera_font(originals[3]);title.set_content(opera_font,3)
    from kwce.home_menu import korean_home_menu
    if args.diagnostic_skip!='home':
        home,home_record=korean_home_menu(originals[6],fix_dialogs=args.revision>=99,all_dialog_languages=args.revision>=100);title.set_content(home,6)
    else:home_record=None
    from kwce.channel_korean_font import korean_shared_fonts
    common_fonts,korean_font_record=korean_shared_fonts();title.set_content(common_fonts,7)
    executable=bytearray(originals[1]);needle='Error Code:'.encode('utf-16-be')
    at=executable.find(needle)
    if at<0 or executable.find(needle,at+2)>=0:raise ValueError('Error code label not unique')
    end=at
    while end+2<=len(executable)and executable[end:end+2]!=b'\0\0':end+=2
    original_label=bytes(executable[at:end]).decode('utf-16-be')
    new_label=('오류 코드:'+original_label[len('Error Code:'):]).encode('utf-16-be')
    if len(new_label)>end-at:raise ValueError('Error label overflow')
    executable[at:end]=new_label+bytes(end-at-len(new_label))
    executable,literal_count=patch_utf16_literals(executable,config['literals'])
    from kwce.forecast_time import korean_time
    executable,time_record=(executable,None)if args.diagnostic_skip=='time'else korean_time(executable,tuple(x for x in('observation','periods','clock')if x!=args.diagnostic_skip),clock_language_fallback=27<=args.revision<=28 and args.diagnostic_skip!='clock',clock_font_fallback=args.revision==28 and args.diagnostic_skip!='clock',clock_region_enabled=args.revision==29 and args.diagnostic_skip!='clock',clock_display_enabled=30<=args.revision<=61 and args.diagnostic_skip!='clock',clock_main_views_only=args.revision==84 and args.diagnostic_skip!='clock',clock_active_view_only=args.revision>=85 and args.diagnostic_skip!='clock')
    wind_record=None
    if args.revision>=98:
        from kwce.forecast_wind import korean_wind
        executable,wind_record=korean_wind(executable)
    supply_record=None
    if args.revision>=104:
        # Convert WiiLink supply strings (conditions, UV, place/country names) inside the channel:
        # a guarded hook runs localize_forecast's rules on the verified+decompressed download buffer.
        from kwce.forecast_supply import patch_executable as patch_supply
        from kwce.forecast_data import forecast_mapping as supply_mapping
        executable,supply_record=patch_supply(bytes(executable),supply_mapping())
    title.set_content(executable,1)
    # Translate the menu tile/banner while preserving original animation tracks.
    # BRLYT font size is normalized by FINF width/height, not square units.
    # The verified 43K wbf1 font uses width24/height28; retain v102 for replay.
    icon_font_ratio=1.0
    if args.revision>=103:
        from kwce.channel_font import font_data
        shared_font=ChannelArchive(common_fonts).get('wbf1.brfna')
        finf=font_data(b'RFNT'+shared_font[4:])[0][b'FINF'][1]
        if (finf[29],finf[28])!=(24,28):raise ValueError('Icon font normalization changed')
        icon_font_ratio=finf[29]/finf[28]
    banner_data,banner_groups=korean_banner_groups(originals[0],translate=True,font_path=font,natural_icon_title=args.revision>=102,icon_font_ratio=icon_font_ratio);banner=bytearray(banner_data);base=0x40
    if banner[base+0x40:base+0x44]!=b'IMET':raise ValueError('Unexpected IMET')
    for language in range(10):
        at=base+0x5c+84*language;label='날씨 채널'.encode('utf-16-be');banner[at:at+84]=label+bytes(84-len(label))
    banner[base+0x5f0:base+0x600]=bytes(16);banner[base+0x5f0:base+0x600]=hashlib.md5(banner[base:base+0x600]).digest()
    title.set_content(bytes(banner),0)
    # Correct only this translated channel's allowed region. Keep the HAFE
    # identity, server URLs and the console's KOR/Korean9/Korea136 settings.
    if title.tmd.region!=1:raise ValueError('Expected USA Forecast TMD region')
    title.tmd.region=4
    out.mkdir(parents=True);wad=title.dump_wad();(out/'forecast-ko-personal-test.wad').write_bytes(wad)
    if expected_wad is not None and wad!=expected_wad:raise ValueError('Preserved WAD byte reproduction differs')
    check=lib.title.Title();check.load_wad(wad);modified=[i for i in range(12)if check.get_content_by_index(i)!=originals[i]]
    if modified!=([0,1,3,7,9,10]if args.diagnostic_skip=='home'else[0,1,3,6,7,9,10]):raise ValueError('Unexpected changed content')
    result=dict(revision=args.revision,diagnostic_skip=args.diagnostic_skip,base_sha256=row['sha256'],title_id=title.tmd.title_id,version=7,changed_contents=modified,translated_textboxes=len(translated),remaining_english_panes=len(remaining),weekday_method='BRLYT language panes; original C-locale and RSO preserved',fonts=font_records,local_43K_shared_fonts=korean_font_record,wad_sha256=sha256(wad),Nintendo_signature_valid=False,wiilink_live_compatibility_verified=False,original_design='pane topology and animations preserved; local 43K shared fonts and appended OFL glyphs; short Korean text horizontal fit',incomplete=['remaining long messages','dynamic overlay needs local data replay','manual','banner artwork','live data transport'],config_sha256=sha256(config_path.read_bytes()),dynamic_config_sha256=sha256((ROOT/'configs/forecast-dynamic-ko.json').read_bytes()))
    result.update(manual=manual_record,manual_font=opera_record,manual_config_sha256=sha256((ROOT/'configs/forecast-manual-ko.json').read_bytes()),home_menu=home_record,korean_time_order=time_record,places_config_sha256=sha256((ROOT/'configs/forecast-places-ko.json').read_bytes()),preserved_panes=sorted(config.get('preserved_panes',{})))
    result.update(weekday_method='Seven indexed IA4 caption textures; original weekday selection and color tint preserved',bitmap_captions=bitmap_record,banner_language_groups=banner_groups,TMD_region_before=1,TMD_region_after=4,bottom_Korean_labels='24px height and 2 layout units lower; original hitboxes/animations preserved',temperature_labels_centered=True)
    if args.revision>=95:
        result.update(full_localization_complete=False,
            localization_validation=dict(native_main_clock=True,native_AM_PM=True,native_six_hour_forecast=True,
                clock_hidden_on_globe=True,native_manual_pages=9,native_error_text_styles=22,
                error_text_validation='Native diagnostic presenter; not a reproduction of each original fault flow'),
            incomplete=['alternate native banner states','original full error dialog/control flows',
                'all data-dependent location/weather/UV combinations'],
            live_data_transport='Not verified; capability-zero offline replay only')
    if wind_record:result['korean_wind']=wind_record
    if supply_record:result['supply_conversion']=supply_record
    if runtime_home_record:result['home_runtime_messages']=runtime_home_record
    (out/'build-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'translation-map.json').write_text(json.dumps(translated,ensure_ascii=False,indent=2),encoding='utf-8');(out/'remaining.json').write_text(json.dumps(remaining,indent=2))
    print(json.dumps(result,ensure_ascii=True))

if __name__=='__main__':main()

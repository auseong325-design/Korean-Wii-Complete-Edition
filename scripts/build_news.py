"""Build a Korean News Channel WAD (revision >= 2) from the preserved USA WiiLink copy.

Adds to v1: pane-level fixes, executable UI strings, logo/icon/caption
textures, Korean HOME Menu, Korean manual font and manual. A second WAD with
only the KD URL redirected to the sandbox file feed is written for isolated
Dolphin testing (--test-feed); the main WAD keeps the WiiLink server URL.
The v1 builder is preserved in workspace/channels/news/build_news_v1_snapshot.py.
"""
import argparse,hashlib,json,re,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import *
from kwce.channel_font import extend_font
from kwce.channel_korean_font import korean_shared_fonts

FONT=ROOT/'workspace/channels/forecast/references/NotoSansKR.ttf'
LANGS='(JP|US|GE|FR|SP|IT|DU|EN)'

def utf16_slots(executable,rows):
    """Replace UTF-16 strings at fixed virtual addresses inside their zero-padded slots."""
    from kwce.ppc_patch import to_file
    out=bytearray(executable);done=[]
    for va,expected,target in rows:
        at=to_file(out,va,2);end=at
        while out[end:end+2]!=b'\0\0':end+=2
        slot=end
        while out[slot:slot+2]==b'\0\0'and slot-at<512:slot+=2
        if out[at:end].decode('utf-16-be')!=expected:raise ValueError(f'Unexpected string at {va:#x}')
        data=target.encode('utf-16-be')+b'\0\0'
        if len(data)>slot-at:raise ValueError(f'Korean string exceeds slot at {va:#x}: {target}')
        out[at:slot]=data+bytes(slot-at-len(data));done.append(dict(address=hex(va),target=target))
    return bytes(out),done

def caption(size,text,style,*,safe_outline=False):
    load_library();from PIL import Image,ImageDraw,ImageFont
    w,h=size
    if style=='serif':
        path='C:/Windows/Fonts/batang.ttc';title,sub=text.split('\n')
        img=Image.new('RGBA',size);d=ImageDraw.Draw(img)
        for fs in range(h,6,-1):
            f=ImageFont.truetype(path,fs,index=0)
            if f.getbbox(title)[2]-f.getbbox(title)[0]<=w-4 and fs<=h*0.62:break
        sf=ImageFont.truetype(str(FONT),max(8,h//4));sf.set_variation_by_axes([600])
        b=f.getbbox(title);d.text(((w-(b[2]-b[0]))/2-b[0],1-b[1]),title,font=f,fill='white')
        sb=sf.getbbox(sub);d.text(((w-(sb[2]-sb[0]))/2-sb[0],h-(sb[3]-sb[1])-2-sb[1]),sub,font=sf,fill='white')
        return img
    stroke=max(1,h//14)if style=='outline'else 0
    for fs in range(h,6,-1):
        f=ImageFont.truetype(str(FONT),fs);f.set_variation_by_axes([700 if style=='bold'else 600])
        b=f.getbbox(text,stroke_width=stroke if safe_outline else 1)
        margin=4 if safe_outline else 2
        if b[2]-b[0]<=w-margin and b[3]-b[1]<=h-margin:break
    stroke=max(1,h//14)if style=='outline'else 0
    img=Image.new('RGBA',size);ImageDraw.Draw(img).text(((w-(b[2]-b[0]))/2-b[0],(h-(b[3]-b[1]))/2-b[1]),text,font=f,fill=style=='dark'and(70,70,70,255)or'white',stroke_width=stroke,stroke_fill=(70,70,70,255))
    return img

def localize_textures(content,layout,spec):
    from kwce.tpl import decode,encode,encode_mipmaps
    from kwce.channel_texture import texture_records
    from libWiiPy.archive import decompress_lz77
    records=[]
    news=decompress_lz77(content.get('TPLNews.tpl.LZ'))
    for index,(text,style) in spec['TPLNews'].items():
        index=int(index);old=decode(news,index);new=caption(old.size,text,style)
        if style=='newspaper':
            # Keep the paper art; repaint only the masthead band and draw the Korean title.
            load_library();from PIL import ImageDraw
            if old.size!=(128,128):raise ValueError('Unexpected newspaper title canvas')
            # The original masthead is y=16..39. The former y=8..28 patch
            # left the lower half of the English lettering visible on the globe.
            paper=old.copy();band=(12,16,116,40);ImageDraw.Draw(paper).rectangle((band[0],band[1],band[2]-1,band[3]-1),fill=paper.getpixel((13,17)))
            title=caption((band[2]-band[0],band[3]-band[1]),text,'dark');paper.alpha_composite(title,(band[0],band[1]));new=paper
        news=(encode_mipmaps if style=='newspaper'else encode)(news,index,new);records.append(dict(file='TPLNews',texture=index,text=text,mipmaps_updated=style=='newspaper'))
    content=ChannelArchive(content.replace('TPLNews.tpl.LZ',compress_lz10(news)))
    from kwce.forecast_visual import centered_text,nasa_captions,globe_caption
    from kwce.channel_texture import replace_ia4
    common=decompress_lz77(content.get('TPLCommon.tpl.LZ'))
    days={54:'금요일',55:'월요일',56:'토요일',57:'일요일',58:'목요일',59:'화요일',60:'수요일'}
    for index,text in days.items():
        r=texture_records(common)[index]
        if (r['width'],r['height'],r['format'])!=(72,32,2):raise ValueError('Weekday texture identity')
        common=replace_ia4(common,index,centered_text((72,32),text,FONT,23))
    common,nasa=nasa_captions(common,FONT);common,globe=globe_caption(common)
    content=ChannelArchive(content.replace('TPLCommon.tpl.LZ',compress_lz10(common)))
    for name,text in spec['layout_logos'].items():
        data=layout.get(name);old=decode(data,0);layout=ChannelArchive(layout.replace(name,encode(data,0,caption(old.size,text,'bold'))))
        records.append(dict(file=name,text=text))
    return content,layout,dict(textures=records,weekdays=days,NASA=nasa,globe=globe)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True);args=ap.parse_args()
    if not 2<=args.revision<=100:raise SystemExit('Revision bounds')
    base=ROOT/'workspace/channels/news';out=base/f'build-v{args.revision}'
    if out.exists():raise SystemExit('Existing News build preserved')
    lib=load_library();from libWiiPy.archive import decompress_lz77
    source=base/'originals/news-usa-wiilink-archive.wad';row=next(r for r in json.loads((source.parent/'acquisition.json').read_text())['files']if r['alias']==source.name)
    if sha256(source.read_bytes())!=row['sha256']:raise ValueError('News original changed')
    title=lib.title.Title();title.load_wad(source.read_bytes());assert title.tmd.title_id=='0001000248414745'and len(title.tmd.content_records)==12
    originals=[title.get_content_by_index(i)for i in range(12)]
    mapping=json.loads((ROOT/'configs/news-ko.json').read_text(encoding='utf-8'))
    extra=json.loads((ROOT/'configs/news-extra-ko.json').read_text(encoding='utf-8'))
    content=ChannelArchive(originals[9]);layout=ChannelArchive(decompress_lz77(content.get('news_layout.arc.LZ')));count=0;texts=[]
    for path in list(layout.files):
        if not path.endswith('.brlyt'):continue
        sections=layout_sections(layout.get(path));changed=False
        for i,s in enumerate(sections):
            e=textbox(s)
            if not e:continue
            key=Path(path).stem+'/'+re.sub(LANGS,'',e[0]);target=extra['panes'].get(key)or mapping.get(e[1])
            if target:sections[i]=fit_korean_textbox(replace_textbox(s,target),target);count+=1;changed=True;texts.append(target)
        if changed:layout=ChannelArchive(layout.replace(path,rebuild_layout(layout.get(path),sections)))
    content,layout,texture_record=localize_textures(content,layout,extra['textures'])
    # Article text is drawn with the shared system font (content 7, Korean);
    # layout and content fonts only need the UI strings. A full Hangul set
    # in every font stalled the channel during loading (v2).
    chars=''.join(mapping.values())+''.join(extra['panes'].values())+''.join(t for _,_,t in extra['executable'])+'뉴스 채널오류 코드';fonts=[]
    for path in [p for p in layout.files if p.endswith('.brfnt')]:
        data,record=extend_font(layout.get(path),chars,FONT);layout=ChannelArchive(layout.replace(path,data));fonts.append(dict(file=path,**record))
    data=layout.compact();packed=compress_lz10(data);assert decompress_lz77(packed)==data;content=ChannelArchive(content.replace('news_layout.arc.LZ',packed))
    from kwce.forecast_data import forecast_mapping
    location_config=ROOT/'configs/news-location-glyphs-ko.json'
    location_chars=''.join(forecast_mapping().values())+json.loads(location_config.read_text(encoding='utf-8'))['glyphs']
    for path in [p for p in content.files if p.endswith('.brfnt.LZ')]:
        # Runtime replay revealed a missing Hangul syllable in the Seoul map
        # label. Only the city font needs location glyphs; avoid the v2 stall
        # caused by adding all Hangul syllables to every clock font.
        selected=chars+location_chars if path=='font_weather_city.brfnt.LZ' else chars
        if args.revision>=15:
            # Runtime fonts have fixed roles. Loading the complete static UI
            # alphabet into each clock wastes scarce console heap space.
            selected=(location_chars if path=='font_weather_city.brfnt.LZ' else
                      '년월일요일월화수목금토일오전후시분초' if path=='font_news_date.brfnt.LZ' else
                      '오전후시분초')
        data,record=extend_font(decompress_lz77(content.get(path)),selected,FONT);content=ChannelArchive(content.replace(path,compress_lz10(data)));fonts.append(dict(file=path,**record))
    runtime_home_record=None
    if args.revision>=13:
        from kwce.home_menu import korean_runtime_home_messages
        content,runtime_home_record=korean_runtime_home_messages(content)
    title.set_content(content.compact(),9);shared,shared_record=korean_shared_fonts();title.set_content(shared,7)
    from kwce.home_menu import korean_home_menu
    from kwce.opera_font import korean_opera_font
    from kwce.channel_manual import localize as localize_manual
    home,home_record=korean_home_menu(originals[6],fix_dialogs=args.revision>=11,all_dialog_languages=args.revision>=12);title.set_content(home,6)
    opera,opera_record=korean_opera_font(originals[3]);title.set_content(opera,3)
    manual_config=json.loads((ROOT/'configs/news-manual-ko.json').read_text(encoding='utf-8'));outer=ChannelArchive(originals[10])
    manual,manual_record=localize_manual(outer.get('html-us.arc'),manual_config,ROOT/'workspace/channels/news/work/manual-captures')
    capture_names=sorted({s['capture']for image in manual_config.get('images',{}).values()for s in image.get('shots',[])})
    manual_record['captures']=[dict(file=name,sha256=sha256((base/'work/manual-captures'/name).read_bytes()))for name in capture_names]
    manual_record['config_sha256']=sha256((ROOT/'configs/news-manual-ko.json').read_bytes())
    title.set_content(ChannelArchive(outer.replace('html-us.arc',manual)).compact(),10)
    # Banner/tile (unchanged v1 method: KOR group, Korean notices, original animations).
    outer=ChannelArchive(originals[0][0x640:]);banner_records=[];prefix=bytearray(originals[0][:0x640]);messages=extra['banner']
    for name in['meta/banner.bin','meta/icon.bin']:
        wrapped=outer.get(name);raw=decompress_lz77(wrapped[32:]);a=ChannelArchive(raw);groups=0;btexts=0
        for path in[p for p in a.files if p.endswith('.brlyt')]:
            sections=layout_sections(a.get(path))
            for i,s in enumerate(sections):
                if s[:4]==b'grp1'and s[8:24].split(b'\0')[0]==b'ENG':
                    s=bytearray(s);s[8:24]=b'KOR'+bytes(13);sections[i]=bytes(s);groups+=1
                e=textbox(sections[i])
                if e and e[0]in messages:sections[i]=replace_textbox(sections[i],messages[e[0]]);btexts+=1
            a=ChannelArchive(a.replace(path,rebuild_layout(a.get(path),sections)))
        banner_tex=[]
        for path,spec in extra.get('banner_textures',{}).get(name,{}).items():
            from kwce.tpl import decode,encode
            d=a.get(path);old=decode(d,0);a=ChannelArchive(a.replace(path,encode(d,0,caption(old.size,spec,'outline',safe_outline=args.revision>=14 and path=='arc/timg/news_logoENG.tpl'))));banner_tex.append(path)
        assert all(a.get(p)==ChannelArchive(raw).get(p)for p in a.files if p.endswith('.brlan'))
        data=a.compact();packed=b'LZ77'+compress_lz10(data);assert decompress_lz77(packed)==data
        outer=ChannelArchive(outer.replace(name,b'IMD5'+len(packed).to_bytes(4,'big')+bytes(8)+hashlib.md5(packed).digest()+packed))
        struct.pack_into('>I',prefix,0x40+(0x4c if name.endswith('icon.bin')else 0x50),len(data));banner_records.append(dict(name=name,KOR_groups=groups,texts=btexts,textures=banner_tex,animation_preserved=True))
    for lang in range(10):
        at=0x40+0x5c+84*lang;label='뉴스 채널'.encode('utf-16-be');prefix[at:at+84]=label+bytes(84-len(label))
    prefix[0x630:0x640]=bytes(16);prefix[0x630:0x640]=hashlib.md5(prefix[0x40:0x640]).digest();title.set_content(bytes(prefix)+outer.compact(),0)
    executable,exe_rows=utf16_slots(originals[1],[(int(va,16),src,dst)for va,src,dst in extra['executable']])
    title.set_content(executable,1);title.tmd.region=4
    out.mkdir();wads={}
    for variant in['personal','test-feed']:
        if variant=='test-feed':
            # Isolated Dolphin only: KD reads the seeded sandbox feed through file://.
            from kwce.ppc_patch import to_file
            feed=(ROOT/'workspace/sandbox/news-v1/local-feed').resolve().as_uri()+'/v2/%d/%03d/news.bin'
            exe=bytearray(executable);slot=0x801df210;at=to_file(exe,slot,200)
            if not exe[at:at+24].startswith(b'DVDConvertEntrynumToPath'):raise ValueError('Unexpected debug string slot')
            data=feed.encode('ascii')+b'\0'
            if len(data)>200:raise ValueError('Feed URL too long')
            exe[at:at+len(data)]=data
            hi=(slot+0x8000)>>16;lo=slot&0xffff
            for va,word in[(0x8000822c,(15<<26)|(4<<21)|hi),(0x80008244,(14<<26)|(4<<21)|(4<<16)|lo)]:
                a=to_file(exe,va);old=struct.unpack_from('>I',exe,a)[0]
                if old>>26!=(15 if va==0x8000822c else 14):raise ValueError('Unexpected URL load instruction')
                struct.pack_into('>I',exe,a,word)
            title.set_content(bytes(exe),1)
        wad=title.dump_wad();check=lib.title.Title();check.load_wad(wad)
        for i in range(12):check.get_content_by_index(i)
        name=f'news-ko-{variant}.wad';(out/name).write_bytes(wad);wads[variant]=dict(file=name,sha256=sha256(wad))
    changed=[i for i in range(12)if check.get_content_by_index(i)!=originals[i]]
    result=dict(revision=args.revision,title_id=title.tmd.title_id,base_sha256=row['sha256'],wads=wads,wad_sha256=wads['test-feed']['sha256'],installed_variant='test-feed',translated_textboxes=count,executable_strings=exe_rows,textures=texture_record,fonts=fonts,shared_fonts=shared_record,home_menu=home_record,manual_font=opera_record,manual=manual_record,banners=banner_records,region=4,changed_contents=changed,article_translation='seed time, offline machine translation (kwce.local_mt)',live_service_verified=False)
    result['location_glyph_config_sha256']=sha256(location_config.read_bytes())
    if runtime_home_record:result['home_runtime_messages']=runtime_home_record
    result['location_characters']=''.join(sorted(set(location_chars+chars)))
    (out/'build-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(dict(revision=args.revision,boxes=count,changed=changed,wads=wads)))
if __name__=='__main__':main()

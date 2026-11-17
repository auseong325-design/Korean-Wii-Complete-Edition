"""Forecast v7-specific Korean layout, banner groups and bitmap captions."""
import hashlib,json,re,struct
from .channels import ChannelArchive,layout_sections,rebuild_layout,load_library,compress_lz10,textbox,replace_textbox,fit_korean_textbox
from .channel_texture import decode_ia4,replace_ia4,texture_records

def layout_metrics(stem,pane,section):
    if section[:4]!=b'txt1':return section
    name=re.sub(r'(JP|US|GE|FR|SP|IT|DU)','',pane);out=bytearray(section)
    if stem=='set'and name in ['kion_setT0a','kion_setT1a']:
        # Original split labels used right alignment and unequal 120/190
        # widths. Korean labels are a single centered phrase.
        out[84]=4;struct.pack_into('>f',out,68,120)
    bottom=(stem=='forecast'and(name.startswith('backT')or name.startswith('downT')or name=='aroundT'))or(stem=='around'and name in ['backT','resetT'])or(stem in ['set','set_area1']and name=='backT')
    if bottom:
        old_w,old_h=struct.unpack_from('>ff',out,100)
        struct.pack_into('>ff',out,100,old_w*24/old_h,24)
        struct.pack_into('>f',out,40,struct.unpack_from('>f',out,40)[0]-2)
    return bytes(out)

def centered_text(size,text,font_path,font_size,outline=0):
    load_library();from PIL import Image,ImageDraw,ImageFont
    font=ImageFont.truetype(str(font_path),font_size);font.set_variation_by_axes([600])
    box=font.getbbox(text,stroke_width=outline);w,h=box[2]-box[0],box[3]-box[1]
    if w>size[0]or h>size[1]:raise ValueError('Korean bitmap caption exceeds original texture')
    out=Image.new('RGBA',size);ImageDraw.Draw(out).text(((size[0]-w)/2-box[0],(size[1]-h)/2-box[1]),text,font=font,fill='white',stroke_width=outline,stroke_fill='black')
    return out

def bitmap_captions(common,weather,font_path):
    days={54:'금요일',55:'월요일',56:'토요일',57:'일요일',58:'목요일',59:'화요일',60:'수요일'}
    for index,text in days.items():
        r=texture_records(common)[index]
        if (r['width'],r['height'],r['format'])!=(72,32,2):raise ValueError('Forecast weekday texture identity')
        common=replace_ia4(common,index,centered_text((72,32),text,font_path,23))
    load_library();from PIL import Image,ImageDraw,ImageFont
    font=ImageFont.truetype(str(font_path),14);font.set_variation_by_axes([600])
    credit=[]
    for index in [24,25]:
        original=decode_ia4(weather,index)
        if original.size!=(214,19):raise ValueError('Forecast provider texture identity')
        out=Image.new('RGBA',original.size);draw=ImageDraw.Draw(out);box=font.getbbox('제공:');origin=(1-box[0],(19-(box[3]-box[1]))/2-box[1])
        if index==24:draw.text((origin[0]+1,origin[1]+1),'제공:',font=font,fill='black')
        draw.text(origin,'제공:',font=font,fill='white',stroke_width=1 if index==25 else 0,stroke_fill='black')
        # Retain every company pixel; translate only the provider prefix.
        company=original.crop((100,0,198,19));company_x=round(box[2]-box[0])+6;out.paste(company,(company_x,0))
        weather=replace_ia4(weather,index,out)
        if decode_ia4(weather,index).crop((company_x,0,company_x+98,19)).tobytes()!=company.tobytes():raise ValueError('Company artwork changed')
        credit.append(dict(texture=index,company_pixels_preserved=True))
    common,nasa_record=nasa_captions(common,font_path)
    common,globe_record=globe_caption(common)
    return common,weather,dict(weekday_textures=days,provider_prefix='제공:',company='weathernews',credits=credit,NASA=nasa_record,globe_transition=globe_record)

def nasa_captions(common,font_path):
    load_library();from PIL import Image,ImageDraw,ImageFont
    font=ImageFont.truetype(str(font_path),14);font.set_variation_by_axes([600]);rows=[]
    for index in [3,6]:
        original=decode_ia4(common,index)
        if original.size!=(164,18):raise ValueError('NASA caption identity')
        out=Image.new('RGBA',original.size);draw=ImageDraw.Draw(out);label='이미지 소유:'
        box=font.getbbox(label);origin=(1-box[0],(18-(box[3]-box[1]))/2-box[1])
        if index==3:draw.text((origin[0]+1,origin[1]+1),label,font=font,fill='black')
        draw.text(origin,label,font=font,fill='white',stroke_width=1 if index==6 else 0,stroke_fill='black')
        nasa=original.crop((122,0,164,18));nasa_x=round(box[2]-box[0])+6
        if nasa_x+42>164:raise ValueError('NASA Korean prefix exceeds texture')
        out.paste(nasa,(nasa_x,0));common=replace_ia4(common,index,out)
        if decode_ia4(common,index).crop((nasa_x,0,nasa_x+42,18)).tobytes()!=nasa.tobytes():raise ValueError('NASA pixels changed')
        rows.append(dict(texture=index,NASA_original_pixels_preserved=True))
    return common,dict(text='이미지 소유: NASA',textures=rows)

def globe_caption(common):
    from pathlib import Path
    load_library();from PIL import Image,ImageDraw,ImageFont
    path=Path('C:/Windows/Fonts/batang.ttc')
    source=path.read_bytes();digest=hashlib.sha256(source).hexdigest()
    lock=json.loads((Path(__file__).resolve().parents[1]/'configs/forecast-serif-font.lock.json').read_text())
    if digest!=lock['sha256']:raise ValueError('Pinned local Korean serif font differs')
    font=ImageFont.truetype(str(path),60,index=0)
    if font.getname()!=('Batang','Regular'):raise ValueError('Expected Batang Regular')
    original=decode_ia4(common,102)
    if original.size!=(206,58):raise ValueError('Globe transition texture identity')
    box=font.getbbox('지구본');width,height=box[2]-box[0],box[3]-box[1]
    if width>206 or height>58:raise ValueError('Serif title exceeds original canvas')
    out=Image.new('RGBA',original.size);ImageDraw.Draw(out).text(((206-width)/2-box[0],(58-height)/2-box[1]),'지구본',font=font,fill='white')
    common=replace_ia4(common,102,out)
    return common,dict(texture=102,text='지구본',font='Batang Regular',font_size=60,font_sha256=digest,font_file_distributed=False,canvas_preserved=True,style='Korean serif with stroke contrast; centered in original Globe canvas')

def korean_banner_text(section,*,natural_title=False,title_font_ratio=1.0):
    entry=textbox(section)
    if entry is None:return section,None
    pane,source=entry;target=None
    if pane.startswith('titleENG'):target='날씨 채널'
    elif pane.startswith('sprt_WW'):target='제공: weathernews'
    elif pane=='textT0ENG':target='날씨 채널에서는\n국내외의 일기 예보를\n바로 확인할 수 있습니다.\n\n시작을 선택해 주세요.'
    elif pane=='textT1ENG':target='최신 일기 예보를\n가져올 수 없습니다.\n\n시작을 선택해 주세요.'
    elif pane=='textT2ENG':target='현재 지역으로 설정한 도시의\n최신 일기 예보가 있으면\n이 화면에 표시됩니다.\n\n시작을 선택해 주세요.'
    if target is None:return section,None
    result=replace_textbox(section,target)
    if natural_title and pane.startswith('titleENG'):
        result=bytearray(result)
        struct.pack_into('>f',result,100,struct.unpack_from('>f',result,104)[0]*title_font_ratio)
        result=bytes(result)
    return fit_korean_textbox(result,target),dict(pane=pane,target=target)

def korean_banner_groups(content,*,translate=False,font_path=None,natural_icon_title=False,icon_font_ratio=1.0):
    load_library();from libWiiPy.archive import decompress_lz77
    if content[0x80:0x84]!=b'IMET':raise ValueError('Expected offset IMET')
    outer=ChannelArchive(content[0x640:]);records=[]
    for name in ['meta/banner.bin','meta/icon.bin']:
        wrapped=outer.get(name)
        if wrapped[:4]!=b'IMD5'or wrapped[16:32]!=hashlib.md5(wrapped[32:]).digest():raise ValueError('Banner IMD5 integrity')
        raw=decompress_lz77(wrapped[32:]);archive=ChannelArchive(raw);changed=0;captions=[]
        for path in [p for p in archive.files if p.endswith('.brlyt')]:
            layout=archive.get(path);sections=layout_sections(layout)
            if any(s[:4]==b'grp1'and s[8:24].split(b'\0')[0]==b'KOR'for s in sections):raise ValueError('Unexpected existing Korean group')
            for i,section in enumerate(sections):
                if section[:4]==b'grp1'and section[8:24].split(b'\0')[0]==b'ENG':
                    revised=bytearray(section);revised[8:24]=b'KOR'+bytes(13);sections[i]=bytes(revised);changed+=1
                if translate:
                    sections[i],record=korean_banner_text(sections[i],natural_title=natural_icon_title and name=='meta/icon.bin',title_font_ratio=icon_font_ratio)
                    if record:captions.append(record)
            archive=ChannelArchive(archive.replace(path,rebuild_layout(layout,sections)))
        if changed!=1 or(not translate and len(archive.data)!=len(raw)):raise ValueError('Banner language group bounds')
        if translate:
            expected=11 if name=='meta/banner.bin'else 2
            if len(captions)!=expected:raise ValueError('Banner caption identity/count')
            if name=='meta/banner.bin':
                if font_path is None:raise ValueError('Banner caption font required')
                path='arc/timg/belt_currentUS.tpl';texture=archive.get(path)
                if decode_ia4(texture,0).size!=(208,40):raise ValueError('Banner current-weather texture identity')
                texture=replace_ia4(texture,0,centered_text((208,40),'현재 날씨',font_path,30,outline=1))
                archive=ChannelArchive(archive.replace(path,texture))
            archive=ChannelArchive(archive.compact())
        if any(archive.get(p)!=ChannelArchive(raw).get(p)for p in archive.files if p.endswith('.brlan')):raise ValueError('Banner animation changed')
        payload=b'LZ77'+compress_lz10(archive.data)
        header=b'IMD5'+len(payload).to_bytes(4,'big')+bytes(8)+hashlib.md5(payload).digest()
        if decompress_lz77(payload)!=archive.data:raise ValueError('Banner compression roundtrip')
        outer=ChannelArchive(outer.replace(name,header+payload));records.append(dict(file=name,ENG_group_renamed_to_KOR=True,uncompressed_size_preserved=len(archive.data)==len(raw),uncompressed_size=len(archive.data),translated_captions=captions,animation_bytes_preserved=True))
    prefix=bytearray(content[:0x640])
    for row in records:
        at=0x40+(0x4c if row['file']=='meta/icon.bin'else 0x50)
        struct.pack_into('>I',prefix,at,row['uncompressed_size'])
    out=bytes(prefix)+outer.compact()
    return out,records

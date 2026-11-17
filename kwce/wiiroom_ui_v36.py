"""Refine Korean title geometry and stable notice/settings text alignment."""
import struct
from .channels import ChannelArchive,layout_sections,rebuild_layout
from .wiiroom_formats import decompress_lz11,compress_lz11_optimal
from .wiiroom_wordmark_v36 import TITLE,geometry,letter_image,transition_wordmark
from . import tpl

def refine_content(content,original,geometric=False):
    a=ChannelArchive(content);source=ChannelArchive(original);changed=[];record={}
    title='layout/Title/Title_Scene.lex';ar=ChannelArchive(decompress_lz11(a.get(title)))
    if geometric:
        # Revision 58+: geometric Hangul on the native W's height, letter gap and
        # a re-centred table + wordmark group (see wiiroom_wordmark_v58).
        from .wiiroom_wordmark_v58 import wordmark,letter_texture,MARGIN
        ar,record['title_geometry'],targets=wordmark(ar,'title')
        for c,suffix in [('의','No'),('방','Ma')]:
            p=next(p for p in ar.files if p.endswith('/Title_Logo_'+suffix+'.tpl'));raw=ar.get(p)
            q=targets['Pic_Logo_'+suffix][2:]
            ar=ChannelArchive(ar.replace(p,tpl.encode(raw,0,letter_texture(c,q,MARGIN['title'],tpl.decode(raw,0).size))))
    else:
        for c,suffix in [('의','No'),('방','Ma')]:
            p=next(p for p in ar.files if p.endswith('/Title_Logo_'+suffix+'.tpl'));raw=ar.get(p)
            ar=ChannelArchive(ar.replace(p,tpl.encode(raw,0,letter_image(c,tpl.decode(raw,0).size))))
        ar,record['title_geometry']=geometry(ar,TITLE)
    a=ChannelArchive(a.replace(title,compress_lz11_optimal(ar.compact())));changed.append(title)
    path='layout/Wipe/Fade_White_Logo.lex';ar=ChannelArchive(decompress_lz11(a.get(path)));old=ChannelArchive(decompress_lz11(source.get(path)))
    p=next(p for p in ar.files if p.endswith('/Title_Logo.tpl'));raw=ar.get(p)
    if geometric:
        from .wiiroom_wordmark_v58 import transition_wordmark as geometric_transition
        image,record['transition_wordmark']=geometric_transition(tpl.decode(old.get(p),0))
    else:image=transition_wordmark(tpl.decode(old.get(p),0))
    ar=ChannelArchive(ar.replace(p,tpl.encode(raw,0,image)))
    a=ChannelArchive(a.replace(path,compress_lz11_optimal(ar.compact())));changed.append(path)
    for path in a.files:
        setting=any(path==f'layout/Option/{name}.lex'for name in ('Family_Btn','Video_Btn','Area_Btn','Agree_Btn'))
        notice=path.endswith('/Message_Update_Text.lex')
        if not(setting or notice):continue
        ar=ChannelArchive(decompress_lz11(a.get(path)));count=0
        for p in ar.files:
            if not p.endswith('.brlyt'):continue
            data=ar.get(p);sections=layout_sections(data)
            for i,s in enumerate(sections):
                if s[:4]!=b'txt1':continue
                name=s[12:28].split(b'\0')[0].decode()
                if(setting and name!='Text_Btn')or(notice and not name.startswith('Text_Update_')):continue
                b=bytearray(s)
                if setting:
                    struct.pack_into('>ff',b,36,30.,0.);struct.pack_into('>ff',b,68,190.,38.)
                    b[84]=4;b[85]=1 # middle/centre, explicit centred line alignment
                    struct.pack_into('>ff',b,100,25.6,30.4)
                else:
                    # Do not recenter each incomplete typewriter line as it grows.
                    struct.pack_into('>f',b,68,460.);b[84]=0;b[85]=0
                sections[i]=bytes(b);count+=1
            ar=ChannelArchive(ar.replace(p,rebuild_layout(data,sections)))
        if count!=(1 if setting else 2):raise ValueError('UI label refinement coverage differs')
        a=ChannelArchive(a.replace(path,compress_lz11_optimal(ar.compact())));changed.append(path)
    if len(changed)!=7:raise ValueError('Expected seven Korean UI layouts')
    record.update(changed_layouts=changed,settings_buttons=4,stable_notice_textboxes=2,native_wii_textures_preserved=True)
    return a.compact(),record

"""Translate literal layout labels and append their Korean font glyphs."""
from .channels import ChannelArchive,layout_sections,textbox,replace_textbox,fit_korean_textbox,rebuild_layout
from .votes_resources import decode_yaz0,encode_yaz0_greedy
from .channel_font import extend_font


def localize_layouts(outer,mapping,font_path):
    characters=''.join(mapping.values());stats=dict(textboxes=0,fonts=0,unsafe_archives_preserved=0)
    def walk(data,glyphs=characters):
        if data[:4]==b'Yaz0':
            old=decode_yaz0(data);new=walk(old,glyphs)
            return encode_yaz0_greedy(new)if old!=new else data
        if data[:4]==b'RLYT':
            sections=layout_sections(data);changed=False
            for i,s in enumerate(sections):
                entry=textbox(s)
                if entry and entry[1]in mapping:
                    target=mapping[entry[1]];sections[i]=fit_korean_textbox(replace_textbox(s,target),target);stats['textboxes']+=1;changed=True
            return rebuild_layout(data,sections)if changed else data
        if data[:4]==b'RFNT':
            new,record=extend_font(data,glyphs,font_path)
            stats['fonts']+=bool(record['added_glyphs']);return new
        if data[:4]==bytes.fromhex('55aa382d'):
            try:archive=ChannelArchive(data)
            except ValueError:stats['unsafe_archives_preserved']+=1;return data
            needed=[]
            for path in archive.files:
                raw=archive.get(path)
                if raw[:4]==b'RLYT':
                    for section in layout_sections(raw):
                        entry=textbox(section)
                        if entry and entry[1]in mapping:needed.append(mapping[entry[1]])
            if needed:glyphs=''.join(needed)
            changed=False
            for path in archive.files:
                old=archive.get(path);new=walk(old,glyphs)
                if new!=old:archive=ChannelArchive(archive.replace(path,new));changed=True
            return archive.compact()if changed else data
        return data
    return ChannelArchive(walk(outer.data)),stats


def upright_system_text(outer,width_scale=.96,height_scale=1.035,skip=('/HBM/','/Keyboard/'),extra=None):
    """Restore upright Hangul in system-font (wbf1) text boxes.

    The Korean console font draws Hangul about 4-7% wider than tall at the
    channel's 0.842 box ratio (measured on screen in 16:9, so not an aspect
    artefact). Narrow slightly and grow slightly; panes and animations stay.
    `extra` maps (layout file name, pane-name prefix) to further (x, y) factors.
    """
    import struct
    stats=dict(textboxes=0,layouts=0)
    def walk(data,where):
        if data[:4]==b'Yaz0':
            old=decode_yaz0(data);new=walk(old,where)
            return encode_yaz0_greedy(new)if old!=new else data
        if data[:4]==b'RLYT':
            sections=layout_sections(data);fnl=next((s for s in sections if s[:4]==b'fnl1'),None);names=[]
            if fnl:
                for i in range(struct.unpack_from('>H',fnl,8)[0]):
                    at=12+struct.unpack_from('>I',fnl,12+8*i)[0];names.append(fnl[at:fnl.index(b'\0',at)])
            changed=False
            for i,s in enumerate(sections):
                if s[:4]!=b'txt1':continue
                font=struct.unpack_from('>H',s,0x52)[0]
                if font>=len(names)or not names[font].startswith(b'RevoIpl_RodinNTLGPro'):continue
                fx,fy=struct.unpack_from('>ff',s,0x64)
                if not(0<fx<200 and 0<fy<200):raise ValueError('Textbox metric bounds')
                sx,sy=width_scale,height_scale;pane=s[12:28].split(b'\0')[0].decode('ascii')
                for (layout,prefix),(ex,ey) in (extra or {}).items():
                    if where.endswith('/'+layout)and pane.startswith(prefix):sx*=ex;sy*=ey;stats['extra']=stats.get('extra',0)+1
                result=bytearray(s);struct.pack_into('>ff',result,0x64,fx*sx,fy*sy);sections[i]=bytes(result);stats['textboxes']+=1;changed=True
            if changed:stats['layouts']+=1
            return rebuild_layout(data,sections)if changed else data
        if data[:4]==bytes.fromhex('55aa382d'):
            if any(part in where for part in skip):return data
            try:archive=ChannelArchive(data)
            except ValueError:return data
            changed=False
            for path in archive.files:
                old=archive.get(path);new=walk(old,where+'/'+path)
                if new!=old:archive=ChannelArchive(archive.replace(path,new));changed=True
            return archive.compact()if changed else data
        return data
    return ChannelArchive(walk(outer.data,'')),stats

"""Translate static BRLYT labels as well as runtime BMG strings."""
import json,re,struct
from pathlib import Path
from .channels import ChannelArchive,load_library,layout_sections,textbox,replace_textbox,fit_korean_textbox
from .wiiroom_formats import decompress_lz11,compress_lz11_optimal,compress_lz10_optimal

JP=re.compile('[\u3040-\u30ff\u3400-\u9fff]')

def bounded_text(section):
    try:return textbox(section),False
    except ValueError:
        if section[:4]!=b'txt1'or len(section)<116:raise
        # Some original placeholders use 0xff/0xffff sentinel lengths. Bound
        # the string by its section and terminator, never by that sentinel.
        off=struct.unpack_from('>I',section,88)[0]
        if not 116<=off<len(section)or off%2:raise ValueError('Invalid static label pointer')
        data=section[off:];end=next((i for i in range(0,len(data)-1,2)if data[i:i+2]==b'\0\0'),None)
        if end is None:raise ValueError('Unterminated static label')
        return (section[12:28].split(b'\0')[0].decode('ascii'),data[:end].decode('utf-16-be')),True

def korean_static_labels(content,preserve_capacity=False):
    lib=load_library();from libWiiPy.archive import decompress_lz77
    cfg=json.loads((Path(__file__).resolve().parents[1]/'configs/wiiroom-static-v32-ko.json').read_text(encoding='utf-8'))
    mapping=cfg['messages'];a=ChannelArchive(content);records=[];fixed=0;empty=[];layouts=[]
    for name in a.files:
        if not name.startswith('layout/')or not name.endswith('.lex'):continue
        raw=a.get(name);kind=raw[0];decoded=decompress_lz11(raw)if kind==17 else decompress_lz77(raw)if kind==16 else raw
        try:inner=ChannelArchive(decoded)
        except ValueError:
            if len(decoded)==98:empty.append(name);continue # original empty placeholder archive
            raise
        touched=False
        for p in inner.files:
            if not p.endswith('.brlyt'):continue
            data=inner.get(p);sections=layout_sections(data);new=[];changed=False
            for sec in sections:
                if sec[:4]!=b'txt1':new.append(sec);continue
                item,repaired=bounded_text(sec)
                if item and JP.search(item[1]):
                    if item[1]not in mapping:raise ValueError('Untranslated static UI label: '+ascii(item[1]))
                    text=mapping[item[1]]
                    capacity=struct.unpack_from('>H',sec,76)[0];length=struct.unpack_from('>H',sec,78)[0]
                    translated=replace_textbox(sec,text)
                    if not preserve_capacity or capacity<=length:
                        translated=fit_korean_textbox(translated,text)
                    if preserve_capacity:
                        translated=bytearray(translated)
                        struct.pack_into('>H',translated,76,max(capacity,struct.unpack_from('>H',translated,76)[0]))
                        translated=bytes(translated)
                    sec=translated;changed=True
                    fixed+=int(repaired);records.append(dict(layout=name,pane=item[0],text=text))
                new.append(sec)
            if changed:
                output=bytearray(data[:16]+b''.join(new));struct.pack_into('>I',output,8,len(output))
                inner=ChannelArchive(inner.replace(p,bytes(output)));touched=True
        if touched:
            payload=inner.compact();packed=compress_lz11_optimal(payload)if kind==17 else compress_lz10_optimal(payload)if kind==16 else payload
            a=ChannelArchive(a.replace(name,packed));layouts.append(name)
    result=dict(labels=records,count=len(records),sentinel_labels_repaired=fixed,empty_reference_archives=empty,changed_layouts=layouts)
    if preserve_capacity:result['original_runtime_buffer_capacity_preserved']=True
    return a.compact(),result

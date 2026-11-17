"""Private Wii Room UI inventory; stdout contains derived counts only."""
import collections,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,ChannelArchive,layout_sections,textbox
from kwce.wiiroom_formats import decompress_lz11
from kwce.votes_resources import bmg_sections,bmg_message


def main():
    lib=load_library();from libWiiPy.archive import decompress_lz77
    base=ROOT/'workspace/channels/wiiroom';title=lib.title.Title();title.load_wad((base/'originals/wiiroom-english-wiilink-archive.wad').read_bytes())
    a=ChannelArchive(title.get_content_by_index(2));bmg=decompress_lz77(a.get('msg/message.lex'))
    sections=bmg_sections(bmg);inf=next(s for s in sections if s[:4]==b'INF1');dat=next(s for s in sections if s[:4]==b'DAT1');stride=int.from_bytes(inf[10:12],'big');messages=[]
    for i in range(int.from_bytes(inf[8:10],'big')):
        raw=bmg_message(dat,8+int.from_bytes(inf[16+i*stride:20+i*stride],'big'))
        messages.append(dict(index=i,raw_hex=raw.hex(),text=raw.decode('utf-16-be',errors='replace'),has_controls=b'\0\x1a'in raw))
    out=base/'analysis';out.mkdir(exist_ok=True)
    (out/'messages.json').write_text(json.dumps(messages,ensure_ascii=False,indent=2),encoding='utf-8')
    boxes=[];formats=collections.Counter();unsupported=[]
    for name in [p for p in a.files if p.startswith('layout/')and p.endswith('.lex')]:
        raw=a.get(name);raw=decompress_lz11(raw)if raw[:1]==b'\x11'else decompress_lz77(raw)if raw[:1]==b'\x10'else raw
        try:inner=ChannelArchive(raw)
        except ValueError:
            unsupported.append(dict(resource=name,archive_size=len(raw),archive_magic=raw[:4].hex()));continue
        for path in inner.files:
            formats[Path(path).suffix]+=1
            if not path.endswith('.brlyt'):continue
            for sec in layout_sections(inner.get(path)):
                try:entry=textbox(sec)
                except ValueError:
                    unsupported.append(dict(resource=name,layout=path,size=len(sec),capacity=int.from_bytes(sec[76:78],'big'),length=int.from_bytes(sec[78:80],'big'),offset=int.from_bytes(sec[88:92],'big')));continue
                if entry:boxes.append(dict(resource=name,layout=path,pane=entry[0],text=entry[1]))
    (out/'textboxes.json').write_text(json.dumps(boxes,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'unsupported-textboxes.json').write_text(json.dumps(unsupported,indent=2))
    result=dict(messages=len(messages),messages_with_controls=sum(r['has_controls']for r in messages),layout_resources=496,textboxes=len(boxes),unsupported_textboxes=len(unsupported),layout_formats=dict(formats))
    (out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))


if __name__=='__main__':main()

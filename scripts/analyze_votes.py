"""Private local inventory; stdout contains counts only, never resource text."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,ChannelArchive,layout_sections,textbox,sha256
from kwce.votes_resources import decode_yaz0

def main():
    base=ROOT/'workspace/channels/votes';lib=load_library();title=lib.title.Title()
    source=base/'originals/votes-usa-wiilink-archive.wad';title.load_wad(source.read_bytes())
    rows=[];resources=[]
    def walk(data,path):
        if data[:4]==b'Yaz0':return walk(decode_yaz0(data),path+'!')
        if data[:4]==bytes.fromhex('55aa382d'):
            archive=ChannelArchive(data)
            for name in archive.files:walk(archive.get(name),path+'/'+name)
        elif data[:4]==b'RLYT':
            for section in layout_sections(data):
                entry=textbox(section)
                if entry:rows.append(dict(path=path,pane=entry[0],text=entry[1]))
        else:resources.append(dict(path=path,size=len(data),magic=data[:4].hex()))
    for i in range(2,len(title.tmd.content_records)):walk(title.get_content_by_index(i),str(i))
    private=base/'analysis';private.mkdir(exist_ok=True)
    (private/'textboxes.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    (private/'resources.json').write_text(json.dumps(resources,indent=2))
    summary=dict(source_sha256=sha256(source.read_bytes()),textboxes=len(rows),unique_texts=len({r['text']for r in rows}),message_files=sum(r['magic']=='4d455347'for r in resources),runtime_verified=False)
    (private/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
if __name__=='__main__':main()

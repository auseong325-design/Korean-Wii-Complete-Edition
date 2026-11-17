"""Private Mii Contest Channel inventory; stdout emits counts and format metadata."""
import json,sys,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,ChannelArchive,layout_sections,textbox
from kwce.votes_resources import decode_yaz0,bmg_sections,bmg_message

def main():
    base=ROOT/'workspace/channels/mii-contest';lib=load_library();from libWiiPy.archive import decompress_lz77
    title=lib.title.Title();title.load_wad((base/'originals/mii-contest-usa-wiilink-archive.wad').read_bytes())
    resources=[];messages=[];textboxes=[]
    def walk(data,path,depth=0):
        if depth>12:raise ValueError('Archive recursion bound')
        if data[:4]==b'Yaz0':return walk(decode_yaz0(data),path+'!',depth+1)
        if data[:4]==b'LZ77'or data[:1]==b'\x10':
            try:raw=decompress_lz77(data)
            except (ValueError,IndexError):raw=None
            if raw is not None:return walk(raw,path+'!',depth+1)
        if data[:4]==bytes.fromhex('55aa382d'):
            try:archive=ChannelArchive(data)
            except ValueError:
                resources.append(dict(path=path,size=len(data),magic='unparsed-u8-preserved'));return
            for name in archive.files:walk(archive.get(name),path+'/'+name,depth+1)
        elif data[:8]==b'MESGbmg1':
            sections=bmg_sections(data);inf=next(s for s in sections if s[:4]==b'INF1');dat=next(s for s in sections if s[:4]==b'DAT1');stride=int.from_bytes(inf[10:12],'big')
            for i in range(int.from_bytes(inf[8:10],'big')):
                raw=bmg_message(dat,8+int.from_bytes(inf[16+i*stride:20+i*stride],'big'))
                messages.append(dict(path=path,index=i,raw_hex=raw.hex()))
        elif data[:4]==b'RLYT':
            for s in layout_sections(data):
                entry=textbox(s)
                if entry:textboxes.append(dict(path=path,pane=entry[0],text=entry[1]))
        else:resources.append(dict(path=path,size=len(data),magic=data[:4].hex()))
    for i in range(2,len(title.tmd.content_records)):walk(title.get_content_by_index(i),str(i))
    out=base/'analysis';out.mkdir(exist_ok=True)
    for name,value in [('resources',resources),('messages',messages),('textboxes',textboxes)]:
        (out/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    result=dict(title_id=title.tmd.title_id,messages=len(messages),message_files=len({r['path']for r in messages}),textboxes=len(textboxes),resources=len(resources),formats=collections.Counter(r['magic']for r in resources).most_common(8))
    (out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()

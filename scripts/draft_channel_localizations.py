"""Offline-only draft translation. Never sends channel resources to a service."""
import json,re,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools/local-translation/python')]
from kwce.channels import load_library,ChannelArchive
from kwce.votes_resources import decode_yaz0,bmg_sections,bmg_message

def messages(data):
    sections=bmg_sections(data);inf=next(s for s in sections if s[:4]==b'INF1');dat=next(s for s in sections if s[:4]==b'DAT1');stride=int.from_bytes(inf[10:12],'big')
    return [bmg_message(dat,8+int.from_bytes(inf[16+i*stride:20+i*stride],'big'))for i in range(int.from_bytes(inf[8:10],'big'))]

def tokenize(raw):
    chunks=[];text=bytearray();pos=0;controls=0
    while pos<len(raw):
        if raw[pos:pos+2]==b'\0\x1a':
            if text:chunks.append(text.decode('utf-16-be'));text.clear()
            length=raw[pos+2];chunks.append('{CTRL'+str(controls)+'}');controls+=1;pos+=length
        else:text.extend(raw[pos:pos+2]);pos+=2
    if text:chunks.append(text.decode('utf-16-be'))
    return chunks

def main():
    import ctranslate2,sentencepiece
    folder=ROOT/'tools/local-translation';lock=json.loads((folder/'model-lock.json').read_text())
    if hashlib.sha256((folder/'en-ko-1.1.argosmodel').read_bytes()).hexdigest()!=lock['sha256']:raise ValueError('Model hash mismatch')
    sp=sentencepiece.SentencePieceProcessor(model_file=str(folder/'model/en_ko/sentencepiece.model'));engine=ctranslate2.Translator(str(folder/'model/en_ko/model'),device='cpu',compute_type='int8',intra_threads=4)
    lib=load_library();vote=lib.title.Title();vote.load_wad((ROOT/'workspace/channels/votes/originals/votes-usa-wiilink-archive.wad').read_bytes());va=ChannelArchive(vote.get_content_by_index(10));nested=ChannelArchive(decode_yaz0(va.get('Channel/Screen/Usa/Layout00.szs')))
    nintendo=lib.title.Title();nintendo.load_wad((ROOT/'workspace/channels/nintendo/originals/nintendo-usa-wiilink-archive.wad').read_bytes());na=ChannelArchive(nintendo.get_content_by_index(5))
    groups={'votes':messages(nested.get('vote_message_U.bmg')),'nintendo':messages(na.get('message/promotion_message_UE.bmg'))}
    protected=re.compile(r'(\{CTRL\d+\}|%[-+0-9.*]*[a-zA-Z]|Nintendo DS|Nintendo|WiiConnect24|WiiLink|Wii|Mii|\n)')
    cache={};jobs={}
    for group,rows in groups.items():
        jobs[group]=[sum((protected.split(chunk)for chunk in tokenize(raw)),[])for raw in rows]
        for chunks in jobs[group]:
            for chunk in chunks:
                key=chunk.strip()
                if key and re.search('[A-Za-z]',key)and not protected.fullmatch(chunk):cache.setdefault(key,None)
    keys=list(cache)
    for start in range(0,len(keys),32):
        batch=keys[start:start+32];results=engine.translate_batch([sp.encode(s,out_type=str)for s in batch],beam_size=4,max_decoding_length=384)
        for key,result in zip(batch,results):cache[key]=sp.decode(result.hypotheses[0])
    output={}
    for group,rows in jobs.items():
        mapping={}
        for i,chunks in enumerate(rows):
            value=''
            for chunk in chunks:
                key=chunk.strip()
                if key in cache:
                    value+=(' 'if chunk.startswith(' ')else'')+cache[key]+(' 'if chunk.endswith(' ')else'')
                else:value+=chunk
            mapping[str(i)]=value
        output[group]=mapping
    prior=json.loads((ROOT/'configs/votes-messages-ko.json').read_text(encoding='utf-8'));output['votes'].update(prior['messages'])
    dest=ROOT/'workspace/channels/localization-drafts';dest.mkdir(exist_ok=True)
    for group,mapping in output.items():(dest/(group+'-ko-draft.json')).write_text(json.dumps(dict(status='offline-machine-draft-needs-review',messages=mapping),ensure_ascii=False,indent=2),encoding='utf-8')
    (dest/'engine-lock.json').write_text(json.dumps(dict(model=lock,ctranslate2='4.6.0',sentencepiece='0.2.0',setuptools='75.8.0',outbound_resource_transfer=False),indent=2))
    print(json.dumps(dict(draft_message_counts={k:len(v)for k,v in output.items()},translated_chunks=len(cache),review_complete=False)))
if __name__=='__main__':main()

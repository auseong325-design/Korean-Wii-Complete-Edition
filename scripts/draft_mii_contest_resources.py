"""Offline Korean layout/manual drafts. Emits counts, never source text."""
import hashlib, json, re, sys
from html.parser import HTMLParser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools/local-translation/python')]
from kwce.channels import load_library,ChannelArchive
from kwce.votes_resources import decode_yaz0


def main():
    import ctranslate2,sentencepiece
    base=ROOT/'workspace/channels/mii-contest';out=base/'draft/resources-v1'
    if out.exists():raise SystemExit('Existing resource draft preserved')
    model=ROOT/'tools/local-translation/m2m100-418m-int8'
    for row in json.loads((model/'source-lock.json').read_text())['files']:
        if hashlib.sha256((model/row['file']).read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Model changed')
    sp=sentencepiece.SentencePieceProcessor(model_file=str(model/'spm.128k.model'))
    engine=ctranslate2.Translator(str(model),device='cpu',compute_type='int8',intra_threads=4)
    cache={};protected=re.compile(r'(Nintendo|WiiConnect24|WiiLink|Wii|Mii|%[-+0-9.*]*[a-zA-Z]|\n)')
    def pieces(text):return protected.split(text)
    def collect(text):
        for s in pieces(text):
            if re.search('[A-Za-z]',s)and not protected.fullmatch(s):cache.setdefault(s.strip(),None)
    rows=json.loads((base/'analysis/textboxes.json').read_text(encoding='utf-8'))
    for row in rows:collect(row['text'])
    lib=load_library();title=lib.title.Title();title.load_wad((base/'originals/mii-contest-usa-wiilink-archive.wad').read_bytes())
    archive=ChannelArchive(title.get_content_by_index(4));manual=ChannelArchive(decode_yaz0(archive.get('content4/Basic/VCMV/US.szs')))
    documents={p:manual.get(p).decode('utf-8')for p in manual.files if p.endswith('.html')}
    class TextNodes(HTMLParser):
        def __init__(self):super().__init__(convert_charrefs=False);self.skip=0
        def handle_starttag(self,t,a):
            if t in ['script','style']:self.skip+=1
        def handle_endtag(self,t):
            if t in ['script','style']:self.skip-=1
        def handle_data(self,s):
            if not self.skip:collect(s)
    for doc in documents.values():TextNodes().feed(doc)
    keys=list(cache)
    for start in range(0,len(keys),16):
        batch=keys[start:start+16]
        rr=engine.translate_batch([['__en__']+sp.encode(s,out_type=str)+['</s>']for s in batch],target_prefix=[['__ko__']for _ in batch],beam_size=4,max_decoding_length=384)
        for key,r in zip(batch,rr):cache[key]=sp.decode([x for x in r.hypotheses[0]if not x.startswith('__')])
    def translate(s):
        return ''.join((v[:len(v)-len(v.lstrip())]+cache[v.strip()]+v[len(v.rstrip()):])if v.strip()in cache else v for v in pieces(s))
    translated=[dict(path=r['path'],pane=r['pane'],source_sha256=hashlib.sha256(r['text'].encode()).hexdigest(),target=translate(r['text']))for r in rows]
    out.mkdir(parents=True)
    (out/'textboxes-ko.json').write_text(json.dumps(translated,ensure_ascii=False,indent=2),encoding='utf-8')
    # Keep dictionaries private; manual HTML rebuilding/encoding and font QA is a separate step.
    (out/'manual-text-ko.json').write_text(json.dumps(cache,ensure_ascii=False,indent=2),encoding='utf-8')
    record=dict(textboxes=len(rows),manual_html_files=len(documents),unique_chunks=len(cache),translation_engine='local M2M100 int8',source_transmitted=False,review_complete=False,installed=False)
    (out/'manifest.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))


if __name__=='__main__':main()

"""Translate resource drafts entirely on the host; no outbound channel data."""
import hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools/local-translation/python')]
from draft_channel_localizations import tokenize

def main():
    import ctranslate2,sentencepiece
    model=ROOT/'tools/local-translation/m2m100-418m-int8';lock=json.loads((model/'source-lock.json').read_text())
    for row in lock['files']:
        if hashlib.sha256((model/row['file']).read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Local model differs')
    sp=sentencepiece.SentencePieceProcessor(model_file=str(model/'spm.128k.model'));engine=ctranslate2.Translator(str(model),device='cpu',compute_type='int8',intra_threads=4)
    base=ROOT/'workspace/channels/mii-contest';rows=json.loads((base/'analysis/messages.json').read_text(encoding='utf-8'));rows=[r for r in rows if r['path'].endswith('Basic_US.szs!')]
    split=re.compile(r'(\{CTRL\d+\}|%[-+0-9.*]*[a-zA-Z]|Nintendo DS|Nintendo|WiiConnect24|WiiLink|Wii|Miis|Mii|\n)')
    jobs={r['index']:sum((split.split(s)for s in tokenize(bytes.fromhex(r['raw_hex']))),[])for r in rows};cache={}
    terms={'OK':'확인','Cancel':'취소','Yes':'예','No':'아니요','Back':'뒤로','Close':'닫기','Loading...':'불러오는 중입니다...','Please wait...':'잠시 기다려 주세요...','Error code:':'오류 코드:','Error Code:':'오류 코드:','Saving...':'저장하는 중입니다...','Sending...':'보내는 중입니다...','Receiving...':'받는 중입니다...','Reset':'다시 시작','Continue':'계속','Retry':'다시 시도','Start':'시작','Quit':'종료'}
    for chunks in jobs.values():
        for text in chunks:
            key=text.strip()
            if key and re.search('[A-Za-z]',key)and not split.fullmatch(text):cache.setdefault(key,None)
    keys=[k for k in cache if k not in terms];cache.update(terms)
    for start in range(0,len(keys),16):
        batch=keys[start:start+16];results=engine.translate_batch([['__en__']+sp.encode(s,out_type=str)+['</s>']for s in batch],target_prefix=[['__ko__']for _ in batch],beam_size=4,max_decoding_length=256)
        for key,result in zip(batch,results):cache[key]=sp.decode([t for t in result.hypotheses[0]if not t.startswith('__')])
    mapping={}
    for i,chunks in jobs.items():
        mapping[str(i)]=''.join((' 'if text.startswith(' ')else'')+cache[text.strip()]+(' 'if text.endswith(' ')else'')if text.strip()in cache else text for text in chunks)
    out=base/'draft';out.mkdir(exist_ok=True)
    (out/'messages-ko.json').write_text(json.dumps(dict(status='offline-machine-draft-needs-review',source_sha256='ca2cb2cf215dc563f4a1e070892dfc211994755a824b88dc9ed7bec3f8fa4603',messages=mapping),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(messages=len(mapping),unique_chunks=len(cache),review_complete=False)))
if __name__=='__main__':main()

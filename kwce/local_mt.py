"""Offline English→Korean machine translation for dynamic channel data.

Uses the locally pinned M2M100 418M int8 CTranslate2 model under
tools/local-translation. Nothing is sent to an external service. Output is a
machine translation of third-party content for private local testing only.
"""
import hashlib,json,re,sys
from .channels import ROOT

FOLDER=ROOT/'tools/local-translation/m2m100-418m-int8'
_engine=None

def _load():
    global _engine
    if _engine is None:
        sys.path.insert(0,str(ROOT/'tools/local-translation/python'))
        import ctranslate2,sentencepiece
        lock=json.loads((FOLDER/'source-lock.json').read_text())
        for row in lock['files']:
            p=FOLDER/row['file']
            if p.stat().st_size!=row['size']:raise ValueError('Local MT model changed: '+row['file'])
        _engine=(sentencepiece.SentencePieceProcessor(model_file=str(FOLDER/'spm.128k.model')),ctranslate2.Translator(str(FOLDER),device='cpu',compute_type='int8',intra_threads=4))
    return _engine

_SENTENCE=re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"“‘(])')
PROTECT=['WiiConnect24','WiiLink','Wii','Nintendo','REUTERS','Reuters']

def translate(texts,batch=24):
    """Translate a list of strings, keeping paragraph breaks; returns a list."""
    sp,engine=_load();units=[];shape=[]
    for text in texts:
        paragraphs=text.split('\n');row=[]
        for para in paragraphs:
            sentences=[s for s in _SENTENCE.split(para.strip())if s]if para.strip()else[]
            row.append(len(sentences));units.extend(sentences)
        shape.append(row)
    out=[]
    for start in range(0,len(units),batch):
        chunk=units[start:start+batch]
        tokens=[['__en__']+sp.encode(s,out_type=str)+['</s>']for s in chunk]
        results=engine.translate_batch(tokens,target_prefix=[['__ko__']]*len(chunk),beam_size=3,max_decoding_length=256)
        for r in results:
            hyp=[t for t in r.hypotheses[0]if t not in('__ko__','</s>')]
            out.append(sp.decode(hyp).strip())
    result=[];pos=0
    for row in shape:
        paras=[]
        for n in row:paras.append(' '.join(out[pos:pos+n]));pos+=n
        result.append('\n'.join(paras))
    return result

def model_record():
    return dict(model='M2M100 418M int8 (CTranslate2)',lock_sha256=hashlib.sha256((FOLDER/'source-lock.json').read_bytes()).hexdigest(),offline=True,machine_translation=True)

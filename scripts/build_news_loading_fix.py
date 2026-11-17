"""Derive immutable News v16 from v15, changing content1 only."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.news_loading import patch
def main():
    out=ROOT/'workspace/channels/news/build-v16'
    if out.exists():raise ValueError('News v16 preserved')
    previous=ROOT/'workspace/channels/news/build-v15';meta=json.loads((previous/'build-manifest.json').read_text(encoding='utf-8'))
    raw=(previous/'news-ko-personal.wad').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=meta['wads']['personal']['sha256']:raise ValueError('News v15 WAD differs')
    lib=load_library();title=lib.title.Title();title.load_wad(raw);original=[title.get_content_by_index(i)for i in range(12)]
    exe,record=patch(original[1]);title.set_content(exe,1);wad=title.dump_wad();check=lib.title.Title();check.load_wad(wad)
    changed=[i for i in range(12)if original[i]!=check.get_content_by_index(i)]
    if changed!=[1]:raise ValueError('News loading fix changed unexpected content')
    meta.update(revision=16,installed_variant='personal',wads=dict(personal=dict(file='news-ko-personal.wad',sha256=hashlib.sha256(wad).hexdigest())),wad_sha256=hashlib.sha256(wad).hexdigest(),loading_fix=record,parent_revision=15,changed_from_parent=changed,live_service_verified=False)
    out.mkdir(parents=True);(out/'news-ko-personal.wad').write_bytes(wad);(out/'build-manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PASS: News v16, only executable content changed, native checks/other11 contents preserved; hook',record['bytes'],'bytes')
if __name__=='__main__':main()

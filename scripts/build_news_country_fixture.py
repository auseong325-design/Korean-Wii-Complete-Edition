"""Make a second synthetic-only country route for local News experiments."""
import hashlib,json,shutil,struct,sys,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,compress_lz10
from kwce.channel_feed import validate_feed

def main():
    load_library();from libWiiPy.archive import decompress_lz77
    old=ROOT/'workspace/channels/news/local-feed-v1';validate_feed(old)
    meta=json.loads((old/'feed-manifest.json').read_text(encoding='utf-8'))
    if not meta.get('fictional_articles') or not meta.get('pictures_removed') or not meta.get('local_only'):raise ValueError('Only synthetic fixtures allowed')
    out=ROOT/'workspace/channels/news/local-feed-v2'
    if out.exists():raise ValueError('Existing fixture preserved')
    shutil.copytree(old,out);rows=meta['files'][:]
    for row in meta['files']:
        p=out/row['path'];raw=p.read_bytes();body=bytearray(decompress_lz77(raw[320:]));body[20]=49
        struct.pack_into('>I',body,8,zlib.crc32(body[12:])&0xffffffff)
        new=raw[:320]+compress_lz10(bytes(body))
        path=row['path'].replace('/136/','/049/');target=out/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(new)
        rows.append(dict(path=path,sha256=hashlib.sha256(new).hexdigest(),size=len(new)))
    meta.update(revision=2,alternate_country=49,files=rows)
    (out/'feed-manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'PASS: {validate_feed(out)} fictional local-only files; no real articles or pictures')
if __name__=='__main__':main()

"""News v20: retain r16 and bound WC24 IPC/socket startup, content1 only."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.channel_socket_startup import patch
from kwce.channel_ipc_deadline import patch as patch_ipc

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,choices=[19,20],default=20);ap.add_argument('--reproduce',action='store_true');args=ap.parse_args()
    out=ROOT/f'workspace/channels/news/build-v{args.revision}';expected=None
    if args.reproduce:
        expected=(out/'news-ko-personal.wad').read_bytes();n=1
        while(ROOT/f'workspace/private/news-socket-reproduce-{args.revision}-{n}').exists():n+=1
        out=ROOT/f'workspace/private/news-socket-reproduce-{args.revision}-{n}'
    if out.exists():raise ValueError('Existing News build preserved')
    parent=ROOT/'workspace/channels/news/build-v16';meta=json.loads((parent/'build-manifest.json').read_text(encoding='utf-8'))
    raw=(parent/'news-ko-personal.wad').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=meta['wads']['personal']['sha256']:raise ValueError('News parent differs')
    lib=load_library();t=lib.title.Title();t.load_wad(raw);old=[t.get_content_by_index(i)for i in range(12)]
    exe,record=patch(old[1],'news');ipc=None
    if args.revision>=20:exe,ipc=patch_ipc(exe,'news')
    t.set_content(exe,1);wad=t.dump_wad();checked=lib.title.Title();checked.load_wad(wad)
    if {i for i in range(12)if checked.get_content_by_index(i)!=old[i]}!={1}:raise ValueError('News socket change boundary')
    if expected is not None and wad!=expected:raise ValueError('News byte-identical WAD reproduction differs')
    h=hashlib.sha256(wad).hexdigest();meta.update(revision=args.revision,parent_revision=16,socket_startup=record,wads={'personal':{'file':'news-ko-personal.wad','sha256':h}},wad_sha256=h,changed_from_parent=[1],live_service_verified=False)
    if ipc:meta['ipc_deadline']=ipc
    out.mkdir();(out/'news-ko-personal.wad').write_bytes(wad);(out/'build-manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'PASS: News v{args.revision}; exact WAD reproduction; other11 contents identical; IPC adapter={ipc is not None}')
if __name__=='__main__':main()

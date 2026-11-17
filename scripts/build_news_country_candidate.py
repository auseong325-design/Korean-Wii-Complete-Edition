"""Diagnostic News-only country fallback candidate; not a hardware release."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.ppc_patch import assemble,to_file

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--reproduce',action='store_true');args=ap.parse_args()
    out=ROOT/'workspace/channels/news/build-v22'
    expected=None
    if args.reproduce:
        expected=(out/'news-ko-personal.wad').read_bytes();n=1
        while (ROOT/f'workspace/private/news-country-reproduce-v{n}').exists():n+=1
        out=ROOT/f'workspace/private/news-country-reproduce-v{n}'
    if out.exists():raise ValueError('Existing build preserved')
    parent=ROOT/'workspace/channels/news/build-v20';meta=json.loads((parent/'build-manifest.json').read_text(encoding='utf-8'))
    wad=(parent/'news-ko-personal.wad').read_bytes()
    if hashlib.sha256(wad).hexdigest()!=meta['wads']['personal']['sha256']:raise ValueError('Parent WAD differs')
    t=load_library().title.Title();t.load_wad(wad);original=[t.get_content_by_index(i) for i in range(12)]
    exe=bytearray(original[1]);digest=hashlib.sha256(exe).hexdigest()
    if digest!='0a2e48a5c87c48fbb8756328c95ae4801ae70769b742ed32e327162deeea44eb':raise ValueError('Parent executable differs')
    entry=0x800081f8;cave=0x801e0560;offset=to_file(exe,cave,128)
    if hashlib.sha256(exe[offset:offset+128]).hexdigest()!='fddb0a0be9c67098de878c70bb9318b71c6613691433016ea2d894666158c745':raise ValueError('Candidate cave differs')
    ep=to_file(exe,entry)
    if exe[ep:ep+4]!=bytes.fromhex('7c9d2378'):raise ValueError('Country instruction differs')
    # This subrange lies in the already reference-audited v20 IPC cave, after its blob.
    body=assemble('''cmpwi cr7,r4,136
    bne cr7,preserve
    li r29,49
    b resume
preserve:
    mr r29,r4
    b resume''',cave,{'resume':entry+4})
    branch=assemble('b candidate',entry,{'candidate':cave})
    if len(body)>128 or len(branch)!=4:raise ValueError('Candidate size')
    exe[offset:offset+len(body)]=body;exe[ep:ep+4]=branch;t.set_content(bytes(exe),1)
    output=t.dump_wad();check=load_library().title.Title();check.load_wad(output)
    if expected is not None and output!=expected:raise ValueError('Candidate reproduction differs')
    if {i for i in range(12) if check.get_content_by_index(i)!=original[i]}!={1}:raise ValueError('Changed unrelated content')
    h=hashlib.sha256(output).hexdigest();meta.update(revision=22,parent_revision=20,country_fallback={'from':136,'to':49,'scope':'News constructor only','signature_verified':False,'hardware_verified':False,'diagnostic_only':True},wads={'personal':{'file':'news-ko-personal.wad','sha256':h}},wad_sha256=h,changed_from_parent=[1],live_service_verified=False)
    out.mkdir();(out/'news-ko-personal.wad').write_bytes(output);(out/'build-manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PASS: diagnostic v22 built; News context country 136->49, other channel contents unchanged; not hardware verified')
if __name__=='__main__':main()

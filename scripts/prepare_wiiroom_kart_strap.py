"""Extract only the original Korean Mario Kart strap UI, without save/ticket IO."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import ChannelArchive,load_library
from kwce.votes_resources import decode_yaz0
from kwce import tpl
OUT=ROOT/'workspace/channels/wiiroom/references/kart-strap-v1'
CONFIG=ROOT/'configs/wiiroom-strap-kart-v1.lock.json'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--content',type=Path,required=True);args=ap.parse_args()
    if OUT.exists()or CONFIG.exists():raise ValueError('Numbered strap reference preserved')
    # Exact reviewed channel-content identity; the source is opened read-only.
    raw=args.content.read_bytes()
    if sha(raw)!='0c4ea3fb9678de92d08c2822eded7618589dc052fb475211ad8af118ed78bd38':raise ValueError('Reviewed Korean Mario Kart UI content required')
    source=ChannelArchive(raw).get('Boot/Strap/kr/Korean.szs');decoded=decode_yaz0(source)
    if decoded[:4]!=b'bres':raise ValueError('Expected BRRES strap archive')
    rows=[];pos=0
    while True:
        at=decoded.find(b'TEX0',pos)
        if at<0:break
        pos=at+4;size,version=struct.unpack_from('>II',decoded,at+4)
        offset,name=struct.unpack_from('>II',decoded,at+16);w,h,fmt,levels=struct.unpack_from('>HHII',decoded,at+28)
        if not(size>64 and at+size<=len(decoded)):continue
        name=decoded[at+name:].split(b'\0')[0].decode('ascii')
        if(version,w,h,fmt,levels)!=(3,608,456,4,1)or name not in('strapA_608x456','strapB_608x456'):raise ValueError('Unexpected strap TEX0')
        n=tpl.data_size(fmt,w,h)
        if offset+n>size:raise ValueError('Strap pixels out of bounds')
        head=bytearray(64);struct.pack_into('>III',head,0,0x0020af30,1,12);struct.pack_into('>II',head,12,20,0)
        struct.pack_into('>HHII',head,20,h,w,fmt,64);struct.pack_into('>II',head,36,1,1)
        body=bytes(head)+decoded[at+offset:at+offset+n];rows.append((name,body))
    if [n for n,b in rows]!=['strapA_608x456','strapB_608x456']:raise ValueError('Two original Korean images required')
    OUT.mkdir(parents=True);record=dict(title_id='00010004524d434b',content_sha256=sha(raw),ui_archive_sha256=sha(source),source_dimensions=[608,456],native_korean=True,redrawn=False,files=[])
    for i,(name,body)in enumerate(rows):
        p=OUT/f'strap-{i}.tpl';p.write_bytes(body);record['files'].append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(body),texture=name))
    CONFIG.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');print('Extracted two native Korean Mario Kart strap images; no text redraw/source writes')
if __name__=='__main__':main()

"""Photo Prints A/B diagnostic WADs for the isolated profile (create-once).

build-v4: the stock Japanese title, every content unchanged (re-serialized only;
          original Nintendo signatures kept, installs in EmuNAND as-is).
build-v5: stock + ONLY the title-local Korea-area bridge (content 1: one byte,
          KOR area code 6->0, LZ11 re-encoded to the same raw size).
No WiiLink patch, no Korean text/font/HOME/banner, no endpoint change; the
original service hosts are unreachable from the capability-0 container.
Manifests carry diagnostic=true and local_only=true (profile-only use).
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.wiiroom_formats import decompress_lz11,reencode_lz11_same_size
from kwce.photoprints_compat import patch_korean_area

def build(original,revision):
    lib=load_library();title=lib.title.Title();title.load_wad(original)
    if title.tmd.title_id!='000100014843444a':raise ValueError('Photo Prints source identity differs')
    contents=[title.get_content_by_index(i) for i in range(len(title.tmd.content_records))]
    record=dict(revision=revision,diagnostic=True,local_only=True,title_id=title.tmd.title_id,
        full_localization_complete=False,hardware_success_verified=False)
    if revision==5:
        dol,area=patch_korean_area(decompress_lz11(contents[1]))
        title.set_content(reencode_lz11_same_size(contents[1],dol),1);record['korean_area']=area
        record['purpose']='stock + Korea-area bridge only'
    else:record['purpose']='stock Japanese original, contents unchanged'
    wad=title.dump_wad();check=lib.title.Title();check.load_wad(wad)
    changed=[i for i in range(len(contents)) if check.get_content_by_index(i)!=contents[i]]
    if changed!=([1] if revision==5 else []):raise ValueError(f'Unexpected diagnostic content change {changed}')
    record.update(changed_contents=changed,wad_sha256=hashlib.sha256(wad).hexdigest(),
        original_sha256=hashlib.sha256(original).hexdigest(),identical_to_original=wad==original)
    return wad,record

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True,choices=[4,5]);ap.add_argument('--reproduce',action='store_true');args=ap.parse_args()
    base=ROOT/'workspace/channels/photoprints';out=base/f'build-v{args.revision}';expected=None
    original=(base/'originals/digicam-japan-v1024.wad').read_bytes()
    if args.reproduce:
        expected=(out/'photoprints-ko-local-test.wad').read_bytes();n=1
        while(ROOT/f'workspace/private/photoprints-reproduce-v{args.revision}-{n}').exists():n+=1
        out=ROOT/f'workspace/private/photoprints-reproduce-v{args.revision}-{n}'
    if out.exists():raise SystemExit('Existing Photo Prints diagnostic build preserved')
    wad,record=build(original,args.revision)
    out.mkdir(parents=True);(out/'photoprints-ko-local-test.wad').write_bytes(wad)
    (out/'build-manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    if expected is not None and expected!=wad:raise ValueError('Photo Prints diagnostic reproduction differs')
    print(('Reproduced byte-identically' if expected is not None else 'Built'),f'diagnostic v{args.revision} ({record["purpose"]}); sha',record['wad_sha256'][:12])
if __name__=='__main__':main()

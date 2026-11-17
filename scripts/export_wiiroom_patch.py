"""Ignored personal Room deltas with exact WAD reconstruction verification."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,sha256
from kwce.channel_patch import make_patch,apply_patch

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,choices=[v for v in range(1,52)if v not in(18,19,28,29,32,33,38,39,40,41,42,43,44,45,48,49)],default=50);args=ap.parse_args();base=ROOT/'workspace/channels/wiiroom';out=base/f'patches/v{args.revision}'
    if out.exists():raise SystemExit('Existing personal Room delta preserved')
    source=(base/'originals/wiiroom-english-wiilink-archive.wad').read_bytes();target=(base/f'build-v{args.revision}/wiiroom-ko-local-test.wad').read_bytes();meta=json.loads((base/f'build-v{args.revision}/build-manifest.json').read_text())
    if sha256(source)!=meta['source_sha256']or sha256(target)!=meta['wad_sha256']:raise ValueError('Room delta input changed')
    lib=load_library();a=lib.title.Title();b=lib.title.Title();a.load_wad(source);b.load_wad(target)
    if a.tmd.title_id!=b.tmd.title_id or b.tmd.title_id!='000100014843494a':raise ValueError('Room title differs')
    a.tmd.region=4;rows=[];out.mkdir(parents=True)
    for i in range(16):
        old=a.get_content_by_index(i);new=b.get_content_by_index(i)
        if old==new:continue
        patch=make_patch(old,new);rebuilt=apply_patch(old,patch);a.set_content(rebuilt,i);name=f'content-{i:02d}.kwcp';(out/name).write_bytes(patch);rows.append(dict(index=i,file=name,sha256=sha256(patch)))
    if a.dump_wad()!=target:raise ValueError('Room delta WAD reconstruction differs')
    (out/'manifest.json').write_text(json.dumps(dict(revision=args.revision,title_id=b.tmd.title_id,base_sha256=sha256(source),output_sha256=sha256(target),contents=rows,byte_identical_WAD_rebuild_verified=True,redistribution='private local only; contains Nintendo data',full_localization_complete=False),indent=2));print('Room private deltas:',len(rows),'; byte-identical WAD reconstruction verified')

if __name__=='__main__':main()

"""Private News deltas and exact WAD reconstruction check."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,sha256
from kwce.channel_patch import make_patch,apply_patch
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True);args=ap.parse_args()
 if not 1<=args.revision<=100:raise SystemExit('Invalid revision')
 base=ROOT/'workspace/channels/news';out=base/f'patches/v{args.revision}'
 if out.exists():raise SystemExit('Existing private News patch preserved')
 folder=base/f'build-v{args.revision}';meta=json.loads((folder/'build-manifest.json').read_text(encoding='utf-8'))
 row=meta['wads']['personal']if 'wads'in meta else dict(file='news-ko-personal-test.wad',sha256=meta['wad_sha256'])
 lib=load_library();a=lib.title.Title();b=lib.title.Title();source=(base/'originals/news-usa-wiilink-archive.wad').read_bytes();target=(folder/row['file']).read_bytes()
 if sha256(target)!=row['sha256']:raise ValueError('News target changed')
 a.load_wad(source);b.load_wad(target)
 assert a.tmd.title_id==b.tmd.title_id=='0001000248414745'and(a.tmd.region,b.tmd.region)==(1,4)
 a.tmd.region=4;rows=[];out.mkdir(parents=True)
 for i in range(12):
  old=a.get_content_by_index(i);new=b.get_content_by_index(i)
  if old==new:continue
  delta=make_patch(old,new);assert apply_patch(old,delta)==new;a.set_content(new,i);name=f'content-{i:02d}.kwcp';(out/name).write_bytes(delta);rows.append(dict(index=i,file=name,sha256=sha256(delta)))
 assert a.dump_wad()==target
 result=dict(revision=args.revision,variant='personal',title_id=b.tmd.title_id,base_sha256=sha256(source),output_sha256=sha256(target),channel_TMD_region=4,contents=rows,byte_identical_WAD_rebuild_verified=True,redistribution='private local only')
 (out/'manifest.json').write_text(json.dumps(result,indent=2));print(json.dumps(dict(revision=args.revision,private_deltas=len(rows),byte_identical=True)))
if __name__=='__main__':main()

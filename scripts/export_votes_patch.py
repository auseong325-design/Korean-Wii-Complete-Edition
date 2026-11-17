"""Private Votes deltas and exact WAD reconstruction check."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,sha256
from kwce.channel_patch import make_patch,apply_patch
def main():
 base=ROOT/'workspace/channels/votes';out=base/'patches/v10'
 if out.exists():raise SystemExit('Existing private Votes patch preserved')
 lib=load_library();a=lib.title.Title();b=lib.title.Title();source=(base/'originals/votes-usa-wiilink-archive.wad').read_bytes();target=(base/'build-v10/votes-ko-ui-test.wad').read_bytes();a.load_wad(source);b.load_wad(target)
 assert a.tmd.title_id==b.tmd.title_id=='0001000148414a45'and(a.tmd.region,b.tmd.region)==(1,4)
 a.tmd.region=4;rows=[];out.mkdir(parents=True)
 for i in range(14):
  old=a.get_content_by_index(i);new=b.get_content_by_index(i)
  if old==new:continue
  delta=make_patch(old,new);assert apply_patch(old,delta)==new;a.set_content(new,i);name=f'content-{i:02d}.kwcp';(out/name).write_bytes(delta);rows.append(dict(index=i,file=name,sha256=sha256(delta)))
 assert a.dump_wad()==target
 result=dict(revision=10,title_id=b.tmd.title_id,base_sha256=sha256(source),output_sha256=sha256(target),channel_TMD_region=4,contents=rows,byte_identical_WAD_rebuild_verified=True,redistribution='private local only')
 (out/'manifest.json').write_text(json.dumps(result,indent=2));print(json.dumps(dict(revision=10,private_deltas=len(rows),byte_identical=True)))
if __name__=='__main__':main()

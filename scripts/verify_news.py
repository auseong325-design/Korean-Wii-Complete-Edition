"""Read-only News source/contents and entire Forecast preservation check."""
import json,subprocess,sys
from audit_sd import ROOT,PRIVATE,sha256
from prepare_gc_v6 import snapshot
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.channel_validation import verify_installed_title
def main():
 if 'dolphin.exe'in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin first')
 before=json.loads((PRIVATE/'forecast-v12-before-news-manifest.json').read_text())
 if snapshot(ROOT/'workspace/sandbox/forecast-v1')!=before:raise ValueError('Forecast profile changed; do not repair automatically')
 base=ROOT/'workspace/channels/news';acq=json.loads((base/'originals/acquisition.json').read_text())
 for row in acq['files']:
  p=base/'originals'/row['alias'];st=p.stat()
  if(st.st_size,st.st_mtime_ns,sha256(p))!=(row['size'],row['mtime_ns'],row['sha256']):raise ValueError('Original News WAD changed')
 refs=json.loads((base/'references/source-lock.json').read_text())
 for row in refs['files']:
  if sha256(base/'references'/row['file'])!=row['sha256']:raise ValueError('Pinned News reference changed')
 lib=load_library();t=lib.title.Title();wad=base/'build-v1/news-ko-personal-test.wad';meta=json.loads(wad.with_name('build-manifest.json').read_text())
 if sha256(wad)!=meta['wad_sha256']:raise ValueError('News WAD differs')
 t.load_wad(wad.read_bytes());count=verify_installed_title(ROOT/'workspace/sandbox/news-v1/user/Wii',t.tmd.title_id,t.tmd.dump())
 patch=json.loads((base/'patches/v1/manifest.json').read_text())
 for row in patch['contents']:
  if sha256(base/'patches/v1'/row['file'])!=row['sha256']:raise ValueError('News patch differs')
 result=dict(passed=True,originals_preserved=len(acq['files']),installed_contents=count,forecast_v12_whole_profile_preserved=True,forecast_files=len(before),pinned_news_references=len(refs['files']),normal_exit_hex=json.loads((ROOT/'workspace/sandbox/news-v1/child-exit.json').read_text())['exit_code_hex'],articles_verified=False,live_service_verified=False)
 (PRIVATE/'news-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()

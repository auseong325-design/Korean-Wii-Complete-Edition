"""Verified local test copy inside AppContainer ACL root; no dump modification."""
import json,shutil,configparser,subprocess
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
if 'dolphin.exe' in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin')
catalog=json.loads((PRIVATE/'disc-catalog.json').read_text(encoding='utf-8'));row=next(r for r in catalog['files'] if r['name'].endswith('.iso'))
source=Path(row['path']);dest=ROOT/'workspace/sandbox/gc-v3/disc/GALJ01.iso';dest.parent.mkdir(parents=True,exist_ok=True)
if dest.exists():raise SystemExit('No overwrite')
if sha256(source)!=row['sha256']:raise SystemExit('Source differs from catalog')
with source.open('rb') as a,dest.open('xb') as b:shutil.copyfileobj(a,b,8*1024*1024)
if sha256(dest)!=row['sha256']:raise SystemExit('Staged copy hash mismatch')
cfg=ROOT/'workspace/sandbox/gc-v3/user/Config/Dolphin.ini';c=configparser.ConfigParser(strict=False);c.optionxform=str;c.read(cfg,encoding='utf-8');c['Core']['DefaultISO']=str(dest)
with cfg.open('w',encoding='utf-8') as f:c.write(f)
print(json.dumps(dict(local_disc_copy_verified=True,original_dump_unchanged=True,OS_AppContainer_required=True)))

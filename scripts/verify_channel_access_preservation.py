"""Verify immutable original profiles against the first access-work manifest."""
import json,sys
from audit_sd import ROOT,PRIVATE
from prepare_gc_v6 import snapshot

def main():
 before=json.loads((PRIVATE/'channel-access-before-v1.json').read_text())
 result={}
 for alias,rows in before.items():
  now=snapshot(ROOT/'workspace/sandbox'/alias)
  old={r['path']:r for r in rows};new={r['path']:r for r in now}
  details=dict(missing=sorted(old.keys()-new.keys()),added=sorted(new.keys()-old.keys()),changed=[p for p in old.keys()&new.keys()if old[p]!=new[p]])
  result[alias]=dict(files=len(now),unchanged=not any(details.values()),differences=details)
  print(alias,dict(files=len(now),unchanged=result[alias]['unchanged'],differences={k:len(v)for k,v in details.items()}),flush=True)
 out=PRIVATE/'channel-access-preservation-after-v1.json';out.write_text(json.dumps(result,indent=2))
 if not all(r['unchanged']for r in result.values()):raise SystemExit(1)

if __name__=='__main__':main()

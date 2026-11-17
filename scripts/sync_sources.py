"""Recreate exact public source checkouts from lock; no pull, reset, or push."""
import json, subprocess
from audit_sd import ROOT

def main():
    rows=json.loads((ROOT/'configs/sources.lock.json').read_text())
    for row in rows:
        p=ROOT/row['path']
        if not p.exists():
            subprocess.run(['git','clone','--no-checkout',row['url']+'.git',str(p)],check=True)
            subprocess.run(['git','-C',str(p),'checkout','--detach',row['commit']],check=True)
        actual=subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'],text=True).strip()
        if actual!=row['commit']:raise SystemExit('Commit mismatch; refusing reset: '+row['repository'])
        if row['repository']=='WiiLink24/WiiLink24-Patcher':
            name='WiiLink-Patcher-CLI/WiiLink Icon.ico'
            original=subprocess.check_output(['git','-C',str(p),'show','HEAD:'+name])
            if (p/name).read_bytes()==original:
                attrs=p/'.git/info/attributes';line='*.ico -filter\n'
                before=attrs.read_text() if attrs.exists() else ''
                if line not in before:attrs.write_text(before+'\n# Raw ICO blob in upstream HEAD; avoid LFS clean false positive.\n'+line)
        status=subprocess.check_output(['git','-C',str(p),'status','--porcelain','--untracked-files=no'],text=True)
        if status:raise SystemExit('Tracked upstream files changed: '+row['repository'])
        print(row['repository'],actual,'verified')

if __name__=='__main__':main()

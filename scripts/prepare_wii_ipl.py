"""Configure 43K and download pinned open tooling; do not run a menu build."""
import json, subprocess, sys
from audit_sd import ROOT, sha256

def main():
    repo=ROOT/'external/wii-ipl';cfg=json.loads((ROOT/'configs/wii-ipl-target.json').read_text())
    subprocess.run([sys.executable,'configure.py','--version',cfg['version']],cwd=repo,check=True)
    paths={'dtk':'build/tools/dtk.exe','objdiff-cli':'build/tools/objdiff-cli.exe','sjiswrap':'build/tools/sjiswrap.exe','bstool':'build/tools/bstool.exe','binutils':'build/binutils'}
    for name,path in paths.items():
        if not (repo/path).exists():subprocess.run([sys.executable,'tools/download_tool.py',name,path,'--tag',cfg['tool_tags'][name]],cwd=repo,check=True)
    inventory=[]
    for name,path in paths.items():
        p=repo/path
        for f in ([p] if p.is_file() else p.rglob('*')):
            if f.is_file():inventory.append(dict(tool=name,path=f.relative_to(ROOT).as_posix(),sha256=sha256(f)))
    lock=ROOT/'configs/wii-ipl-tools.lock.json'
    if lock.exists():
        expected=json.loads(lock.read_text())
        canonical=lambda rows:sorted((r['tool'],r['path'],r['sha256']) for r in rows)
        if canonical(inventory)!=canonical(expected):raise SystemExit('Open tool bytes differ from frozen lock; refusing lock rewrite')
    else:raise SystemExit('Missing open-tool lock: restore the reviewed lock before preparing tools')
    print('43K configured; open tooling verified. Full build blocked by missing original WAD/inputs; no build executed.')

if __name__=='__main__':main()

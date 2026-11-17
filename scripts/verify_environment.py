"""Read-only local checks. --full-sd also rehashes all original SD files.

Never displays console identifiers, original reports, keys or certificate bytes.
Returns nonzero on a failed gate; original copyrighted WAD absence is a known
Phase 0 limitation reported separately, not a reason to claim a completed build.
"""
import argparse,hashlib,json,subprocess,sys
from audit_sd import ROOT,PRIVATE,sha256

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--full-sd',action='store_true');args=ap.parse_args()
    checks=[]
    def check(name,ok):
        checks.append(dict(name=name,pass_=bool(ok)));print(('PASS' if ok else 'FAIL')+': '+name)
    docs=['reference/PROJECT_SCOPE','reference/CONSOLE_BASELINE','reference/NAND_BACKUP_AUDIT','reference/DEVELOPMENT_ENVIRONMENT','reference/DOLPHIN_VALIDATION','reference/RECOVERY_RISK','archive/SETUP_STATUS']
    check('All seven required reports',all((ROOT/'docs'/f'{x}.md').is_file() for x in docs))
    for rel in ['sd/nand.bin','sd/keys.bin','workspace/private/nand-audit.json','workspace/dolphin/baseline-user/Wii/keys.bin','external/wii-ipl','tools/devkitpro-root','.venv']:
        p=subprocess.run(['git','check-ignore','-q','--',rel],cwd=ROOT)
        check('Git excludes '+rel,p.returncode==0)
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    check('No original/derived/tool files tracked',not any(p.startswith(('sd/','workspace/','external/','tools/','.venv/')) for p in tracked))
    for row in json.loads((ROOT/'configs/sources.lock.json').read_text()):
        p=ROOT/row['path'];rev=subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'],text=True).strip()
        status=subprocess.check_output(['git','-C',str(p),'status','--porcelain','--untracked-files=no'],text=True)
        check('Pinned clean source '+row['repository'],rev==row['commit'] and not status)
    lock=json.loads((ROOT/'configs/dolphin.lock.json').read_text());exe=ROOT/'tools/dolphin-2609a/Dolphin-x64/Dolphin.exe'
    check('Pinned Dolphin executable SHA-256',sha256(exe)==lock['executable_sha256'])
    for row in json.loads((ROOT/'configs/devkit.lock.json').read_text()):
        p=ROOT/'tools/packages'/row['url'].rsplit('/',1)[1]
        check('Package SHA-256 '+row['name'],p.exists() and sha256(p)==row['sha256'])
    audit=json.loads((PRIVATE/'nand-audit.json').read_text(encoding='utf-8'))
    for row in audit['provenance']:
        check('NAND/keys working copy hash',sha256(ROOT/row['source'])==row['sha256']==sha256(ROOT/row['destination']))
    frozen=json.loads((PRIVATE/'dolphin-baseline-manifest.json').read_text());base=ROOT/'workspace/dolphin/baseline-user'
    same_files={p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file()}=={x['path'] for x in frozen}
    check('Frozen Dolphin baseline unchanged',same_files and all((base/x['path']).exists() and sha256(base/x['path'])==x['sha256'] for x in frozen))
    from launch_dolphin import validate,proxy_environment
    try:validate();proxy_environment();ok=True
    except (SystemExit,ValueError,OSError):ok=False
    check('Sanitized profile launch guard',ok)
    profile=ROOT/'workspace/dolphin/experiment-user/Wii';setting='title/00000001/00000002/data/setting.txt'
    check('KOR setting.txt preserved',sha256(profile/setting)==sha256(base/'Wii'/setting))
    build=(ROOT/'external/wii-ipl/build.ninja').read_text()
    check('wii-ipl explicitly targets 43K','configure_args = --version 43K' in build)
    for row in json.loads((ROOT/'configs/wii-ipl-tools.lock.json').read_text()):
        check('Open tooling hash '+row['tool'],sha256(ROOT/row['path'])==row['sha256'])
    if args.full_sd:
        p=subprocess.run([sys.executable,str(ROOT/'scripts/audit_sd.py'),'--verify'],cwd=ROOT)
        check('All SD files unchanged against initial baseline',p.returncode==0)
    result=dict(checks=checks,passed=all(x['pass_'] for x in checks),known_limitations=['No System Menu WAD: full wii-ipl build not run','WiiMC libogc2/portlibs not installed','No physical recovery/GC/DVD test','Phase 0 proxy alone is not OS isolation; native GC AppContainer checks are separate'])
    (PRIVATE/'environment-verification.json').write_text(json.dumps(result,indent=2))
    print('Known Phase 0 limitations: original menu WAD / WiiMC dependencies / physical recovery. Native GC isolation and execution limits are reported separately.')
    raise SystemExit(0 if result['passed'] else 1)

if __name__=='__main__':main()

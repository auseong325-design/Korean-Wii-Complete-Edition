"""Compare official GUI import with independent extraction after Dolphin exits.

Only SYSCONF is allowed to differ. Restore it from the same NAND, freeze baseline,
and refuse overwriting an existing baseline. Never launches either profile.
"""
import argparse,json,shutil,subprocess
from audit_sd import ROOT, PRIVATE, sha256

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
    running=subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True)
    if 'dolphin.exe' in running.stdout.lower():raise SystemExit('Close Dolphin before finalizing')
    baseline=ROOT/'workspace/dolphin/baseline-user';manifest=PRIVATE/'dolphin-baseline-manifest.json'
    if args.check:
        rows=json.loads(manifest.read_text());bad=[]
        if {p.relative_to(baseline).as_posix() for p in baseline.rglob('*') if p.is_file()}!={r['path'] for r in rows}:
            raise SystemExit('Baseline file set differs from frozen manifest')
        for r in rows:
            p=baseline/r['path']
            if not p.exists() or sha256(p)!=r['sha256']:bad.append(r['path'])
        if bad:raise SystemExit('Baseline differs from frozen manifest; details must be investigated locally')
        print('PASS: frozen baseline hashes',len(rows));return
    if baseline.exists():raise SystemExit('Baseline already exists; use --check. Never overwrite.')
    independent=ROOT/'workspace/extracted-system/nand-current';imp=ROOT/'workspace/dolphin/import-user'
    files=[p for p in independent.rglob('*') if p.is_file()];diff=[]
    for p in files:
        rel=p.relative_to(independent);q=imp/'Wii'/rel
        if not q.exists() or sha256(p)!=sha256(q):diff.append(rel.as_posix())
    if any(p!='shared2/sys/SYSCONF' for p in diff):raise SystemExit('Official import mismatch outside SYSCONF; do not create baseline')
    if diff:shutil.copy2(independent/'shared2/sys/SYSCONF',imp/'Wii/shared2/sys/SYSCONF')
    if any(sha256(p)!=sha256(imp/'Wii'/p.relative_to(independent)) for p in files):raise SystemExit('Final import hash mismatch')
    shutil.copytree(imp,baseline)
    rows=[dict(path=p.relative_to(baseline).as_posix(),size=p.stat().st_size,sha256=sha256(p)) for p in sorted(baseline.rglob('*')) if p.is_file()]
    manifest.write_text(json.dumps(rows,indent=2))
    (PRIVATE/'official-import-comparison.json').write_text(json.dumps(dict(files_compared=len(files),importer_exit_changed=diff,correction='Restored only SYSCONF from independently decrypted same NAND; final all files match'),indent=2))
    print('Official import verified and baseline frozen:',len(rows),'files')

if __name__=='__main__':main()

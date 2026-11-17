"""Verify public synthetic tests and local Phase 1 artifacts without game boot."""
import argparse,json,subprocess,sys
from audit_sd import ROOT,PRIVATE,sha256

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--full-sd',action='store_true');ap.add_argument('--full-disc',action='store_true');args=ap.parse_args()
    (PRIVATE/'phase1-verification.json').write_text(json.dumps(dict(passed=False,status='verification in progress')),encoding='utf-8')
    commands=[['-m','unittest','discover','-s','tests'],['scripts/test_launcher_guards.py'],['-m','kwce.build','--verify'],['scripts/finalize_import.py','--check'],['scripts/launch_dolphin.py','--profile','gc-visual-v1-user','--check']]
    if args.full_disc:commands.append(['scripts/catalog_disc.py','--verify'])
    if args.full_sd:commands.append(['scripts/audit_sd.py','--verify'])
    for command in commands:subprocess.run([sys.executable,*command],cwd=ROOT,check=True)
    refs=json.loads((ROOT/'configs/phase1-references.lock.json').read_text(encoding='utf-8'))
    for row in refs:
        base=ROOT/'external/other-tools/phase1-references'/row['repository'].split('/')[1]
        for f in row['files']:
            if sha256(base/f['path'])!=f['sha256']:raise SystemExit('Reference source hash mismatch')
    for p in ['workspace/test-assets/gamecube/GALJ01/GALJ01.bca','workspace/test-assets/gamecube/GALJ01/GALJ01-dumpinfo.txt']:
        subprocess.run(['git','check-ignore','-q',p],cwd=ROOT,check=True)
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    if any(p.startswith(('sd/','workspace/','external/','tools/','.venv/')) for p in tracked):raise SystemExit('Private files tracked')
    artifact=json.loads((ROOT/'workspace/experiments/gc-restoration-v1/build-manifest.json').read_text(encoding='utf-8'))
    result=dict(passed=True,scope='v1 artifacts and shared guards; native GC results are in gc-native-verification.json',synthetic_unit_tests=16,launcher_guard_tests=16,GUI_verified=artifact['GUI_verified'],
                GC_detection_executed=False,game_executed=False,real_console_writes=False,
                source_references_verified=True,full_sd_verified=args.full_sd,full_disc_verified=args.full_disc)
    (PRIVATE/'phase1-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':main()

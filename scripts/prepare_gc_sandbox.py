"""Compile project-only OS sandbox helpers; probe contains no console data."""
from pathlib import Path
import subprocess,shutil,os,argparse,json
from audit_sd import ROOT

def main():
    running=subprocess.run(['tasklist','/FI','IMAGENAME eq AppContainerRunner.exe','/FO','CSV','/NH'],capture_output=True,text=True)
    if 'appcontainerrunner.exe' in running.stdout.lower():raise SystemExit('Close active sandbox session before recompiling its helper')
    ap=argparse.ArgumentParser();ap.add_argument('--revision',choices=[2,3,4,5,6],type=int,default=6);args=ap.parse_args()
    runtime=ROOT/f'workspace/sandbox/gc-v{args.revision}';runtime.mkdir(parents=True,exist_ok=True)
    csc=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    # Runner lives at tools/gc-sandbox/bin; it derives this exact project root.
    bindir=ROOT/('tools/gc-sandbox/v6/bin' if args.revision==6 else 'tools/gc-sandbox/bin');bindir.mkdir(parents=True,exist_ok=True)
    source=ROOT/'scripts/AppContainerRunner.cs'
    extra=[]
    if args.revision==6:
        # Keep the legacy source/binary/manifest unchanged for v5. Generate
        # only the separately rooted v6 allowlist from the same helper.
        text=source.read_text(encoding='utf-8')
        for old,new in [('"../../.."','"../../../.."'),('new string[]{"gc-v2","gc-v3","gc-v4","gc-v5"}','new string[]{"gc-v6"}'),('root.EndsWith("gc-v5"','root.EndsWith("gc-v6"')]:
            if text.count(old)!=1:raise ValueError('Legacy helper generation guard mismatch')
            text=text.replace(old,new)
        generated=bindir/'AppContainerRunner-v6.cs';generated.write_text(text,encoding='utf-8');extra=[source,Path(__file__).resolve()];source=generated
    probe=ROOT/'scripts/NetProbe.cs';probe_extra=[]
    if args.revision==6:
        text=probe.read_text(encoding='utf-8')
        old='File.WriteAllText(args[0],report);return pass?0:2;'
        if text.count('class NetProbe {')!=1 or text.count(old)!=1:raise ValueError('Legacy probe generation guard mismatch')
        text=text.replace('class NetProbe {','partial class NetProbe {')
        text=text.replace(old,'bool fstPassed;string fst=FstAtomicProbe(folder,out fstPassed);report=report.Substring(0,report.Length-1)+",\\\"fst_atomic_probe\\\":"+fst+"}";File.WriteAllText(args[0],report);return pass&&fstPassed?0:2;')
        generated=bindir/'NetProbe-v6.cs';generated.write_text(text,encoding='utf-8');probe=generated
        probe_extra=[ROOT/'scripts/FstAtomicProbe.cs']
    for src,out,additional in [(source,bindir/'AppContainerRunner.exe',[]),(probe,runtime/'NetProbe.exe',probe_extra)]:
        subprocess.run([str(csc),'/nologo','/target:exe','/platform:x64','/out:'+str(out),str(src),*[str(p)for p in additional]],check=True,cwd=ROOT)
    from audit_sd import sha256
    manifest=dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256(p)) for p in dict.fromkeys([source,probe,ROOT/'scripts/NetProbe.cs',bindir/'AppContainerRunner.exe',*extra,*probe_extra])],probe_sha256=sha256(runtime/'NetProbe.exe'))
    (bindir/'helper-build.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    subprocess.run([str(bindir/'AppContainerRunner.exe'),str(runtime),'probe'],check=True,cwd=ROOT)

if __name__=='__main__':main()

"""Compile the v7-rooted OS sandbox helpers (same generation as v6, allowlist gc-v7).

prepare_gc_sandbox.py is itself hashed by the v6 helper manifest, so v7 lives
in this separate script and leaves the v5/v6 sources, binaries and manifests unchanged.
"""
from pathlib import Path
import subprocess,os,json
from audit_sd import ROOT,sha256

def main():
    running=subprocess.run(['tasklist','/FI','IMAGENAME eq AppContainerRunner.exe','/FO','CSV','/NH'],capture_output=True,text=True)
    if 'appcontainerrunner.exe' in running.stdout.lower():raise SystemExit('Close active sandbox session before recompiling its helper')
    runtime=ROOT/'workspace/sandbox/gc-v7'
    if not (runtime/'user').exists():raise SystemExit('Run prepare_gc_v7.py first')
    csc=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    bindir=ROOT/'tools/gc-sandbox/v7/bin';bindir.mkdir(parents=True,exist_ok=True)
    source=ROOT/'scripts/AppContainerRunner.cs';text=source.read_text(encoding='utf-8')
    for old,new in [('"../../.."','"../../../.."'),('new string[]{"gc-v2","gc-v3","gc-v4","gc-v5"}','new string[]{"gc-v7"}'),('root.EndsWith("gc-v5"','root.EndsWith("gc-v7"')]:
        if text.count(old)!=1:raise ValueError('Legacy helper generation guard mismatch')
        text=text.replace(old,new)
    runner=bindir/'AppContainerRunner-v7.cs';runner.write_text(text,encoding='utf-8')
    probe_source=ROOT/'scripts/NetProbe.cs';text=probe_source.read_text(encoding='utf-8')
    old='File.WriteAllText(args[0],report);return pass?0:2;'
    if text.count('class NetProbe {')!=1 or text.count(old)!=1:raise ValueError('Legacy probe generation guard mismatch')
    text=text.replace('class NetProbe {','partial class NetProbe {')
    text=text.replace(old,'bool fstPassed;string fst=FstAtomicProbe(folder,out fstPassed);report=report.Substring(0,report.Length-1)+",\\\"fst_atomic_probe\\\":"+fst+"}";File.WriteAllText(args[0],report);return pass&&fstPassed?0:2;')
    probe=bindir/'NetProbe-v7.cs';probe.write_text(text,encoding='utf-8');fst=ROOT/'scripts/FstAtomicProbe.cs'
    for src,out,extra in [(runner,bindir/'AppContainerRunner.exe',[]),(probe,runtime/'NetProbe.exe',[fst])]:
        subprocess.run([str(csc),'/nologo','/target:exe','/platform:x64','/out:'+str(out),str(src),*[str(p)for p in extra]],check=True,cwd=ROOT)
    files=[runner,probe,probe_source,bindir/'AppContainerRunner.exe',source,Path(__file__).resolve(),fst]
    manifest=dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256(p))for p in files],probe_sha256=sha256(runtime/'NetProbe.exe'))
    (bindir/'helper-build.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    subprocess.run([str(bindir/'AppContainerRunner.exe'),str(runtime),'probe'],check=True,cwd=ROOT)

if __name__=='__main__':main()

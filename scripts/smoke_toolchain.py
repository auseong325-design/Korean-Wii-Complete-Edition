"""Compile/link a Wii/libfat probe and convert ELF to DOL; never runs it."""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kwce.toolchain import DKP, tool
from audit_sd import ROOT, sha256

def main():
    dkp=DKP
    base=ROOT/'workspace/experiments';name='toolchain-smoke' if sys.platform == 'win32' else 'toolchain-smoke-linux'
    revision=1
    while (base/f'{name}-v{revision}').exists():revision+=1
    out=base/f'{name}-v{revision}';out.mkdir(parents=True)
    src=out/'probe.c'
    src.write_text('#include <gccore.h>\n#include <fat.h>\nint main(void) { VIDEO_Init(); return fatInitDefault() ? 0 : 1; }\n')
    cmd=[str(tool('powerpc-eabi-gcc.exe')),'-mrvl','-mcpu=750','-meabi','-mhard-float','-DGEKKO','-I'+str(dkp/'libogc/include'),'-L'+str(dkp/'libogc/lib/wii'),str(src),'-lfat','-logc','-lm','-o',str(out/'probe.elf')]
    r=subprocess.run(cmd,capture_output=True,text=True)
    (out/'build-result.json').write_text(json.dumps(dict(command=cmd,exit_code=r.returncode,output=r.stdout+r.stderr),indent=2))
    if r.returncode:raise SystemExit(r.stdout+r.stderr)
    subprocess.run([str(tool('elf2dol.exe', dkp/'tools/bin')),str(out/'probe.elf'),str(out/'probe.dol')],check=True,capture_output=True)
    result=dict(link=True,elf2dol=True,hardware_execution=False,elf_sha256=sha256(out/'probe.elf'),dol_sha256=sha256(out/'probe.dol'))
    (out/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

if __name__=='__main__':main()

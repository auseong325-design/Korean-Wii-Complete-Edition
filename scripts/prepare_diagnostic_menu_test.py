"""Build a menu/snapshot-only Dolphin variant; installation is disabled."""
import shutil,subprocess
from audit_sd import ROOT
from prepare_channel_access import stopped
from export_diagnostic_hardware import DKP

def main():
    stopped();src=ROOT/'workspace/hardware/kwce-diagnostic-sd-v2/source'
    parent=ROOT/'workspace/private';n=1
    while (parent/f'diagnostic-menu-test-v{n}').exists():n+=1
    work=parent/f'diagnostic-menu-test-v{n}';work.mkdir()
    for f in ('kwce.h','kwce_diagnostics.h','kwce_diagnostics.c','kwce_diag_builds.h'):shutil.copy2(src/f,work/f)
    s=(src/'main.c').read_text(encoding='utf-8');start=s.index('    if (!cios_ok) {\n');end=s.index('    if (load_packages()',start)
    s=s[:start]+'    cios_ok = 1; /* Dolphin test only; install/restore disabled below */\n'+s[end:]
    for action in ('install','restore'):
        needle=f'do_{action}(&pkgs[sel])'
        if s.count(needle)!=2:raise ValueError('Unexpected action sites')
        s=s.replace(needle,'say("  TEST ONLY: actions disabled.\\n")')
    (work/'main.c').write_text(s,encoding='utf-8');elf=work/'test.elf'
    cmd=[str(DKP/'devkitPPC/bin/powerpc-eabi-gcc.exe'),'-O2','-Wall','-mrvl','-mcpu=750','-meabi','-mhard-float','-DGEKKO','-I'+str(DKP/'libogc/include'),'-L'+str(DKP/'libogc/lib/wii'),str(work/'main.c'),str(work/'kwce_diagnostics.c'),'-lwiiuse','-lbte','-lfat','-logc','-lm','-o',str(elf)]
    subprocess.run(cmd,capture_output=True,check=True);dol=work/'boot.dol'
    subprocess.run([str(DKP/'tools/bin/elf2dol.exe'),str(elf),str(dol)],capture_output=True,check=True)
    target=ROOT/'workspace/sandbox/hardware-test-v1/sd-sync/apps/kwce-installer/boot.dol'
    if not target.is_file():raise ValueError('Missing test bed')
    shutil.copy2(dol,target);print('PASS: Dolphin-only snapshot tester; channel installation disabled')
if __name__=='__main__':main()

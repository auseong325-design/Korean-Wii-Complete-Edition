"""Prepare an emulator-only menu stub; install/restore are disabled at compile time."""
import shutil,subprocess,sys
from audit_sd import ROOT
from prepare_channel_access import stopped
sys.path.insert(0,str(ROOT))
from kwce.unified_hardware import source
from export_unified_hardware import DKP

def main():
    stopped();parent=ROOT/'workspace/private';n=1
    while (parent/f'unified-menu-test-v{n}').exists():n+=1
    work=parent/f'unified-menu-test-v{n}';work.mkdir()
    src=ROOT/'homebrew/kwce-installer/source/main.c';s=source(src.read_text(encoding='utf-8'))
    start=s.index('    if (!cios_ok) {\n');end=s.index('    if (load_packages()',start)
    s=s[:start]+'    cios_ok = 1; /* emulator menu-only test, no IOS dependency */\n'+s[end:]
    for action in ('install','restore'):
        needle=f'do_{action}(&pkgs[sel])'
        if s.count(needle)!=2:raise ValueError('Unexpected action sites')
        s=s.replace(needle,'say("  TEST ONLY: actions disabled.\\n")')
    (work/'main.c').write_text(s,encoding='utf-8');shutil.copy2(src.with_name('kwce.h'),work/'kwce.h')
    elf=work/'test.elf';cmd=[str(DKP/'devkitPPC/bin/powerpc-eabi-gcc.exe'),'-O2','-Wall','-mrvl','-mcpu=750','-meabi','-mhard-float','-DGEKKO','-I'+str(DKP/'libogc/include'),'-L'+str(DKP/'libogc/lib/wii'),str(work/'main.c'),'-lwiiuse','-lbte','-lfat','-logc','-lm','-o',str(elf)]
    subprocess.run(cmd,capture_output=True,check=True);dol=work/'boot.dol'
    subprocess.run([str(DKP/'tools/bin/elf2dol.exe'),str(elf),str(dol)],capture_output=True,check=True)
    target=ROOT/'workspace/sandbox/hardware-test-v1/sd-sync/apps/kwce-installer/boot.dol'
    if not target.is_file():raise ValueError('Missing emulator installer')
    shutil.copy2(dol,target)
    print('PASS: emulator-only menu stub; install/restore disabled')
if __name__=='__main__':main()

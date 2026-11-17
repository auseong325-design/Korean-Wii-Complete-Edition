"""Build a new read-only Priiloader SD/NAND comparison app."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.disc_diagnostic import sd_files
DKP=ROOT/'tools/devkitpro-root/opt/devkitpro'
FORBIDDEN=('ISFS_Write','ISFS_Delete','ISFS_CreateFile','ES_AddTitleStart','ES_AddContentStart','ES_DeleteTitle','CONF_Set','IOS_ReloadIOS')
def main():
    base=ROOT/'workspace/hardware';n=1
    while (base/f'kwce-disc-diagnostic-sd-v{n}').exists():n+=1
    out=base/f'kwce-disc-diagnostic-sd-v{n}';src=out/'source';src.mkdir(parents=True)
    shutil.copy2(ROOT/'homebrew/kwce-disc-diagnostic/source/main.c',src/'main.c')
    elf=src/'probe.elf';dol=src/'boot.dol'
    cmd=[str(DKP/'devkitPPC/bin/powerpc-eabi-gcc.exe'),'-O2','-Wall','-Wextra','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-mrvl','-mcpu=750','-meabi','-mhard-float','-DGEKKO','-I'+str(DKP/'libogc/include'),'-L'+str(DKP/'libogc/lib/wii'),str(src/'main.c'),'-lfat','-logc','-lm','-o',str(elf)]
    r=subprocess.run(cmd,capture_output=True,text=True);(src/'compile.log').write_text(r.stdout+r.stderr)
    if r.returncode or 'warning:' in r.stderr:raise ValueError('Diagnostic compiler failed or warned; see private build log')
    nm=subprocess.run([str(DKP/'devkitPPC/bin/powerpc-eabi-nm.exe'),str(elf)],capture_output=True,text=True,check=True).stdout
    if any(line.rstrip().endswith(' '+name) for line in nm.splitlines() for name in FORBIDDEN):raise ValueError('Forbidden system writer linked')
    subprocess.run([str(DKP/'tools/bin/elf2dol.exe'),str(elf),str(dol)],check=True,capture_output=True)
    app=out/'apps/kwce-disc-diagnostic';app.mkdir(parents=True);shutil.copy2(dol,app/'boot.dol')
    (app/'meta.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><app version="1"><name>KWCE Disc Diagnostic</name><coder>KWCE</coder><version>1.0</version><short_description>Read-only Priiloader comparison</short_description><long_description>Compares the Priiloader hack definitions saved on NAND with the SD file. No console identity or file content is recorded.</long_description></app>\n',encoding='utf-8')
    readme=out/'KWCE-DISC-DIAGNOSTIC-README-ko.txt';readme.write_text('KWCE 디스크 읽기 전용 진단\n\n홈브류 채널에서 KWCE Disc Diagnostic을 실행하면 SD의 Priiloader 파일과 NAND 저장본이 같은지 비교해 sd:/kwce-rc/disc-diag-번호.txt에 결과를 저장합니다. 본체 파일 원문이나 식별자는 기록하지 않습니다. 읽기 권한이 없으면 오류 번호를 기록하며, 실행 중 시스템 메뉴의 메모리 상태는 검사하지 않습니다.\n',encoding='utf-8')
    rows=[]
    for path in (app/'boot.dol',app/'meta.xml',readme):
        b=path.read_bytes();rows.append(dict(path=path.relative_to(out).as_posix(),bytes=len(b),sha256=hashlib.sha256(b).hexdigest()))
    rec=dict(kind='disc-diagnostic-v1',nand_write=False,console_identifiers=False,wad_included=False,real_console_verified=False,sd_files=rows)
    raw=(json.dumps(rec,ensure_ascii=False,indent=2)+'\n').encode();(out/'package-manifest.json').write_bytes(raw);(out/'package-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
    sd_files(out);print(f'PASS: {out.name}; private read-only comparison, Wii access unverified')
if __name__=='__main__':main()

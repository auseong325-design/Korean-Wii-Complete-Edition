"""Build read-only post-run diagnostics into the existing unified installer."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,sha256
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.unified_hardware import APP_DIRS
from kwce.unified_diagnostics import diagnostic_source,sd_files

DKP=ROOT/'tools/devkitpro-root/opt/devkitpro'
def content_hash(wad,tid):
    title=load_library().title.Title();title.load_wad(wad.read_bytes())
    if title.tmd.title_id.lower()!=tid:raise ValueError('Unexpected known channel')
    return hashlib.sha1(title.get_content_by_index(1)).digest()

def main():
    base=ROOT/'workspace/hardware';n=1
    while (base/f'kwce-diagnostic-sd-v{n}').exists():n+=1
    out=base/f'kwce-diagnostic-sd-v{n}';out.mkdir();staged=out/'source';staged.mkdir()
    src=ROOT/'homebrew/kwce-installer/source'
    (staged/'main.c').write_text(diagnostic_source((src/'main.c').read_text(encoding='utf-8')),encoding='utf-8')
    shutil.copy2(src/'kwce.h',staged/'kwce.h')
    diag=ROOT/'homebrew/kwce-diagnostics/source'
    for name in ('kwce_diagnostics.h','kwce_diagnostics.c'):shutil.copy2(diag/name,staged/name)
    inputs=[('kwce_news22_digest',ROOT/'workspace/channels/news/build-v22/news-ko-personal.wad','0001000248414745'),('kwce_news20_digest',ROOT/'workspace/channels/news/build-v20/news-ko-personal.wad','0001000248414745'),('kwce_room51_digest',base/'kwce-loading-news20-room51-v1/kwce/wiiroom/korean.wad','000100014843494a')]
    header='/* Known executable content digests; only match labels are reported. */\n'
    for name,path,tid in inputs:
        digest=content_hash(path,tid);header+=f'static const unsigned char {name}[20] = {{{",".join(str(x) for x in digest)}}};\n'
    (staged/'kwce_diag_builds.h').write_text(header,encoding='ascii')
    elf=staged/'installer.elf'
    command=[str(DKP/'devkitPPC/bin/powerpc-eabi-gcc.exe'),'-O2','-Wall','-mrvl','-mcpu=750','-meabi','-mhard-float','-DGEKKO','-I'+str(DKP/'libogc/include'),'-L'+str(DKP/'libogc/lib/wii'),str(staged/'main.c'),str(staged/'kwce_diagnostics.c'),'-lwiiuse','-lbte','-lfat','-logc','-lm','-o',str(elf)]
    r=subprocess.run(command,capture_output=True,text=True);(staged/'compile.log').write_text(r.stdout+r.stderr,encoding='utf-8')
    if r.returncode or 'warning:' in r.stderr:raise ValueError('Diagnostic compile failed/warned; see package source/compile.log')
    symbols=subprocess.run([str(DKP/'devkitPPC/bin/powerpc-eabi-nm.exe'),str(elf)],capture_output=True,text=True,check=True).stdout
    if any(' '+name in symbols for name in ('menu_available','menu_install','menu_restore','menu_state','ISFS_Write','ISFS_Delete','ISFS_CreateFile')):raise ValueError('Unexpected system/NAND writer linked')
    dol=staged/'boot.dol';subprocess.run([str(DKP/'tools/bin/elf2dol.exe'),str(elf),str(dol)],capture_output=True,check=True)
    files=[]
    for i,name in enumerate(APP_DIRS):
        folder=out/name;folder.mkdir(parents=True);shutil.copy2(dol,folder/'boot.dol')
        appname='KWCE Unified Channels' if i==0 else 'KWCE Unified Shortcut'
        (folder/'meta.xml').write_text(f'<?xml version="1.0" encoding="UTF-8"?><app version="1"><name>{appname}</name><coder>KWCE</coder><version>0.6-diag.{n}</version><short_description>Install, restore and diagnostics</short_description><long_description>Wii Remote MINUS saves a sanitized post-run snapshot. Channel-only install/restore requires cIOS249.</long_description></app>\n',encoding='utf-8')
        shutil.copy2(base/'kwce-unified-sd-v2'/name/'icon.png',folder/'icon.png')
        files.extend(folder/x for x in ('boot.dol','meta.xml','icon.png'))
    readme=out/'KWCE-DIAGNOSTIC-README-ko.txt'
    readme.write_text('KWCE 뉴스/Wii의 방 실기 진단\n\n이 도구는 채널을 자동 설치하거나 Wii 설정을 변경하지 않습니다. 홈브류 채널의 KWCE Unified Channels를 열고 리모컨 - 버튼을 누릅니다. 위/아래로 상황을 고르고 A를 누르면 SD:/kwce/diagnostics/diag-번호.txt가 생성됩니다. B는 취소입니다. 채널 설치 전에는 Before testing, 뉴스 무한 대기 뒤 다시 Wii를 켜면 After News, Wii의 방 무한 대기 뒤 다시 켜면 After Wii Room을 각각 선택하세요. 필요한 경우 대기 화면에서 Wii 전원 버튼을 길게 눌러 종료하고 다시 켭니다. 이미 생성된 보고서는 덮어쓰지 않습니다.\n\n기록: 단계, 본체 시각, IOS 번호, 지역/언어/WiiConnect24 활성 상태, 허용된 3개 채널의 설치 버전과 News r20/r22 및 Room r51 일치 여부, 해당 채널들의 WiiConnect24 예약 작업 오류·재시도 수, 뉴스 데이터 보관 파일 크기와 채널 폴더 개수. 계정·기기 식별자·MAC·주소·URL 원문·인증서·티켓·저장 데이터·뉴스 내용은 기록하지 않습니다. Wii의 방은 예약 작업이 없을 수도 있습니다.\n\n이것은 실행 후 남은 상태의 스냅샷입니다. 채널 내부 HTTP 함수의 실행 단계나 멈춘 스레드를 실시간 추적하지 않으며, 결과가 정상 또는 접근 불가여도 원인을 특정하지 못할 수 있습니다. SD 카드를 PC에 연결해 diag 텍스트 파일들을 전달해 주세요.\n',encoding='utf-8');files.append(readme)
    record=dict(kind='unified-diagnostics-v1',package=out.name,menu_writer_linked=False,channel_wads=False,read_only_nand=True,no_live_trace=True,
       sd_files=[dict(path=f.relative_to(out).as_posix(),bytes=f.stat().st_size,sha256=sha256(f)) for f in sorted(files)])
    manifest=out/'package-manifest.json';manifest.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'package-manifest.sha256').write_text(sha256(manifest)+'\n',encoding='ascii');sd_files(out)
    print(f'PASS: {out.name}, {len(files)} payload files, sanitized read-only NAND snapshots, no WAD/system writer')
if __name__=='__main__':main()

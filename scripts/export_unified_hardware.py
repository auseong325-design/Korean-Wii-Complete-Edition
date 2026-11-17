"""Build a new reviewed channel-only installer and selected official app updates."""
import argparse,json,shutil,subprocess,sys,zipfile
from pathlib import Path
from audit_sd import ROOT,sha256
sys.path.insert(0,str(ROOT))
from kwce.unified_hardware import ROWS,APP_DIRS,UPSTREAM,allowed,sd_files,source

DKP=ROOT/'tools/devkitpro-root/opt/devkitpro'
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--news-v22',action='store_true');args=ap.parse_args()
    base=ROOT/'workspace/hardware';n=1
    while (base/f'kwce-unified-sd-v{n}').exists():n+=1
    out=base/f'kwce-unified-sd-v{n}';out.mkdir()
    staged=out/'source';staged.mkdir()
    src=ROOT/'homebrew/kwce-installer/source/main.c'
    (staged/'main.c').write_text(source(src.read_text(encoding='utf-8')),encoding='utf-8')
    shutil.copy2(src.with_name('kwce.h'),staged/'kwce.h')
    elf=staged/'installer.elf'
    command=[str(DKP/'devkitPPC/bin/powerpc-eabi-gcc.exe'),'-O2','-Wall','-mrvl','-mcpu=750','-meabi','-mhard-float','-DGEKKO','-I'+str(DKP/'libogc/include'),'-L'+str(DKP/'libogc/lib/wii'),str(staged/'main.c'),'-lwiiuse','-lbte','-lfat','-logc','-lm','-o',str(elf)]
    run=subprocess.run(command,capture_output=True,text=True);(staged/'compile.log').write_text(run.stdout+run.stderr,encoding='utf-8')
    if run.returncode or 'warning:' in run.stderr:raise ValueError('Compile failed or warned; see package source/compile.log')
    symbols=subprocess.run([str(DKP/'devkitPPC/bin/powerpc-eabi-nm.exe'),str(elf)],capture_output=True,text=True,check=True).stdout
    if any(' '+name in symbols for name in ('menu_available','menu_install','menu_restore','menu_state')):raise ValueError('System Menu writer linked')
    dol=staged/'boot.dol';subprocess.run([str(DKP/'tools/bin/elf2dol.exe'),str(elf),str(dol)],capture_output=True,check=True)
    files=[]
    for index,appname in enumerate(APP_DIRS):
        app=out/appname;app.mkdir(parents=True);shutil.copy2(dol,app/'boot.dol')
        name='KWCE Unified Channels' if index==0 else 'KWCE Unified Shortcut'
        (app/'meta.xml').write_text(f'<?xml version="1.0" encoding="UTF-8"?><app version="1"><name>{name}</name><coder>KWCE</coder><version>0.5-unified.{n}</version><short_description>Channel install and restore</short_description><long_description>Use Wii Remote up/down and A. Channel titles only; cIOS 249 required.</long_description></app>\n',encoding='utf-8')
        shutil.copy2(base/'kwce-alpha-v7/apps/kwce-installer/icon.png',app/'icon.png')
        files.extend(app/x for x in ('boot.dol','meta.xml','icon.png'))
    data=out/'kwce';data.mkdir();packages=data/'packages.txt'
    packages.write_text('# id|title id|name|experimental\n'+''.join(f'{i}|{t}|{("News r22 US feed trial" if i=="news" and args.news_v22 else label)}|{(1 if i=="news" and args.news_v22 else exp)}\n' for i,t,label,exp in ROWS),encoding='ascii');files.append(packages)
    if args.news_v22:
        from kwce.hardware import hardware_wad
        folder=ROOT/'workspace/channels/news';candidate=folder/'build-v22/news-ko-personal.wad'
        metadata=json.loads((candidate.parent/'build-manifest.json').read_text(encoding='utf-8'))
        if sha256(candidate)!=metadata['wads']['personal']['sha256'] or not metadata['country_fallback']['diagnostic_only']:raise ValueError('Candidate WAD differs')
        original=folder/'originals/news-usa-wiilink-archive.wad'
        wad,checks=hardware_wad(candidate.read_bytes(),original.read_bytes())
        if checks['title_id']!='0001000248414745':raise ValueError('Unexpected candidate title')
        target=data/'news/korean.wad';target.parent.mkdir();target.write_bytes(wad);files.append(target)
    downloads=ROOT/'workspace/private/homebrew-updates-20261027'
    for archive,digest in UPSTREAM.items():
        p=downloads/archive
        if sha256(p)!=digest:raise ValueError('Official archive digest differs')
        with zipfile.ZipFile(p) as z:
            if z.testzip():raise ValueError('Archive CRC differs')
            for item in z.infolist():
                path=item.filename
                if item.is_dir() or not allowed(path) or not path.startswith(('apps/CleanRip/','apps/vbagx/','apps/not64/','apps/usbloader_gx/')):continue
                dst=out/path
                if dst.exists():raise ValueError('Duplicate update path')
                dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(z.read(item));files.append(dst)
    readme=out/'KWCE-UNIFIED-README-ko.txt'
    readme.write_text('KWCE 통합 채널 도구\n\n홈브류 채널에서 KWCE Unified Channels를 선택하세요. 방향키 위/아래로 채널을 고르고 A를 누른 후 위/아래로 설치 또는 복원을 선택하고 A로 확인합니다. B는 취소, HOME은 종료입니다. 설치/복원 전 별도의 확인이 한 번 더 나옵니다. 1과 2도 단축키로 사용할 수 있습니다. 기존 Wii Room/DVD 도구 항목도 같은 통합 도구로 연결됩니다. 기존 채널 설치 기록과 원본 WAD를 사용합니다. DVD 복원은 기존 기록에 따라 처리하며 원본 WAD가 없으면 덮어쓰지 않습니다.\n\n이 패키지는 채널을 자동 설치하지 않습니다. 뉴스 r22는 만료된 한국용 대신 미국용 영문 데이터로 수신을 시험하며, 실기 성공은 미검증입니다. Wii의 방 무한 로딩도 해결 확인되지 않았습니다. USB Loader GX, CleanRip, VisualBoyAdvance GX, Not64만 공식 배포본으로 갱신했습니다. VBA GX는 새 버전 첫 실행에서 기존 설정을 초기화할 수 있으므로 SD 백업 폴더의 settings.xml을 보관하세요. 게임과 저장 파일은 건드리지 않았습니다.\n',encoding='utf-8');files.append(readme)
    record=dict(kind='unified-homebrew-v1',package=out.name,menu_writer_linked=False,priiloader_update=False,source_sha256=sha256(staged/'main.c'),upstream_archives=UPSTREAM,sd_files=[dict(path=f.relative_to(out).as_posix(),bytes=f.stat().st_size,sha256=sha256(f)) for f in sorted(files)])
    manifest=out/'package-manifest.json';manifest.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'package-manifest.sha256').write_text(sha256(manifest)+'\n',encoding='ascii');sd_files(out)
    print(f'PASS: {out.name}, {len(files)} files, fixed eight-channel allowlist, official archive hashes, no system menu writer')
if __name__=='__main__':main()

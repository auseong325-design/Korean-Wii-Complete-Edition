"""Package only recently changed channels, with a channel-only HBC installer."""
import argparse,json,shutil,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,sha256
sys.path.insert(0,str(ROOT))
from kwce.channel_hardware import APP,DATA,README,IDS,installer_source,sd_files
from kwce.hardware import hardware_wad,fakesigned

CONFIG=ROOT/'configs/hardware-channels-v1.json'
DKP=ROOT/'tools/devkitpro-root/opt/devkitpro'
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');ap.add_argument('--package');args=ap.parse_args()
    cfg=json.loads(CONFIG.read_text(encoding='utf-8'));source=ROOT/'homebrew/kwce-installer/source/main.c'
    if sha256(source)!=cfg['installer_source_sha256']or set(r['id']for r in cfg['channels'])!=IDS:raise ValueError('Reviewed channel configuration differs')
    if args.check:
        out=ROOT/'workspace/hardware'/(args.package or 'kwce-channels-v1');record,_=sd_files(out)
        if record['config_sha256']!=sha256(CONFIG):raise ValueError('Channel configuration hash differs')
        if (out/'source/main.c').read_text(encoding='utf-8')!=installer_source(source.read_text(encoding='utf-8'),record['channels']):raise ValueError('Channel installer source differs')
        print('PASS: latest five-channel package, hashes/allowlist/source, no menu writer/Priiloader update/ISO');return
    base=ROOT/'workspace/hardware';n=1
    while(base/f'kwce-channels-v{n}').exists():n+=1
    out=base/f'kwce-channels-v{n}';out.mkdir();records=[]
    for row in cfg['channels']:
        folder=ROOT/'workspace/channels'/row['id'];wad=folder/row['korean'];original=folder/row['original']
        if sha256(wad)!=row['source_sha256']:raise ValueError('Reviewed channel WAD differs')
        korean,checks=hardware_wad(wad.read_bytes(),original.read_bytes());restore,_=fakesigned(original.read_bytes())
        if checks['title_id']!=row['title_id']:raise ValueError('Reviewed channel title differs')
        target=out/DATA/row['id'];target.mkdir(parents=True)
        (target/'korean.wad').write_bytes(korean);(target/'original.wad').write_bytes(restore)
        records.append(dict(row,hardware_checks=checks,hardware_success_verified=False))
        print('PASS:',row['id'],'build',row['build'],'channel boundary/original routing',flush=True)
    staged=out/'source';staged.mkdir();generated=installer_source(source.read_text(encoding='utf-8'),records)
    (staged/'main.c').write_text(generated,encoding='utf-8');shutil.copy2(source.with_name('kwce.h'),staged/'kwce.h')
    elf=staged/'installer.elf'
    command=[str(DKP/'devkitPPC/bin/powerpc-eabi-gcc.exe'),'-O2','-Wall','-mrvl','-mcpu=750','-meabi','-mhard-float','-DGEKKO','-I'+str(DKP/'libogc/include'),'-L'+str(DKP/'libogc/lib/wii'),str(staged/'main.c'),'-lwiiuse','-lbte','-lfat','-logc','-lm','-o',str(elf)]
    result=subprocess.run(command,capture_output=True,text=True);(staged/'compile.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode or 'warning:'in result.stderr:raise ValueError('Channel installer compile error/warning; private log retained')
    symbols=subprocess.run([str(DKP/'devkitPPC/bin/powerpc-eabi-nm.exe'),str(elf)],capture_output=True,text=True,check=True).stdout
    if any(' '+name in symbols for name in ['menu_available','menu_install','menu_restore','menu_state']):raise ValueError('System Menu writer linked')
    app=out/APP;app.mkdir(parents=True)
    subprocess.run([str(DKP/'tools/bin/elf2dol.exe'),str(elf),str(app/'boot.dol')],capture_output=True,check=True)
    (app/'meta.xml').write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<app version="1"><name>KWCE Recent Channels (v{n})</name><coder>KWCE</coder><version>0.4-channels.{n}</version>
<short_description>Five recent Korean channel updates</short_description>
<long_description>Forecast103 / News15 / WiiRoom23 / Mii25 / TVGuide8 trial. Channel titles only. Existing cIOS249 required. Per-channel install / restore. Original state/logs preserved.</long_description></app>
''',encoding='utf-8')
    shutil.copy2(base/'kwce-alpha-v7/apps/kwce-installer/icon.png',app/'icon.png')
    (out/DATA/'packages.txt').write_text('# id|title id|name|experimental\n'+''.join(f'{r["id"]}|{r["title_id"]}|{r["label"]}|{int(r["experimental"])}\n'for r in records),encoding='ascii')
    shutil.copy2(ROOT/'docs/hardware/CHANNELS-V1-README-ko.txt',out/README)
    files=[*sorted(app.iterdir()),out/DATA/'packages.txt',out/README]
    for row in records:files.extend(out/DATA/row['id']/name for name in ['korean.wad','original.wad'])
    record=dict(kind='channel-only-v1',package=out.name,config_sha256=sha256(CONFIG),channels=records,
        compile_warnings=0,menu_writer_linked=False,priiloader_update=False,iso_included=False,publish=False,
        generated_source_sha256=sha256(staged/'main.c'),sd_files=[dict(path=f.relative_to(out).as_posix(),bytes=f.stat().st_size,sha256=sha256(f))for f in files])
    manifest=out/'package-manifest.json';manifest.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'package-manifest.sha256').write_text(sha256(manifest)+'\n',encoding='ascii');sd_files(out)
    print(f'PASS: {out.name}, five channel titles, warnings0, menu writer/Priiloader update/ISO absent')
if __name__=='__main__':main()

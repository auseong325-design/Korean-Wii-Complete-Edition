"""Package a reviewed DVD player/UI for physical tests; never run on a Wii."""
import argparse,hashlib,json,re,shutil,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,sha256
sys.path.insert(0,str(ROOT))
from kwce.dvd_hardware import APP,DATA,README,TITLE,installer_source,sd_files

DKP=ROOT/'tools/devkitpro-root/opt/devkitpro'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.add_argument('--package');parser.add_argument('--build',type=int,choices=[19,20,21,24,25,26,27],default=27);args=parser.parse_args()
    revision=args.build
    if args.package:
        match=re.fullmatch(r'kwce-dvd-r(19|20|21|24|25|26|27)-v[1-9][0-9]*',args.package)
        if not match:raise ValueError('Invalid DVD package name')
        revision=int(match[1])
    elif args.check:
        packages=list((ROOT/'workspace/hardware').glob(f'kwce-dvd-r{revision}-v*'))
        args.package=max(packages,key=lambda p:int(p.name.rsplit('-v',1)[1])).name
    config_path=ROOT/f'configs/hardware-dvd-r{revision}-v1.json';cfg=json.loads(config_path.read_text(encoding='utf-8'))
    source=ROOT/'homebrew/kwce-installer/source/main.c'
    if sha256(source)!=cfg['installer_source_sha256']:raise ValueError('Reviewed installer source differs')
    wad_revision=cfg['wad_revision'];home_ui=cfg['home_ui'];banner_hook=cfg.get('dvd_banner_hook',False)
    if banner_hook:
        if banner_hook not in (10,11,12) or sha256(ROOT/f'kwce/dvd_disc_banner_hook_v{banner_hook}.py')!=cfg['dvd_hook_source_sha256']:raise ValueError('Reviewed native DVD banner hook differs')
        if banner_hook in (11,12) and sha256(ROOT/f'homebrew/kwce-disc-menu/r{banner_hook}/menu.c')!=cfg['dvd_native_source_sha256']:raise ValueError('Reviewed native DVD C source differs')
    original=ROOT/f'workspace/channels/dvd-player/wad-v{wad_revision}/dvd-player.wad'
    wm=json.loads(original.with_name('wad-manifest.json').read_text(encoding='utf-8'))
    if sha256(original)!=cfg['wad_sha256'] or wm['player_build']!=revision or wm['home_ui']!=home_ui:raise ValueError('DVD source selection differs')
    from kwce.channels import load_library
    from kwce.hardware import fakesigned
    lib=load_library();title=lib.title.Title();title.load_wad(original.read_bytes())
    if title.tmd.title_id.lower()!=TITLE or title.tmd.ios_tid.lower()!='000000010000003a' or title.tmd.access_rights!=3 or title.tmd.boot_index!=1 or len(title.tmd.content_records)!=4:raise ValueError('DVD channel privileges/content differ')
    from kwce.dvd_channel_boot import channel_boot
    dol=ROOT/f'workspace/channels/dvd-player/build-v{revision}/boot.dol';home=ROOT/f'workspace/channels/dvd-player/home-ui-v{home_ui}/home.arc'
    if title.get_content_by_index(1)!=channel_boot(dol.read_bytes())[0] or title.get_content_by_index(3)!=home.read_bytes():raise ValueError('DVD channel payload differs')
    wad,_=fakesigned(original.read_bytes());check=lib.title.Title();check.load_wad(wad)
    if any(check.get_content_by_index(i)!=title.get_content_by_index(i)for i in range(4)):raise ValueError('DVD packaging changed content')
    if args.check:
        existing=ROOT/'workspace/hardware'/args.package;record,_=sd_files(existing)
        if revision>=27:
            from kwce.priiloader_legacy import parse,apply as legacy_apply
            from kwce.dvd_disc_banner_hook_v12 import patch_dvd_banner_hook
            menu=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
            if legacy_apply(menu,parse((existing/'priiloader/kwce-hacks.ini').read_bytes()))!=patch_dvd_banner_hook(menu)[0]:raise ValueError('Legacy Priiloader byte verification differs')
        if (existing/DATA/'dvd-player/korean.wad').read_bytes()!=wad:raise ValueError('Packaged WAD differs from reviewed source')
        if (existing/'source/main.c').read_text(encoding='utf-8')!=installer_source(source.read_text(encoding='utf-8'),revision):raise ValueError('Packaged installer source differs')
        if record['config_sha256']!=sha256(config_path)or record['menu_writer_linked']or record['emulator_preview_included']or record['media_iso_included']:raise ValueError('DVD package scope differs')
        print(f'PASS: DVD-only hardware package, R{revision}/HOME{home_ui}/WAD{wad_revision}, payload hashes, no menu writer/ISO/preview')
        return
    base=ROOT/'workspace/hardware';n=1
    while(base/f'kwce-dvd-r{revision}-v{n}').exists():n+=1
    out=base/f'kwce-dvd-r{revision}-v{n}';out.mkdir()
    staged=out/'source';staged.mkdir();generated=installer_source(source.read_text(encoding='utf-8'),revision)
    (staged/'main.c').write_text(generated,encoding='utf-8');shutil.copy2(source.with_name('kwce.h'),staged/'kwce.h')
    elf=staged/'installer.elf'
    command=[str(DKP/'devkitPPC/bin/powerpc-eabi-gcc.exe'),'-O2','-Wall','-mrvl','-mcpu=750','-meabi','-mhard-float','-DGEKKO','-I'+str(DKP/'libogc/include'),'-L'+str(DKP/'libogc/lib/wii'),str(staged/'main.c'),'-lwiiuse','-lbte','-lfat','-logc','-lm','-o',str(elf)]
    built=subprocess.run(command,capture_output=True,text=True);(staged/'compile.log').write_text(built.stdout+built.stderr,encoding='utf-8')
    if built.returncode:raise ValueError('DVD installer compile failed; local log retained')
    warnings=[s for s in built.stderr.splitlines()if 'warning:'in s]
    if warnings:raise ValueError('DVD installer compiler warnings; local log retained')
    symbols=subprocess.run([str(DKP/'devkitPPC/bin/powerpc-eabi-nm.exe'),str(elf)],capture_output=True,text=True,check=True).stdout
    if any(' '+x in symbols for x in ['menu_install','menu_restore','menu_available','menu_state']):raise ValueError('Menu writer linked into DVD installer')
    app=out/APP;app.mkdir(parents=True)
    subprocess.run([str(DKP/'tools/bin/elf2dol.exe'),str(elf),str(app/'boot.dol')],check=True,capture_output=True)
    (app/'meta.xml').write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<app version="1"><name>KWCE DVD Installer (R{revision})</name><coder>KWCE</coder><version>0.3-dvd.{n}</version>
<short_description>DVD Player R{revision} install / remove</short_description>
<long_description>DVD channel only. Requires existing d2x cIOS249; player uses IOS58. Logs: sd:/kwce-dvd-test/log.txt. No System Menu resources or IOS install.</long_description></app>
''',encoding='utf-8')
    shutil.copy2(ROOT/'workspace/hardware/kwce-alpha-v7/apps/kwce-installer/icon.png',app/'icon.png')
    target=out/DATA/'dvd-player';target.mkdir(parents=True);(target/'korean.wad').write_bytes(wad)
    # The legacy experimental flag means "did not reach its main screen in
    # emulator tests". R19 has passed that check; real hardware stays unverified.
    (out/DATA/'packages.txt').write_text(f'# DVD-only physical test package\ndvd-player|{TITLE}|DVD Player R{revision}|0\n',encoding='ascii')
    shutil.copy2(ROOT/f'docs/hardware/DVD-R{revision}-README-ko.txt',out/README)
    from kwce.priiloader_hacks import hacks,ini,apply,DVD_GROUP
    from kwce.dvd_disc_hook import patch_dvd_hook
    menu=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes();entries=[e for e in hacks(menu,dvd=True,dvd_banner=banner_hook)if e['name']==DVD_GROUP]
    if banner_hook:
        from importlib import import_module
        patch_dvd_hook=import_module(f'kwce.dvd_disc_banner_hook_v{banner_hook}').patch_dvd_banner_hook
    if apply(menu,entries)!=patch_dvd_hook(menu)[0]:raise ValueError('DVD-only Priiloader simulation differs')
    from kwce.priiloader_legacy import checked_ini
    raw_hacks=checked_ini(menu,entries) if revision>=27 else ini(entries).replace('\n','\r\n').encode('ascii')
    pri=out/'priiloader';pri.mkdir();(pri/'kwce-hacks.ini').write_bytes(raw_hacks)
    paths=[*sorted(app.iterdir()),out/DATA/'packages.txt',target/'korean.wad',out/README]
    record=dict(kind=f'dvd-only-r{revision}',package=out.name,title_id=TITLE,player_build=revision,home_ui=home_ui,dvd_banner_hook=banner_hook,wad_revision=wad_revision,ios=58,css_decryption=False,config_sha256=sha256(config_path),installer_source_sha256=sha256(source),generated_source_sha256=sha256(staged/'main.c'),compile_warnings=0,menu_writer_linked=False,emulator_preview_included=False,media_iso_included=False,hardware_tested=False,publish=False,wad_sha256=hashlib.sha256(wad).hexdigest(),priiloader_sha256=sha256(pri/'kwce-hacks.ini'),sd_files=[dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=sha256(p))for p in paths])
    manifest=out/'package-manifest.json';manifest.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(out/'package-manifest.sha256').write_text(sha256(manifest)+'\n',encoding='ascii')
    sd_files(out)
    print(f'PASS: {out.name}, R{revision}/HOME{home_ui}/WAD{wad_revision}, DVD-only installer, no menu writer/ISO/preview, warnings 0')

if __name__=='__main__':main()

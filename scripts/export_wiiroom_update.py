"""Standalone Room-only SD ZIP. Never accesses a physical SD or system title."""
import argparse,hashlib,json,os,shutil,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.hardware import hardware_wad,fakesigned
from kwce.channel_hardware import installer_source

OUT=ROOT/'workspace/hardware/kwce-wiiroom-r47-v1'
ZIP=OUT.with_suffix('.zip');APP='apps/kwce-wiiroom-installer';DATA='kwce-wiiroom'
README='KWCE-WIIROOM-README-ko.txt';MANIFEST='KWCE-WIIROOM-manifest.json'
ALLOWED={f'{APP}/{n}'for n in ['boot.dol','meta.xml','icon.png']}|{f'{DATA}/packages.txt',f'{DATA}/wiiroom/korean.wad',f'{DATA}/wiiroom/original.wad',README,MANIFEST}
def sha(b):return hashlib.sha256(b).hexdigest()

def verify():
    m=json.loads((OUT/MANIFEST).read_text(encoding='utf-8'))
    if m['revision']!=47 or m['title_id']!='000100014843494a' or m['system_writer_linked'] or m['hardware_success_verified']:raise ValueError('Room package scope')
    if len(m['files'])!=7 or {r['path']for r in m['files']}!=ALLOWED-{MANIFEST}:raise ValueError('Room package allowlist')
    for r in m['files']:
        p=OUT/r['path'];b=p.read_bytes()
        if p.is_symlink()or p.is_junction()or not p.resolve().is_relative_to(OUT.resolve())or len(b)!=r['bytes']or sha(b)!=r['sha256']:raise ValueError('Room package file differs')
    with zipfile.ZipFile(ZIP)as z:
        if len(z.infolist())!=8 or set(z.namelist())!=ALLOWED or z.testzip():raise ValueError('Room ZIP entries/CRC')
        for name in ALLOWED:
            if z.read(name)!=(OUT/name).read_bytes():raise ValueError('Room ZIP roundtrip')
    return m

def sd_files(package):
    """Expose only the current verified eight-file Room payload to SD deploy."""
    package=Path(package)
    if package.name!=OUT.name or package.resolve()!=OUT.resolve():raise ValueError('Only the current reviewed Room package may be deployed')
    m=verify()
    files=[]
    for name in sorted(ALLOWED):
        p=package/name
        if p.is_symlink()or p.is_junction()or not p.resolve().is_relative_to(OUT.resolve()):raise ValueError('Indirect Room SD source refused')
        files.append((p,name))
    return m,files

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
    if args.check:verify();print('PASS: Room r47 ZIP, eight exact entries/hashes/CRC, channel-only dedicated installer');return
    if OUT.exists()or ZIP.exists():raise ValueError('Existing numbered Room package preserved')
    base=ROOT/'workspace/channels/wiiroom';meta=json.loads((base/'build-v47/build-manifest.json').read_text(encoding='utf-8'))
    data=(base/'build-v47/wiiroom-ko-local-test.wad').read_bytes();compat=meta['resource_language_compatibility']
    if meta['target']!='hardware'or sha(data)!=meta['wad_sha256']or compat.get('source_area')!=6 or not compat.get('native_nand_code_preserved')or meta['static_labels']['count']!=253 or not meta['static_labels'].get('original_runtime_buffer_capacity_preserved')or not meta['wrist_strap'].get('text_redrawn')is False or not meta.get('ui_refinement')or not meta['controller_guide'].get('grayscale_antialiasing_preserved')or not meta['controller_guide'].get('network_prompt_korean')or meta['controller_guide'].get('network_prompt_columns')!=7 or not meta['korean_home'].get('manual_prompt_fonts',{}).get('all_prompt_glyphs_verified')or len(meta['controller_guide'].get('prompt_font_overrides',[]))!=4:raise ValueError('Reviewed Room r47 required')
    wad,checks=hardware_wad(data,(base/'originals/wiiroom-english-wiilink-archive.wad').read_bytes())
    original,_=fakesigned((base/'originals/wiiroom-english-wiilink-archive.wad').read_bytes())
    if checks['title_id']!='000100014843494a'or checks['contents']!=16:raise ValueError('Room channel boundary')
    config=json.loads((ROOT/'configs/hardware-channels-v1.json').read_text(encoding='utf-8'))
    src=ROOT/'homebrew/kwce-installer/source/main.c'
    if sha(src.read_bytes())!=config['installer_source_sha256']:raise ValueError('Reviewed installer differs')
    generated=installer_source(src.read_text(encoding='utf-8'),[dict(title_id=checks['title_id'])])
    if generated.count('#define BASE "sd:/kwce"')!=1:raise ValueError('Installer base anchor')
    generated=generated.replace('#define BASE "sd:/kwce"','#define BASE "sd:/kwce-wiiroom"')
    out=OUT/'source';out.mkdir(parents=True);(out/'main.c').write_text(generated,encoding='utf-8');shutil.copy2(src.with_name('kwce.h'),out/'kwce.h')
    dkp=ROOT/'tools/devkitpro-root/opt/devkitpro';elf=out/'installer.elf'
    cmd=[str(dkp/'devkitPPC/bin/powerpc-eabi-gcc.exe'),'-O2','-Wall','-mrvl','-mcpu=750','-meabi','-mhard-float','-DGEKKO','-I'+str(dkp/'libogc/include'),'-L'+str(dkp/'libogc/lib/wii'),str(out/'main.c'),'-lwiiuse','-lbte','-lfat','-logc','-lm','-o',str(elf)]
    r=subprocess.run(cmd,capture_output=True,text=True);(out/'compile.log').write_text(r.stdout+r.stderr,encoding='utf-8')
    if r.returncode or 'warning:'in r.stderr:raise ValueError('Room installer compile error/warning')
    symbols=subprocess.run([str(dkp/'devkitPPC/bin/powerpc-eabi-nm.exe'),str(elf)],capture_output=True,text=True,check=True).stdout
    if any(' '+s in symbols for s in ['menu_available','menu_install','menu_restore','menu_state']):raise ValueError('System writer linked')
    app=OUT/APP;app.mkdir(parents=True)
    subprocess.run([str(dkp/'tools/bin/elf2dol.exe'),str(elf),str(app/'boot.dol')],capture_output=True,check=True)
    (app/'meta.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><app version="1"><name>KWCE Wii Room r47</name><coder>KWCE</coder><version>r47.1</version><short_description>Korean Wii Room channel update</short_description><long_description>Wii Room only. KOR startup compatibility and Korean resources. Existing cIOS249 required. No System Menu or IOS installation.</long_description></app>\n',encoding='utf-8')
    shutil.copy2(ROOT/'workspace/hardware/kwce-channels-v1/apps/kwce-installer/icon.png',app/'icon.png')
    folder=OUT/DATA/'wiiroom';folder.mkdir(parents=True);(folder/'korean.wad').write_bytes(wad);(folder/'original.wad').write_bytes(original)
    (OUT/DATA/'packages.txt').write_text('# id|title id|name|experimental\nwiiroom|000100014843494a|Wii Room r47 (KOR boot fix)|0\n',encoding='ascii')
    shutil.copy2(ROOT/'docs/hardware/WIIROOM-R47-README-ko.txt',OUT/README)
    files=[p for p in OUT.rglob('*')if p.is_file()and p.relative_to(OUT).as_posix()in ALLOWED]
    record=dict(kind='room-only-r47-v1',revision=47,title_id=checks['title_id'],system_writer_linked=False,compile_warnings=0,
        hardware_success_verified=False,source_sha256=sha(data),source_code_sha256=sha(generated.encode('utf-8')),hardware_checks=checks,
        files=[dict(path=p.relative_to(OUT).as_posix(),bytes=p.stat().st_size,sha256=sha(p.read_bytes()))for p in sorted(files)])
    (OUT/MANIFEST).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with zipfile.ZipFile(ZIP,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9)as z:
        for name in sorted(ALLOWED):
            info=zipfile.ZipInfo(name,(2026,10,26,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,(OUT/name).read_bytes())
    verify();print('PASS: kwce-wiiroom-r47-v1.zip, dedicated Room-only app/paths, warnings0, no SD writes')

if __name__=='__main__':main()

"""Build the alpha real-console SD package (installer app + channel WADs).

Output: workspace/hardware/kwce-alpha-vN/ (new N each run, ignored, never
published). Copy its contents to the SD card root:
  apps/kwce-installer/{boot.dol,meta.xml,icon.png}   Homebrew Channel app
  kwce/packages.txt                                  channel list for the app
  kwce/<id>/korean.wad, original.wad                 fakesigned WADs
Each Korean WAD must match its build manifest, be a channel title and carry
the same local-address references as its WiiLink original (no Dolphin-only
redirects). Nothing is sent to or run on a console by this script.
"""
import hashlib,json,shutil,subprocess,sys
from audit_sd import ROOT,sha256
sys.path.insert(0,str(ROOT))
from kwce.hardware import hardware_wad,fakesigned

DKP=ROOT/'tools/devkitpro-root/opt/devkitpro'
APP=ROOT/'homebrew/kwce-installer'

def build_dol(out):
    work=out/'_build';work.mkdir()
    cc=[str(DKP/'devkitPPC/bin/powerpc-eabi-gcc.exe'),'-O2','-Wall','-mrvl','-mcpu=750','-meabi','-mhard-float','-DGEKKO',
        '-I'+str(DKP/'libogc/include'),'-L'+str(DKP/'libogc/lib/wii'),*[str(p)for p in sorted((APP/'source').glob('*.c'))],'-lwiiuse','-lbte','-lfat','-logc','-lm','-o',str(work/'kwce.elf')]
    r=subprocess.run(cc,capture_output=True,text=True)
    if r.returncode:raise SystemExit('Compile failed:\n'+r.stdout+r.stderr)
    warnings=[l for l in (r.stdout+r.stderr).splitlines() if 'warning' in l]
    subprocess.run([str(DKP/'tools/bin/elf2dol.exe'),str(work/'kwce.elf'),str(work/'boot.dol')],check=True,capture_output=True)
    return work/'boot.dol',warnings

def icon(path):
    from kwce.channels import load_library
    load_library();from PIL import Image,ImageDraw,ImageFont
    image=Image.new('RGBA',(128,48),(24,92,160,255));draw=ImageDraw.Draw(image)
    draw.text((8,4),'KWCE',font=ImageFont.truetype('C:/Windows/Fonts/malgunbd.ttf',20),fill='white')
    draw.text((8,27),'채널 한글화 α',font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',14),fill=(210,230,250))
    image.save(path)

def main():
    config=json.loads((ROOT/'configs/hardware-package.json').read_text(encoding='utf-8'))
    base=ROOT/'workspace/hardware';base.mkdir(exist_ok=True)
    # Never reuse a number, even after older packages were removed.
    n=max([int(p.name.rsplit('-v',1)[1])for p in base.glob('kwce-alpha-v*')if p.name.rsplit('-v',1)[1].isdigit()],default=0)+1
    out=base/f'kwce-alpha-v{n}';out.mkdir()
    try:dol,warnings=build_dol(out)
    except BaseException:
        shutil.rmtree(out);raise  # a failed compile leaves no partial package number
    app=out/'apps/kwce-installer';app.mkdir(parents=True);shutil.copy2(dol,app/'boot.dol');shutil.rmtree(out/'_build')
    (app/'meta.xml').write_text(f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<app version="1">
  <name>KWCE Channel Installer</name>
  <coder>KWCE</coder>
  <version>0.1-alpha.{n}</version>
  <short_description>Korean channel install / restore (alpha)</short_description>
  <long_description>Installs the Korean channel WADs from sd:/kwce and restores the original WiiLink channels or the pre-KWCE state. Channels only; never system titles. Requires d2x cIOS 249.</long_description>
</app>
''',encoding='utf-8');icon(app/'icon.png')
    kwce=out/'kwce';kwce.mkdir();lines=['# id|title id|name|experimental (generated; do not edit)'];records=[]
    for ch in config['channels']:
        folder=ROOT/'workspace/channels'/ch['id'];korean=folder/ch['korean']
        manifest_path=korean.parent/'build-manifest.json'
        if not manifest_path.exists():manifest_path=korean.parent/'wad-manifest.json'  # KWCE's own channels (DVD player)
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        expected=manifest['wads'][ch.get('variant','personal')]['sha256']if'wads'in manifest else manifest['wad_sha256']
        if sha256(korean)!=expected:raise SystemExit(f"{ch['id']}: build WAD differs from its manifest")
        target=kwce/ch['id'];target.mkdir()
        if ch['original']:
            original=folder/ch['original']
            wad,record=hardware_wad(korean.read_bytes(),original.read_bytes())
            restore,orig_record=fakesigned(original.read_bytes())
            (target/'original.wad').write_bytes(restore);orig=dict(orig_record,sha256=hashlib.sha256(restore).hexdigest(),size=len(restore))
        else:
            # A KWCE-made channel has no WiiLink original: restore removes it (it was not there before).
            wad,record=fakesigned(korean.read_bytes());orig=None
        (target/'korean.wad').write_bytes(wad)
        lines.append(f"{ch['id']}|{record['title_id']}|{ch['name']}|{int(ch['experimental'])}")
        records.append(dict(id=ch['id'],source=ch['korean'],experimental=ch['experimental'],korean=dict(record,sha256=hashlib.sha256(wad).hexdigest(),size=len(wad)),original=orig))
        print(f"{ch['id']:<12} {record['title_id']} v{record['version']} IOS{int(record['ios'][8:],16)} korean {len(wad)//1024}KB "+(f"original {orig['size']//1024}KB" if orig else 'no original (restore = remove)'))
    (kwce/'packages.txt').write_text('\n'.join(lines)+'\n',encoding='ascii')
    # System Menu GC patch as Priiloader in-memory hacks (NAND menu untouched).
    from kwce.priiloader_hacks import hacks,ini,apply,DVD_GROUP
    from kwce.gc_native import patch_gc_native
    from kwce.dvd_disc_hook import patch_dvd_hook
    dvd=any(ch['id']=='dvd-player' for ch in config['channels'])
    menu=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes();entries=hacks(menu,dvd=dvd)
    expected_menu=patch_gc_native(menu,japanese_cards=True,japanese_comments=True)[0]
    if dvd:
        expected_menu=patch_dvd_hook(expected_menu)[0]
        if apply(menu,[e for e in entries if e['name']==DVD_GROUP])!=patch_dvd_hook(menu)[0]:raise SystemExit('DVD hack alone differs from the DVD hook')
    if apply(menu,entries)!=expected_menu:raise SystemExit('Hack simulation differs from the GC (+DVD) patch')
    pri=out/'priiloader';pri.mkdir()
    (pri/'kwce-hacks.ini').write_bytes(ini(entries).replace('\n','\r\n').encode('ascii'))
    hack_record=[dict(name=e['name'],pairs=len(e['pairs']))for e in entries]
    # System Menu GC resources (disc-channel GC visuals, save-data card icon, two-line
    # label): the Dolphin-verified resource archive, written by the app theme-style.
    # v7 adds the animated DVD disc model; the v6 resource of earlier packages may be replaced directly.
    original_res=(ROOT/'workspace/extracted-system/nand-current/title/00000001/00000002/content/0000009d.app').read_bytes()
    v6_res=(ROOT/'workspace/experiments/gc-native-v6/menu-resource.app').read_bytes()
    resource_rev=config.get('menu_resource','gc-native-v6')
    patched_res=(ROOT/'workspace/experiments'/resource_rev/'menu-resource.app').read_bytes()
    previous=[hashlib.sha1(v6_res).hexdigest()] if patched_res!=v6_res else []
    from kwce.formats import U8
    changed=sorted(f for f in U8(original_res).files if U8(original_res).get(f)!=U8(patched_res).get(f))
    if changed!=['layout/common/diskBann2.ash','layout/common/setupSel2.ash','message/kor/ipl_common.bmg']:raise SystemExit('Unexpected resource differences')
    menu_dir=kwce/'menu';menu_dir.mkdir()
    (menu_dir/'kwce-0000009d.app').write_bytes(patched_res)
    (menu_dir/'resource.txt').write_text(f"original_sha1={hashlib.sha1(original_res).hexdigest()}\npatched_sha1={hashlib.sha1(patched_res).hexdigest()}\n"
                                         +''.join(f'previous_sha1={p}\n' for p in previous),encoding='ascii')
    resource_record=dict(source=resource_rev,original_sha1=hashlib.sha1(original_res).hexdigest(),patched_sha1=hashlib.sha1(patched_res).hexdigest(),previous_sha1=previous,changed_files=changed)
    shutil.copy2(ROOT/'docs/hardware/SD-README-ko.txt',out/'KWCE-README-ko.txt')
    result=dict(package=out.name,dol_sha256=sha256(app/'boot.dol'),priiloader_hacks=hack_record,menu_resource=resource_record,system_menu_version=518,compile_warnings=warnings,channels=records,
                hardware_tested=False,publish=False,note='Personal use on the owner console only; contains console-derived fonts.')
    (out/'package-manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(f"package {out.relative_to(ROOT)}  boot.dol {result['dol_sha256'][:16]}  warnings {len(warnings)}")

if __name__=='__main__':main()

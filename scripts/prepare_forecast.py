"""Clone stopped v6; install only Forecast into a new emulator NAND."""
import configparser,json,shutil,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
from prepare_gc_v6 import snapshot
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
import launch_dolphin as launcher

def register():
    launcher.NATIVE_PROFILES['forecast-v1-user']='workspace/sandbox/forecast-v1'
    launcher.PROFILES=(*launcher.PROFILES,'forecast-v1-user')

def main():
    if 'dolphin.exe' in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin before channel clone/install')
    parent=ROOT/'workspace/sandbox/gc-v6';target=ROOT/'workspace/sandbox/forecast-v1'
    manifest=PRIVATE/'gc-v6-before-channels-manifest.json'
    if target.exists()or manifest.exists():raise SystemExit('Existing channel experiment and before manifest preserved')
    launcher.validate('gc-native-v6-user');launcher.validate_native_runtime('gc-native-v6-user')
    before=snapshot(parent);manifest.write_text(json.dumps(before,indent=2))
    for folder in ['user','Dolphin-x64','disc']:
        shutil.copytree(parent/folder,target/folder,ignore=shutil.ignore_patterns('Logs','ScreenShots','Cache','StateSaves'))
    shutil.copy2(parent/'NetProbe.exe',target/'NetProbe.exe')
    cfg=target/'user/Config/Dolphin.ini';config=configparser.ConfigParser(strict=False);config.optionxform=str;config.read(cfg,encoding='utf-8-sig')
    for section in config.sections():
        for key,value in list(config[section].items()):config[section][key]=value.replace(str(parent),str(target))
    config['Core']['OverrideRegionSettings']='True'
    with cfg.open('w',encoding='utf-8')as file:config.write(file)
    wii=target/'user/Wii';title_path=wii/'title/00010002/48414645'
    if title_path.exists()or(wii/'ticket/00010002/48414645.tik').exists():raise ValueError('Forecast already installed; refusing replacement')
    lib=load_library();title=lib.title.Title();wad=ROOT/'workspace/channels/forecast/build-v1/forecast-ko-personal-test.wad'
    title.load_wad(wad.read_bytes())
    if title.tmd.title_id!='0001000248414645':raise ValueError('Only Forecast installation authorized here')
    locale=['shared2/sys/SYSCONF','title/00000001/00000002/data/setting.txt']
    previous={name:sha256(wii/name)for name in locale}
    lib.nand.EmuNAND(wii).install_title(title)
    if any(sha256(wii/name)!=digest for name,digest in previous.items()):raise ValueError('Locale changed during channel install')
    register();launcher.scrub_download_tasks('forecast-v1-user');launcher.validate('forecast-v1-user')
    if snapshot(parent)!=before:raise ValueError('GC v6 changed during channel preparation')
    record=dict(profile='forecast-v1-user',parent_profile='gc-native-v6-user',parent_files_unchanged=len(before),installed_title=title.tmd.title_id,source_wad_sha256=sha256(wad),KOR_Korean9_Korea136_preserved=True,install_method='libWiiPy EmuNAND local installer; not Dolphin GUI importer',original_console_unchanged=True)
    (PRIVATE/'forecast-v1-preparation.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))

if __name__=='__main__':main()

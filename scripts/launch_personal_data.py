"""Launch only the pinned, isolated Korean Set Personal Data test build.

The title is hidden (00010008), so the capability-0 helper boots it directly
with Dolphin --nand_title in workspace/sandbox/personal-data-test-v1. --check
validates everything and starts nothing. Nothing here touches sd/, a real
console, WiiConnect24 registration or any service.
"""
import argparse,configparser,json,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_personal_data_test import register,feed_manifest,PROFILE,TITLE,BASE,HELPER,CHANNEL,LOCK,WAD_NAME,TEMPLATE,PD_DIR
import launch_dolphin as launcher
from kwce.channels import load_library
from kwce.channel_validation import verify_installed_title

def check():
    lock=json.loads(LOCK.read_text())
    if lock['profile']!=PROFILE or lock['title_id']!=TITLE or lock['capability_count']!=0 or lock['external_network_allowed']:raise ValueError('Personal-data scope differs')
    for row in lock['files']:
        if sha256(ROOT/row['path'])!=row['sha256']:raise ValueError('Pinned personal-data artifact differs')
    feed_manifest(BASE/'local-feed')
    for p in BASE.rglob('*'):
        if p.is_symlink()or p.is_junction():raise ValueError('Indirect personal-data path')
    launcher.validate(PROFILE);cfg=configparser.ConfigParser(strict=False);cfg.read(BASE/'user/Config/Dolphin.ini',encoding='utf-8-sig')
    if cfg['Core'].get('DefaultISO')or cfg['Core'].getboolean('EnableWiiLink'):raise ValueError('Unexpected personal-data boot settings')
    for key in['WiiSDCard','WiiSDCardEnableFolderSync','WiiSDCardAllowWrites']:
        if cfg['Core'].getboolean(key,fallback=False):raise ValueError('Personal-data SD access refused')
    for section in cfg.sections():
        for key,value in cfg[section].items():
            if(key.lower().endswith(('path','pathoverride'))or key.lower()in('nandroot','dump','load'))and value.strip():
                if not Path(value).resolve().is_relative_to((BASE/'user').resolve()):raise ValueError('Personal-data outside profile path')
    revision=json.loads((CHANNEL/'active-build.json').read_text())['revision'];wad=CHANNEL/f'build-v{revision}'/WAD_NAME
    if sha256(wad)!=lock['builds'].get(str(revision)):raise ValueError('Unapproved personal-data build')
    title=load_library().title.Title();title.load_wad(wad.read_bytes());count=verify_installed_title(BASE/'user/Wii',TITLE,title.tmd.dump())
    if not(BASE/'user/Wii/title/00000001/0000003a/content/title.tmd').is_file():raise ValueError('IOS58 missing from the profile')
    reference=TEMPLATE/'user/Wii/title/00000001'
    for name in['00000002','00000100','00000101','0000003a']:
        for p in(reference/name/'content').glob('*'):
            if p.is_file()and sha256(p)!=sha256(BASE/'user/Wii/title/00000001'/name/'content'/p.name):raise ValueError('Personal-data system contents changed')
    data=PD_DIR/'pd.dat';state='none (built-in template)'
    if data.exists():
        state='fictional fixture'if lock.get('fictional_data_installed')and sha256(data)==lock.get('fictional_pd_sha256')else'written in the test profile'
    return revision,count,state

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');ap.add_argument('--wait',action='store_true',help=argparse.SUPPRESS);args=ap.parse_args()
    stopped();register()
    if not args.check:launcher.scrub_download_tasks(PROFILE)
    revision,count,state=check()
    if args.check:
        print(f'PASS: Korean Set Personal Data build-v{revision}, {count} contents, IOS58 present, Korean locale, offline WC24, pinned runtime/helper, empty fictional fixture routes, pd.dat: {state}');return
    env=launcher.proxy_environment()
    if not args.wait:
        n=1
        while(PRIVATE/f'personal-data-controller-{n}.log').exists():n+=1
        with(PRIVATE/f'personal-data-controller-{n}.log').open('x')as log:
            process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--wait'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        print('Korean Set Personal Data isolated test controller started; PID',process.pid);return
    n=1
    while(PRIVATE/f'personal-data-run-{n}.log').exists():n+=1
    with(PRIVATE/f'personal-data-run-{n}.log').open('x')as log:
        process=subprocess.Popen([str(HELPER/'PersonalDataRunner.exe'),str(BASE),'channel',TITLE],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        code=process.wait()
    launcher.scrub_download_tasks(PROFILE)
    if code:raise SystemExit('Personal-data run ended with a helper error; private diagnostics preserved')
    print('Personal-data run stopped; local scheduled tasks normalized')
if __name__=='__main__':main()

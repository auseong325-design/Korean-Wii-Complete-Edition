"""Only a pinned mail UI DOL without registration/config-write implementation."""
import argparse,configparser,json,subprocess
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_wii_mail_preview import register,PROFILE,BASE,HELPER
import launch_dolphin as launcher

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args();stopped();register()
    lock=json.loads((ROOT/'configs/wii-mail-preview.lock.json').read_text())
    if lock['capability_count']!=0 or lock['external_registration_allowed']or lock['profile']!=PROFILE:raise ValueError('Mail preview scope differs')
    for row in lock['files']:
        if sha256(ROOT/row['path'])!=row['sha256']:raise ValueError('Mail preview artifact differs')
    for p in BASE.rglob('*'):
        if p.is_symlink()or p.is_junction():raise ValueError('Indirect preview path')
    if not args.check:launcher.scrub_download_tasks(PROFILE)
    launcher.validate(PROFILE)
    cfg=configparser.ConfigParser(strict=False);cfg.read(BASE/'user/Config/Dolphin.ini',encoding='utf-8-sig')
    if cfg['Core'].get('DefaultISO')or cfg['Core'].getboolean('EnableWiiLink'):raise ValueError('Mail preview boot differs')
    for key in ['WiiSDCard','WiiSDCardEnableFolderSync','WiiSDCardAllowWrites']:
        if cfg['Core'].getboolean(key,fallback=False):raise ValueError('Mail preview SD access refused')
    for section in cfg.sections():
        for key,value in cfg[section].items():
            if(key.lower().endswith(('path','pathoverride'))or key.lower()in('nandroot','dump','load'))and value.strip():
                from pathlib import Path
                if not Path(value).resolve().is_relative_to((BASE/'user').resolve()):raise ValueError('Outside mail preview path')
    if args.check:print('PASS: incapable Korean mail preview, pinned DOL/runtime/helper, Korean locale, sanitized WC24, no SD/external registration');return
    number=1
    while(PRIVATE/f'wii-mail-preview-run-{number}.log').exists():number+=1
    with(PRIVATE/f'wii-mail-preview-run-{number}.log').open('x')as log:
        process=subprocess.Popen([str(HELPER/'MailPreviewRunner.exe'),str(BASE),'preview'],cwd=ROOT,env=launcher.proxy_environment(),stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    print('Korean mail UI preview started in capability-zero AppContainer; helper PID',process.pid)
if __name__=='__main__':main()

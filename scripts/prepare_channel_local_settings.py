"""Copy the three non-identity offline WC24 settings into one isolated channel NAND.

Generalizes prepare_votes_local_settings.py: IPL.INC, NET.WCFG and IPL.IDL come
from the Forecast test NAND so the channel passes its 109139 standby check.
Locale, credentials and the loopback-only WC24 configuration stay unchanged.
"""
import argparse,importlib,json,subprocess
from audit_sd import ROOT,PRIVATE,sha256
import launch_dolphin as launcher
from prepare_votes_local_settings import records

PROFILES={'news':('prepare_news','news-v1-user'),'nintendo':('prepare_nintendo','nintendo-v1-user'),'mii-contest':('prepare_mii_contest','mii-contest-v1-user')}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('channel',choices=sorted(PROFILES));args=ap.parse_args()
    if 'dolphin.exe'in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin first')
    module,profile=PROFILES[args.channel];importlib.import_module(module).register();launcher.scrub_download_tasks(profile);launcher.validate(profile)
    target=launcher.user_path(profile)/'Wii/shared2/sys/SYSCONF';source=ROOT/'workspace/sandbox/forecast-v1/user/Wii/shared2/sys/SYSCONF'
    old=target.read_bytes();reference=source.read_bytes();a=records(old);b=records(reference);updated=bytearray(old)
    backup=PRIVATE/f'{args.channel}-before-local-settings.bin'
    if backup.exists():raise SystemExit('Existing settings snapshot preserved')
    for key in ['IPL.INC','NET.WCFG','IPL.IDL']:
        start,end,kind=a[key];left,right,other=b[key]
        if kind!=other or end-start!=right-left:raise ValueError('Setting type mismatch')
        updated[start:end]=reference[left:right]
    backup.write_bytes(old);target.write_bytes(bytes(updated));launcher.validate(profile)
    (PRIVATE/f'{args.channel}-local-settings.json').write_text(json.dumps(dict(changed_keys=['IPL.INC','NET.WCFG','IPL.IDL'],before=sha256(backup),after=sha256(target),registration_performed=False)))
    print(f'Prepared {profile} local settings; locale and credential guards passed')
if __name__=='__main__':main()

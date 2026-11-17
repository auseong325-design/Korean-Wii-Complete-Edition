"""Boot the real-console installer DOL in the emulator test bed (capability 0).

Only workspace/sandbox/hardware-test-v1 (prepare_hardware_test.py) is allowed.
--check validates the profile without starting Dolphin.
"""
import argparse,configparser,subprocess,sys
from audit_sd import ROOT,PRIVATE
from prepare_channel_access import stopped
import launch_dolphin as launcher

PROFILE='hardware-test-v1-user';ROOT_DIR=ROOT/'workspace/sandbox/hardware-test-v1'
HELPER=ROOT/'tools/hardware-test/v1/bin/HardwareTestRunner.exe'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
    stopped()
    launcher.NATIVE_PROFILES[PROFILE]='workspace/sandbox/hardware-test-v1'
    if PROFILE not in launcher.PROFILES:launcher.PROFILES=(*launcher.PROFILES,PROFILE)
    try:launcher.validate(PROFILE)
    except SystemExit as e:
        if str(e)!='A scheduled task must be scrubbed before launch':raise
        if args.check:print('NOTE: menu tasks would be scrubbed at launch')
        else:launcher.scrub_download_tasks(PROFILE)
    config=configparser.ConfigParser(strict=False);config.read(ROOT_DIR/'user/Config/Dolphin.ini',encoding='utf-8-sig')
    if config['Core'].getboolean('EnableWiiLink',fallback=False)or config['Core'].get('DefaultISO'):raise SystemExit('Unexpected boot/URL settings')
    dol=ROOT_DIR/'sd-sync/apps/kwce-installer/boot.dol'
    if not dol.exists()or not HELPER.exists():raise SystemExit('Run prepare_hardware_test.py --package <name> first')
    if args.check:print('PASS: hardware test bed profile, helper and installer DOL');return
    run=1
    while(PRIVATE/f'hardware-test-run-{run}.log').exists():run+=1
    launcher.archive_run_log(ROOT_DIR/'user/Logs/dolphin.log',PRIVATE/f'hardware-test-before-run-{run}-dolphin.log')
    with(PRIVATE/f'hardware-test-run-{run}.log').open('x',encoding='utf-8')as log:
        env=launcher.proxy_environment()
        p=subprocess.Popen([str(HELPER),str(ROOT_DIR),'dol'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    print('installer test started in capability-zero AppContainer; helper PID',p.pid)

if __name__=='__main__':main()

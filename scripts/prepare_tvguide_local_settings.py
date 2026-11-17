"""Only three nonidentity flags + synthetic loopback network in stopped TV NAND."""
import json,shutil
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_votes_local_settings import records
from prepare_tvguide_test import BASE,register,PROFILE
import launch_dolphin as launcher
def main():
    stopped();register();launcher.scrub_download_tasks(PROFILE);launcher.validate(PROFILE)
    source=ROOT/'workspace/sandbox/wiiroom-test-v1/user/Wii';target=BASE/'user/Wii'
    backup=PRIVATE/'tvguide-before-local-settings-v1'
    if backup.exists():raise SystemExit('TV local settings backup preserved')
    backup.mkdir();path='shared2/sys/SYSCONF';old=(target/path).read_bytes();reference=(source/path).read_bytes();a,b=records(old),records(reference);changed=bytearray(old)
    for key in ['IPL.INC','NET.WCFG','IPL.IDL']:
        x,y,kind=a[key];u,v,other=b[key]
        if(kind,y-x)!=(other,v-u):raise ValueError('TV local setting type')
        changed[x:y]=reference[u:v]
    (backup/'SYSCONF').write_bytes(old);(target/path).write_bytes(changed)
    path='shared2/sys/net/02/config.dat';shutil.copy2(target/path,backup/'network-config.dat');shutil.copy2(source/path,target/path)
    launcher.validate(PROFILE);print('Prepared TV-only synthetic local network/standby flags; Korean locale and credential guards passed')
if __name__=='__main__':main()

"""Reuse only three non-identity offline settings in the isolated Votes NAND."""
import json,subprocess
from audit_sd import ROOT,PRIVATE,sha256
from prepare_votes import register
import launch_dolphin as launcher

def records(data):
    if data[:4]!=b'SCv0':raise ValueError('SYSCONF header')
    out={}
    for i in range(int.from_bytes(data[4:6],'big')):
        at=int.from_bytes(data[6+2*i:8+2*i],'big');h=data[at];n=(h&31)+1;name=data[at+1:at+1+n].decode('ascii');start=at+1+n;kind=h>>5
        if kind==1:size=int.from_bytes(data[start:start+2],'big')+3
        elif kind==2:size=data[start]+2
        else:size={3:1,4:2,5:4,6:8,7:1}[kind]
        out[name]=(start,start+size,kind)
    return out

def main():
    if 'dolphin.exe'in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin first')
    register();launcher.validate('votes-v1-user')
    target=launcher.user_path('votes-v1-user')/'Wii/shared2/sys/SYSCONF';source=ROOT/'workspace/sandbox/forecast-v1/user/Wii/shared2/sys/SYSCONF'
    old=target.read_bytes();reference=source.read_bytes();a=records(old);b=records(reference);updated=bytearray(old)
    backup=PRIVATE/'votes-before-local-settings.bin'
    if backup.exists():raise SystemExit('Existing settings snapshot preserved')
    for key in ['IPL.INC','NET.WCFG','IPL.IDL']:
        start,end,kind=a[key];left,right,other=b[key]
        if kind!=other or end-start!=right-left:raise ValueError('Setting type mismatch')
        updated[start:end]=reference[left:right]
    backup.write_bytes(old);target.write_bytes(updated);launcher.validate('votes-v1-user')
    (PRIVATE/'votes-local-settings.json').write_text(json.dumps(dict(changed_keys=['IPL.INC','NET.WCFG','IPL.IDL'],before=sha256(backup),after=sha256(target),network_isolation_required=True,registration_performed=False)))
    print('Prepared Votes-only local settings; locale and credential guards passed')
if __name__=='__main__':main()

"""Switch only the stopped project DVD test bed between 480i/480p for regression tests."""
import argparse,json,shutil
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['interlaced','progressive','restore']);p.add_argument('--backup',type=int);a=p.parse_args()
    stopped();root=ROOT/'workspace/sandbox/dvd-test-v2';ini=root/'user/Config/Dolphin.ini';sc=root/'user/Wii/shared2/sys/SYSCONF'
    if a.mode=='restore':
        if not a.backup:raise ValueError('An explicit mode backup is required')
        saved=PRIVATE/f'dvd-output-before-{a.backup}';record=json.loads((saved/'manifest.json').read_text())
        for f,target in [('Dolphin.ini',ini),('SYSCONF',sc)]:
            if sha256(saved/f)!=record[f]:raise ValueError('Mode snapshot differs')
            shutil.copy2(saved/f,target)
        print('PASS: stopped DVD test bed original output configuration restored');return
    n=1
    while(PRIVATE/f'dvd-output-before-{n}').exists():n+=1
    saved=PRIVATE/f'dvd-output-before-{n}';saved.mkdir()
    for f,target in [('Dolphin.ini',ini),('SYSCONF',sc)]:shutil.copy2(target,saved/f)
    (saved/'manifest.json').write_text(json.dumps({f:sha256(saved/f)for f in ['Dolphin.ini','SYSCONF']}))
    data=bytearray(sc.read_bytes());changed=0
    for i in range(int.from_bytes(data[4:6],'big')):
        at=int.from_bytes(data[6+2*i:8+2*i],'big');length=(data[at]&31)+1
        if data[at+1:at+1+length]==b'IPL.PGS':data[at+1+length]=int(a.mode=='progressive');changed+=1
    if changed!=1:raise ValueError('Expected one progressive scan flag')
    sc.write_bytes(data)
    print('PASS: DVD test bed output',a.mode,'; original snapshot',n)

if __name__=='__main__':main()

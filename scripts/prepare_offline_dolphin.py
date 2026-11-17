"""Create a sanitized emulator-only profile, preserving original NAND snapshots.

Native KD HTTP bypasses Dolphin movie socket guards. Omit real keys, client
certificates, WC24 mail queues and tasks; generate valid non-registered config
whose five URLs point to loopback port 9 and a valid empty download list.
No OS firewall/network settings change. This is not a general network sandbox.
"""
from __future__ import annotations
import hashlib, json, shutil, struct, subprocess
from pathlib import Path
from audit_sd import ROOT, PRIVATE

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    r=subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True)
    if 'dolphin.exe' in r.stdout.lower():raise SystemExit('Close Dolphin before preparing profiles')
    base=ROOT/'workspace/dolphin/baseline-user'
    dest=ROOT/'workspace/dolphin/experiment-user'
    quarantine=PRIVATE/'dolphin-first-session'
    if dest.exists():
        if quarantine.exists():raise SystemExit('Quarantine already exists; refusing overwrite')
        if not dest.resolve().is_relative_to(ROOT/'workspace') or not quarantine.resolve().is_relative_to(ROOT/'workspace'):
            raise SystemExit('Path validation failed')
        shutil.move(str(dest),str(quarantine))
    for p in (ROOT/'workspace/experiments').glob('phase0-menu-settings.dtm*'):
        target=PRIVATE/'first-session-recording'/p.name
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():raise SystemExit('Existing quarantined recording')
        shutil.move(str(p),str(target))
    def ignore(path,names):
        omitted=[]
        for n in names:
            if n=='keys.bin' or n.lower().endswith('.pem') or (Path(path).name=='shared2' and n=='wc24'):
                omitted.append(n)
        return omitted
    shutil.copytree(base,dest,ignore=ignore)
    wii=dest/'Wii';wc=wii/'shared2/wc24';wc.mkdir(parents=True,exist_ok=True)
    cfg=bytearray(1024)
    struct.pack_into('>II',cfg,0,0x57634366,8)
    # Synthetic ID/generation/creation stage remain 0 (Initial, not Registered).
    email=b'@offline.invalid';cfg[24:24+len(email)]=email
    for i in range(5):
        url=f'http://127.0.0.1:9/phase0-disabled/{i}'.encode()
        off=0x9c+i*0x80;cfg[off:off+len(url)]=url
    struct.pack_into('>I',cfg,1020,sum(struct.unpack('>255I',cfg[:1020]))&0xffffffff)
    for name in ('nwc24msg.cfg','nwc24msg.cbk'):(wc/name).write_bytes(cfg)
    dl=bytearray(0xf800);struct.pack_into('>II',dl,0,0x5763446c,1)
    struct.pack_into('>H',dl,16,32);struct.pack_into('>H',dl,20,120)
    (wc/'nwc24dl.bin').write_bytes(dl)
    network=wii/'shared2/sys/net/02/config.dat'
    if network.exists():network.write_bytes(bytes(network.stat().st_size))
    # Preserve Korean language and region byte-for-byte.
    preserved=['shared2/sys/SYSCONF','title/00000001/00000002/data/setting.txt']
    if any(digest(base/'Wii'/p)!=digest(wii/p) for p in preserved):raise SystemExit('Region preservation failed')
    cfgdir=dest/'Config'
    (cfgdir/'Dolphin.ini').write_text('[Analytics]\nEnabled = False\nPermissionAsked = True\n[AutoUpdate]\nUpdateTrack =\n[Core]\nWiiSDCard = False\nWiiSDCardAllowWrites = False\nWiiSDCardEnableFolderSync = False\n[Interface]\nLanguageCode = en\nConfirmStop = False\n',encoding='utf-8')
    shutil.copy2(ROOT/'configs/Logger.ini',cfgdir/'Logger.ini')
    result=dict(profile='workspace/dolphin/experiment-user',real_keys_omitted=True,client_certificates_omitted=True,
                wc24_original_queues_and_tasks_omitted=True,wc24_creation_stage='Initial',wc24_urls='127.0.0.1:9 only',
                wifi_profiles_zeroed=True,region_and_language_preserved=True,
                warning='Profile sanitation, not an OS firewall. Do not run online channels or old savestates.',
                modified_files=[str(p.relative_to(dest)).replace('\\','/') for p in [wc/'nwc24msg.cfg',wc/'nwc24msg.cbk',wc/'nwc24dl.bin',network]])
    (PRIVATE/'offline-profile-preparation.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()

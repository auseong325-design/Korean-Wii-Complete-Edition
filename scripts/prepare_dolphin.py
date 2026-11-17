"""Pinned project-only official Dolphin setup. Does not import/boot NAND."""
import hashlib, json, shutil, subprocess, urllib.request
from audit_sd import ROOT

def main():
    lock=json.loads((ROOT/'configs/dolphin.lock.json').read_text())
    archive=ROOT/'tools/dolphin-2609a-x64.7z';exe=ROOT/'tools/dolphin-2609a/Dolphin-x64/Dolphin.exe'
    if not archive.exists():
        archive.parent.mkdir(parents=True,exist_ok=True)
        req=urllib.request.Request(lock['url'],headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req,timeout=90) as r,archive.open('wb') as f:
            while b:=r.read(1024*1024):f.write(b)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=lock['archive_sha256']:raise SystemExit('Dolphin archive hash mismatch')
    if not exe.exists():
        seven=shutil.which('7z') or r'C:\Program Files\7-Zip\7z.exe'
        subprocess.run([seven,'x',str(archive),'-o'+str(ROOT/'tools/dolphin-2609a'),'-y'],check=True,stdout=subprocess.DEVNULL)
    if hashlib.sha256(exe.read_bytes()).hexdigest()!=lock['executable_sha256']:raise SystemExit('Dolphin executable hash mismatch')
    portable=exe.parent/'portable.txt'
    if not portable.exists():portable.touch()
    user=ROOT/'workspace/dolphin/import-user/Config';user.mkdir(parents=True,exist_ok=True)
    cfg=user/'Dolphin.ini'
    if not cfg.exists():cfg.write_text('[Analytics]\nEnabled = False\nPermissionAsked = True\n[AutoUpdate]\nUpdateTrack =\n[Core]\nWiiSDCard = False\nWiiSDCardAllowWrites = False\nWiiSDCardEnableFolderSync = False\n[Interface]\nLanguageCode = en\nConfirmStop = False\n')
    print('Official Dolphin 2609a archive/executable hashes verified; import profile prepared. No NAND booted.')

if __name__=='__main__':main()

"""Hardware candidate of the Korean Set Personal Data build (not installed anywhere).

Takes build-vN's local test WAD unchanged in content (SPD has no network
service, so there are no test endpoints to restore) and fakesigns it after the
hidden-title checks in kwce/personal_data_hardware.py. Output: a new
hardware-vN folder; --reproduce rebuilds into workspace/private and compares.
hardware-v1 is preserved as a failure record only: its DOL has nothing at the
0x80003400 channel entry, so it cannot boot (Dolphin panic seen with build-v1).
Revision 2 requires the channel entry branch.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from kwce.channels import load_library
from kwce.personal_data_hardware import hardware_wad
from build_personal_data import wiilink_title,WAD_NAME,REVISIONS
CHANNEL=ROOT/'workspace/channels/personal-data'
NAME='personal-data-ko-hardware-candidate.wad'
REQUIREMENTS=[
    'IOS58 installed (TMD IOS 000000010000003a; the user console baseline lists IOS58 rev6176, docs/reference/CONSOLE_BASELINE.md)',
    'Fakesign-capable installer (Trucha-patched IOS such as the existing d2x cIOS249); TMD and ticket are fakesigned',
    'TMD access rights 0x3 kept from WiiLink: bit0 lets libpatcher disable AHBPROT-protected IOS checks on hardware',
    'Hidden title 00010008-HCCJ: no Wii Menu icon; launched by Wii no Ma / Demae / Digicam (or a NAND title launcher)']
RISKS=[
    'Replaces WiiLink SPD v512 (same title ID and version); restore = reinstall references/wiilink-patcher/spd__WiiLink_SPD.wad',
    'KWCE installer allowlist (kwce/channel_hardware.py, homebrew installer) accepts only 0001000[12] titles; this WAD needs a lead-approved installer change',
    'libpatcher IOS memory patches run only on hardware; Dolphin skips them, so this path is unverified for the Korean build',
    'Hangul names/addresses are stored as UTF-16BE like any text, but Japanese channels without Hangul glyphs may not display them',
    'pd.dat on the console is never read or exported by KWCE tools; existing data stays in /title/00010008/4843434a/data/nocopy [추정: ES keeps the data folder on reinstall]']
RISKS_V2=[
    'Channel entry: 32-byte branch at 0x80003400 from kwce/dvd_channel_boot.py (hardware-verified for the KDVD channel only); SPD boot on hardware unverified',
    'Supersedes hardware-v1, which has no code at 0x80003400 and must not be installed']

def sha256(data):return hashlib.sha256(data).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,choices=REVISIONS,default=REVISIONS[-1]);ap.add_argument('--reproduce',action='store_true');args=ap.parse_args()
    rev=args.revision;out=CHANNEL/f'hardware-v{rev}';expected=None
    if args.reproduce:
        expected=(out/NAME).read_bytes();n=1
        while(ROOT/f'workspace/private/personal-data-hardware-reproduce-v{rev}-{n}').exists():n+=1
        out=ROOT/f'workspace/private/personal-data-hardware-reproduce-v{rev}-{n}'
    elif out.exists():raise SystemExit('Existing personal-data hardware candidate preserved')
    source=CHANNEL/f'build-v{rev}';prior=json.loads((source/'build-manifest.json').read_text(encoding='utf-8'));local=(source/WAD_NAME).read_bytes()
    if sha256(local)!=prior['wad_sha256']or not prior.get('local_only')or prior['revision']!=rev:raise ValueError(f'build-v{rev} identity differs')
    wiilink,_=wiilink_title();wad,checks=hardware_wad(local,wiilink,require_channel_entry=rev>=2)
    lib=load_library();a=lib.title.Title();a.load_wad(local);b=lib.title.Title();b.load_wad(wad)
    if any(a.get_content_by_index(i)!=b.get_content_by_index(i)for i in range(2)):raise ValueError(f'Hardware contents differ from build-v{rev}')
    if expected is not None and expected!=wad:raise SystemExit('Personal-data hardware reproduction differs; original preserved')
    out.mkdir(parents=True);(out/NAME).write_bytes(wad)
    manifest=dict(revision=rev,hardware_candidate=True,installed_anywhere=False,hardware_success_verified=False,full_localization_complete=False,
        source_revision=rev,source_wad_sha256=prior['wad_sha256'],wad_sha256=sha256(wad),wad_bytes=len(wad),local_only=False,service_endpoints=0,
        hardware_checks=checks,install_requirements=REQUIREMENTS,risks=RISKS+(RISKS_V2 if rev>=2 else[]),
        public_WAD_distribution=False,license='GPL-3.0 fork of WiiLink24/set-personal-data@'+prior['upstream_commit'][:12]+'; personal use only')
    manifest[f'content_identical_to_build_v{rev}']=[0,1]
    if rev>=2:manifest['supersedes']='hardware-v1 (no DOL section at the 0x80003400 channel entry; cannot boot)'
    (out/'build-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    entry='channel entry checked'if rev>=2 else'NO channel entry (preserved failure record)'
    print(f'PASS: personal-data hardware-v{rev} fakesigned candidate, contents = build-v{rev}, 0 local addresses, {entry}; '+('byte-identical reproduction'if expected else'not installed'))
if __name__=='__main__':main()

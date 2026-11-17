"""Numbered own TV Guide fixtures, activated only in the stopped local test bed."""
import argparse,json,shutil
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_tvguide_test import BASE,PROFILE,register
import launch_dolphin as launcher
from kwce.tvguide_fixtures import compressed_header,encrypted_header

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True);args=ap.parse_args();stopped();register()
    if args.revision not in(2,3,4,5,6):raise SystemExit('Only diagnostic fixtures v2 to v6 are defined')
    out=ROOT/f'workspace/channels/tvguide/local-feed-v{args.revision}';backup=PRIVATE/f'tvguide-before-feed-v{args.revision}'
    if out.exists()or backup.exists():raise SystemExit('Numbered TV fixture preserved')
    out.mkdir()
    if args.revision!=6:
        payload=compressed_header()if args.revision==2 else encrypted_header((BASE/'user/Wii/title/00010001/48424e4a/data/wc24pubk.mod').read_bytes(),schema=args.revision-2)
        (out/'header.bin').write_bytes(payload)
    (out/'routes.tsv').write_text(''if args.revision==6 else'GET /header.bin\theader.bin\n',encoding='ascii')
    manifest=dict(revision=args.revision,local_only=True,synthetic=True,header_diagnostic_only=True,files=[dict(path=p.name,sha256=sha256(p))for p in sorted(out.iterdir())])
    if args.revision==6:manifest['expected_error']=117404
    (out/'fixture-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    shutil.copytree(BASE/'local-feed',backup);lock=ROOT/'configs/tvguide-runtime.lock.json';snapshot=ROOT/f'configs/tvguide-runtime-before-feed-v{args.revision}.lock.json'
    if snapshot.exists():raise SystemExit('TV runtime snapshot preserved')
    shutil.copyfile(lock,snapshot)
    for p in out.iterdir():shutil.copyfile(p,BASE/'local-feed'/p.name)
    if args.revision==6:
        obsolete=BASE/'local-feed/header.bin'
        if obsolete.exists():obsolete.unlink()  # The previous fixture is in the numbered backup and source set.
    data=json.loads(lock.read_text());next(r for r in data['files']if r['path'].endswith('local-feed/fixture-manifest.json'))['sha256']=sha256(BASE/'local-feed/fixture-manifest.json');lock.write_text(json.dumps(data,indent=2))
    launcher.scrub_download_tasks(PROFILE);print('Activated synthetic TV header diagnostic fixture',args.revision)
if __name__=='__main__':main()

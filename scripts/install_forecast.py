"""Update only the allowed title in the stopped throwaway channel profile."""
import argparse,json,shutil,subprocess,sys
from audit_sd import ROOT,PRIVATE,sha256
from prepare_forecast import register
from forecast_profile import validate_channel,scrub_channel
import launch_dolphin as launcher
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True);ap.add_argument('--manual-capture',action='store_true',help='update only the separate historical 4:3 profile');ap.add_argument('--review',action='store_true',help='update only the separate review profile');ap.add_argument('--current',action='store_true');ap.add_argument('--snapshot-tag',default='',help='unique private backup suffix for restoring a previously tested build');args=ap.parse_args()
    if args.snapshot_tag and not __import__('re').fullmatch(r'[a-z0-9-]{1,48}',args.snapshot_tag):raise SystemExit('Invalid backup alias')
    if sum((args.review,args.manual_capture,args.current))>1:raise SystemExit('Choose one isolated profile')
    if not any((args.review,args.manual_capture,args.current))and(ROOT/'workspace/sandbox/forecast-v2/current-profile.json').exists():raise SystemExit('Legacy v22 profile is preserved; select --current')
    if not 1<=args.revision<=1000:raise SystemExit('Invalid revision')
    if 'dolphin.exe' in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin before channel update')
    register()
    if args.current:
        launcher.NATIVE_PROFILES['forecast-v1-user']='workspace/sandbox/forecast-v2'
        meta=json.loads((ROOT/launcher.NATIVE_PROFILES['forecast-v1-user']/'current-profile.json').read_text())
        if meta.get('purpose')!='localized-forecast-current-cache':raise SystemExit('Unexpected current profile')
    if args.review:
        launcher.NATIVE_PROFILES['forecast-v1-user']='workspace/sandbox/forecast-review-v1'
        review=json.loads((ROOT/launcher.NATIVE_PROFILES['forecast-v1-user']/'review-profile.json').read_text())
        if review.get('purpose')!='isolated-local-weather-review':raise SystemExit('Unexpected review profile')
    if args.manual_capture:
        launcher.NATIVE_PROFILES['forecast-v1-user']='workspace/sandbox/forecast-manual-v1'
        capture=json.loads((ROOT/launcher.NATIVE_PROFILES['forecast-v1-user']/'capture-profile.json').read_text())
        if capture.get('purpose')!='historical-4:3-manual-capture'or capture.get('real_time_weather')is not False:raise SystemExit('Unexpected capture profile')
    user=launcher.user_path('forecast-v1-user');wii=user/'Wii'
    for p in user.parent.rglob('*'):
        if p.is_symlink()or p.is_junction():raise SystemExit('Indirect channel profile refused')
    target=(wii/'title/00010002/48414645').resolve()
    approved=ROOT/('workspace/sandbox/forecast-v2/user/Wii'if args.current else'workspace/sandbox/forecast-review-v1/user/Wii'if args.review else'workspace/sandbox/forecast-manual-v1/user/Wii'if args.manual_capture else'workspace/sandbox/forecast-v1/user/Wii')
    if not target.is_relative_to(approved.resolve())or target.is_symlink()or target.is_junction():raise SystemExit('Unsafe channel target')
    backup=PRIVATE/f'forecast-{"current-"if args.current else"review-"if args.review else"manual-"if args.manual_capture else""}before-install-v{args.revision}'
    if args.snapshot_tag:backup=backup.with_name(backup.name+'-'+args.snapshot_tag)
    if backup.exists():raise SystemExit('Existing update snapshot preserved')
    shutil.copytree(target,backup)
    lib=load_library();title=lib.title.Title();wad=ROOT/f'workspace/channels/forecast/build-v{args.revision}/forecast-ko-personal-test.wad'
    meta=json.loads(wad.with_name('build-manifest.json').read_text(encoding='utf-8'))
    if sha256(wad)!=meta['wad_sha256']:raise ValueError('Build hash mismatch')
    title.load_wad(wad.read_bytes())
    if title.tmd.title_id!='0001000248414645':raise ValueError('Refusing other title')
    lib.nand.EmuNAND(wii).install_title(title)
    scrub_channel();validate_channel()
    active=user.parent/'active-build.json'if args.manual_capture or args.review or args.current else ROOT/'workspace/channels/forecast/active-build.json'
    active.write_text(json.dumps(dict(revision=args.revision)))
    print(json.dumps(dict(installed=True,profile=user.parent.name,revision=args.revision,wad_sha256=sha256(wad))))

if __name__=='__main__':main()

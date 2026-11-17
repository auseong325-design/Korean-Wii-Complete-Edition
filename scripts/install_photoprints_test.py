"""Install a numbered Photo Prints build and/or the Korean SPD into the test profile.

  --revision N        install build-vN (Korean local or A/B diagnostic) and make it active
  --personal-data     install the pinned Korean SPD title 00010008-4843434a (keeps pd.dat)
  --fictional-data    SPD + fictional Korean pd.dat (kwce/personal_data_format, Dolphin default ID)
  --clear-data        SPD + remove pd.dat
Does not touch the shared catalog (workspace/channels/photoprints/catalog-entry.json
carries the row). Prior install snapshots and the lock's build map are preserved.
"""
import argparse,json,sys
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_photoprints_test import register,PROFILE,BASE
from prepare_gc_v6 import snapshot
import launch_dolphin as launcher
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce import photoprints_personal_data as pdata

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int)
    g=ap.add_mutually_exclusive_group()
    g.add_argument('--personal-data',action='store_true');g.add_argument('--fictional-data',action='store_true');g.add_argument('--clear-data',action='store_true')
    args=ap.parse_args()
    data='fictional' if args.fictional_data else 'clear' if args.clear_data else 'keep' if args.personal_data else None
    if args.revision is None and data is None:ap.error('give --revision and/or a personal-data option')
    stopped();register()
    n=1
    while(PRIVATE/f'photoprints-before-install-{n}.json').exists():n+=1
    (PRIVATE/f'photoprints-before-install-{n}.json').write_text(json.dumps(snapshot(BASE/'user'),indent=2))
    path=ROOT/'configs/photoprints-runtime.lock.json';lock=json.loads(path.read_text())
    if args.revision is not None:
        wad=ROOT/f'workspace/channels/photoprints/build-v{args.revision}/photoprints-ko-local-test.wad'
        meta=json.loads(wad.with_name('build-manifest.json').read_text(encoding='utf-8'))
        # Korean local builds carry local_only; A/B diagnostics (v4 stock, v5 stock+area bridge) carry diagnostic+local_only.
        if not(meta.get('local_only') or meta.get('diagnostic')) or sha256(wad)!=meta['wad_sha256']:raise ValueError('Photo Prints build identity/scope')
        if meta.get('diagnostic'):print('Diagnostic build:',meta.get('purpose'))
        lib=load_library();title=lib.title.Title();title.load_wad(wad.read_bytes());lib.nand.EmuNAND(BASE/'user/Wii').install_title(title)
        (ROOT/'workspace/channels/photoprints/active-build.json').write_text(json.dumps(dict(revision=args.revision,wad_sha256=meta['wad_sha256']),indent=2))
        lock['builds'][str(args.revision)]=meta['wad_sha256']
    if data is not None:
        lock['personal_data']=pdata.install(BASE/'user/Wii',data)
    launcher.scrub_download_tasks(PROFILE);launcher.validate(PROFILE)   # refuses keys.bin
    path.write_text(json.dumps(lock,indent=2))
    state=('' if data is None else f"; Korean SPD installed, pd.dat {'fictional' if lock['personal_data']['pd_installed'] else 'absent'}")
    print('Photo Prints profile updated'+(f': build {args.revision} active' if args.revision is not None else '')+state+'; lock updated (shared catalog untouched)')
if __name__=='__main__':main()

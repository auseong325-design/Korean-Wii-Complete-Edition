"""Install a numbered Korean Set Personal Data build into the isolated test profile.

--fictional-data writes local-feed-v1's fictional Korean pd.dat, encrypted for
Dolphin 2609a's public DEFAULT_DEVICE_ID; launch_dolphin.validate() first
refuses any profile holding keys.bin, so no real console ID can apply.
--clear-data removes the profile's pd.dat (SPD then starts from its template).
Previous installation state is snapshotted; the shared catalog is not edited.
"""
import argparse,json,sys
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_gc_v6 import snapshot
from prepare_personal_data_test import register,build_wad,feed_manifest,PROFILE,BASE,CHANNEL,LOCK,PD_DIR
import launch_dolphin as launcher
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce import personal_data_format as fmt

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True)
    data=ap.add_mutually_exclusive_group();data.add_argument('--fictional-data',action='store_true');data.add_argument('--clear-data',action='store_true')
    args=ap.parse_args();stopped();register()
    wad,meta=build_wad(args.revision);n=1
    while(PRIVATE/f'personal-data-before-install-{n}.json').exists():n+=1
    (PRIVATE/f'personal-data-before-install-{n}.json').write_text(json.dumps(snapshot(BASE/'user'),indent=2))
    lib=load_library();title=lib.title.Title();title.load_wad(wad.read_bytes());lib.nand.EmuNAND(BASE/'user/Wii').install_title(title)
    launcher.scrub_download_tasks(PROFILE);launcher.validate(PROFILE)
    lock=json.loads(LOCK.read_text());target=PD_DIR/'pd.dat'
    if args.fictional_data:
        feed_manifest(BASE/'local-feed');plain=(BASE/'local-feed/fictional-pd-plain.bin').read_bytes();fmt.check(plain)
        PD_DIR.mkdir(parents=True,exist_ok=True);target.write_bytes(fmt.encrypt(plain,fmt.DOLPHIN_DEFAULT_DEVICE_ID))
        lock['fictional_data_installed']=True;lock['fictional_pd_sha256']=sha256(target)
    elif args.clear_data:
        if target.exists():target.unlink()
        lock['fictional_data_installed']=False;lock.pop('fictional_pd_sha256',None)
    lock['builds'][str(args.revision)]=meta['wad_sha256'];LOCK.write_text(json.dumps(lock,indent=2)+'\n')
    (CHANNEL/'active-build.json').write_text(json.dumps(dict(revision=args.revision,wad_sha256=meta['wad_sha256']),indent=2)+'\n')
    state='fictional pd.dat installed'if args.fictional_data else'pd.dat removed'if args.clear_data else'pd.dat unchanged'
    print('Installed isolated Korean Set Personal Data build',args.revision,';',state,'; runtime lock updated')
if __name__=='__main__':main()

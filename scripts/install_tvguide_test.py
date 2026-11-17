"""Install a new numbered TV test build; preserve previous installation manifest."""
import argparse,json
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_tvguide_test import register,PROFILE,BASE
from prepare_gc_v6 import snapshot
import launch_dolphin as launcher
from kwce.channels import load_library
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--revision',type=int,required=True);args=parser.parse_args();stopped();register()
    wad=ROOT/f'workspace/channels/tvguide/build-v{args.revision}/tvguide-ko-local-test.wad';meta=json.loads(wad.with_name('build-manifest.json').read_text(encoding='utf-8'))
    if not meta.get('local_only')or sha256(wad)!=meta['wad_sha256']:raise ValueError('TV build identity/scope')
    number=1
    while(PRIVATE/f'tvguide-before-install-{number}.json').exists():number+=1
    (PRIVATE/f'tvguide-before-install-{number}.json').write_text(json.dumps(snapshot(BASE/'user'),indent=2))
    lib=load_library();title=lib.title.Title();title.load_wad(wad.read_bytes());lib.nand.EmuNAND(BASE/'user/Wii').install_title(title);launcher.scrub_download_tasks(PROFILE)
    (ROOT/'workspace/channels/tvguide/active-build.json').write_text(json.dumps(dict(revision=args.revision,wad_sha256=meta['wad_sha256']),indent=2))
    path=ROOT/'configs/tvguide-runtime.lock.json';data=json.loads(path.read_text());data['builds'][str(args.revision)]=meta['wad_sha256'];path.write_text(json.dumps(data,indent=2))
    path=ROOT/'configs/channels.catalog.json';data=json.loads(path.read_text(encoding='utf-8'));row=next(r for r in data['channels']if r['id']=='tvguide');next(r for r in row['installs']if r['role']=='active')['artifact']=f'build-v{args.revision}';path.write_text(json.dumps(data,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print('Installed isolated TV Guide build',args.revision,'; catalog/lock updated')
if __name__=='__main__':main()

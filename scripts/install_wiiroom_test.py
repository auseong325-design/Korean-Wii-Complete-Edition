"""Switch only the stopped Wii Room test title; preserve build WADs and snapshots."""
import argparse,json,sys
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_wiiroom_test import register,PROFILE
from prepare_gc_v6 import snapshot
import launch_dolphin as launcher
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--diagnostic-original',action='store_true');ap.add_argument('--revision',type=int,choices=[*range(1,9),10,12,14,16,20,22,24,26,30,34,36,46,50,54,61],default=50);args=ap.parse_args();stopped();register();user=launcher.user_path(PROFILE)
    variant='diagnostic-original'if args.diagnostic_original else f'korean-v{args.revision}'
    wad=ROOT/('workspace/channels/wiiroom/originals/wiiroom-english-wiilink-archive.wad'if args.diagnostic_original else f'workspace/channels/wiiroom/build-v{args.revision}/wiiroom-ko-local-test.wad')
    expected='533ac68bc2b7267e52a18c48acf423c3f86c1e97641962d62a1991c630457d8c'if args.diagnostic_original else json.loads(wad.with_name('build-manifest.json').read_text())['wad_sha256']
    if sha256(wad)!=expected:raise ValueError('Wii Room input differs')
    index=1
    while(PRIVATE/f'wiiroom-before-install-{index}.json').exists():index+=1
    (PRIVATE/f'wiiroom-before-install-{index}.json').write_text(json.dumps(snapshot(user),indent=2))
    lib=load_library();title=lib.title.Title();title.load_wad(wad.read_bytes());lib.nand.EmuNAND(user/'Wii').install_title(title)
    (ROOT/'workspace/channels/wiiroom/active-build.json').write_text(json.dumps(dict(variant=variant,revision=0 if args.diagnostic_original else args.revision,wad_sha256=expected),indent=2));print('Installed isolated Wii Room variant:',variant)

if __name__=='__main__':main()

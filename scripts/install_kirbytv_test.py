"""Install a new numbered Kirby TV build into the sandbox; preserve prior manifests."""
import argparse
import json
from audit_sd import ROOT, PRIVATE, sha256
from prepare_channel_access import stopped
from prepare_kirbytv_test import register, PROFILE, BASE
from prepare_gc_v6 import snapshot
import launch_dolphin as launcher
from kwce.channels import load_library


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', type=int, required=True)
    args = parser.parse_args()
    stopped()
    register()
    wad = ROOT / f'workspace/channels/kirbytv/build-v{args.revision}/kirbytv-ko-local-test.wad'
    meta = json.loads(wad.with_name('build-manifest.json').read_text(encoding='utf-8'))
    if not meta.get('local_only') or sha256(wad) != meta['wad_sha256']:
        raise ValueError('Kirby TV build identity/scope')
    number = 1
    while (PRIVATE / f'kirbytv-before-install-{number}.json').exists():
        number += 1
    (PRIVATE / f'kirbytv-before-install-{number}.json').write_text(json.dumps(snapshot(BASE / 'user'), indent=2))
    lib = load_library()
    title = lib.title.Title()
    title.load_wad(wad.read_bytes())
    lib.nand.EmuNAND(BASE / 'user/Wii').install_title(title)
    launcher.scrub_download_tasks(PROFILE)
    (ROOT / 'workspace/channels/kirbytv/active-build.json').write_text(json.dumps(dict(revision=args.revision, wad_sha256=meta['wad_sha256']), indent=2))
    path = ROOT / 'configs/kirbytv-runtime.lock.json'
    data = json.loads(path.read_text())
    data['builds'][str(args.revision)] = meta['wad_sha256']
    path.write_text(json.dumps(data, indent=2))
    print('Installed isolated Kirby TV build', args.revision, '; lock/active-build updated (catalog is the lead\'s)')


if __name__ == '__main__':
    main()

"""Install a new numbered Food build; preserve the previous installation record."""
import argparse, json
from audit_sd import ROOT, PRIVATE, sha256
from prepare_channel_access import stopped
from prepare_food_test import register, PROFILE, BASE
from prepare_gc_v6 import snapshot
import launch_dolphin as launcher
from kwce.channels import load_library


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--revision', type=int, required=True)
    parser.add_argument('--variant', default=None, help='WiiLink edition test build <variant>-build-vN (kwce.food_variants)')
    args = parser.parse_args(); stopped(); register()
    folder = f'{args.variant}-build-v{args.revision}' if args.variant else f'build-v{args.revision}'
    wad = ROOT / f'workspace/channels/food/{folder}/food-ko-local-test.wad'
    meta = json.loads(wad.with_name('build-manifest.json').read_text(encoding='utf-8'))
    if not meta.get('local_only') or sha256(wad) != meta['wad_sha256']:
        raise ValueError('Food build identity/scope')
    number = 1
    while (PRIVATE / f'food-before-install-{number}.json').exists():
        number += 1
    (PRIVATE / f'food-before-install-{number}.json').write_text(json.dumps(snapshot(BASE / 'user'), indent=2))
    lib = load_library(); title = lib.title.Title(); title.load_wad(wad.read_bytes())
    lib.nand.EmuNAND(BASE / 'user/Wii').install_title(title); launcher.scrub_download_tasks(PROFILE)
    active = dict(revision=args.revision, wad_sha256=meta['wad_sha256'])
    if args.variant:
        if meta.get('variant') != args.variant:
            raise ValueError('Food edition build identity')
        active['variant'] = args.variant
    (ROOT / 'workspace/channels/food/active-build.json').write_text(json.dumps(active, indent=2))
    path = ROOT / 'configs/food-runtime.lock.json'; data = json.loads(path.read_text())
    key = f'{args.variant}-{args.revision}' if args.variant else str(args.revision)
    data['builds'][key] = meta['wad_sha256']; path.write_text(json.dumps(data, indent=2))
    print('Installed isolated Food build', folder, '; lock/active-build updated')


if __name__ == '__main__':
    main()

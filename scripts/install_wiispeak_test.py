"""Switch the Wii Speak bed between its two approved builds (Dolphin must be stopped).

  --build original-v512   official Korean v512 (baseline; prepare_wiispeak_test.py installs it first)
  --build hardware-v1     hardware candidate, content 1 = ported Wiimmfi patch (comparison build)

Only these two pinned WADs are accepted (kwce.wiispeak_testbed.pinned_builds).
The channel save folder is kept. A snapshot of the profile before each install
goes to workspace/private. The shared catalog is not touched.

  .venv\\Scripts\\python.exe scripts\\install_wiispeak_test.py --build hardware-v1
"""
import argparse
import json
from audit_sd import ROOT, PRIVATE
from prepare_channel_access import stopped
from prepare_gc_v6 import snapshot
from prepare_wiispeak_test import register, install, PROFILE, BASE, CHANNEL
import launch_dolphin as launcher
from kwce import wiispeak_testbed as bed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--build', choices=sorted(bed.BUILDS), required=True)
    args = parser.parse_args()
    stopped()
    register()
    pinned = bed.pinned_builds(CHANNEL)
    if json.loads((ROOT / bed.LOCK).read_text(encoding='utf-8'))['builds'] != pinned:
        raise ValueError('Wii Speak approved builds differ from the runtime lock')
    number = 1
    while (PRIVATE / f'wiispeak-before-install-{number}.json').exists():
        number += 1
    (PRIVATE / f'wiispeak-before-install-{number}.json').write_text(json.dumps(snapshot(BASE / 'user'), indent=2))
    digest = install(args.build, pinned)
    launcher.scrub_download_tasks(PROFILE)
    launcher.validate(PROFILE)
    print(f'Wii Speak bed: {args.build} installed and active ({digest[:12]}); next: scripts/launch_wiispeak.py --check')


if __name__ == '__main__':
    main()

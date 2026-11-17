"""Read-only channel artifact/installation audit. Outputs metadata only.

Every catalog install (profile + artifact folder) is checked: the artifact WAD
must match its build manifest and the profile's installed title must match
that WAD. Hash agreement confirms build identity, not localization
completeness. Prints one compact line per install; --json prints the record.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.channel_validation import verify_installed_title
from audit_sd import sha256


def artifact_wad(folder, variant):
    manifest_path=folder/'build-manifest.json'
    if not manifest_path.exists()and folder.parent.name=='dvd-player':manifest_path=folder/'wad-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if 'wads' in manifest:
        row = manifest['wads'][variant]
        return folder / row['file'], row['sha256']
    candidates = list(folder.glob('*.wad'))
    if len(candidates) != 1:
        raise ValueError('Expected one WAD per selected build')
    return candidates[0], manifest['wad_sha256']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    catalog = json.loads((ROOT / 'configs/channels.catalog.json').read_text(encoding='utf-8'))
    library = load_library()
    results = []
    for channel in catalog['channels']:
        for install in channel['installs']:
            row = dict(channel=channel['id'], profile=install['profile'], artifact=install['artifact'], role=install['role'])
            try:
                if install.get('native_package'):
                    if channel['id'] != 'dvd-player' or install['profile'] != 'dvd-test-v3':
                        raise ValueError('Unexpected native install')
                    from kwce.dvd_native_validation import verify
                    row.update(passed=True, native_resources=verify(install, library))
                    results.append(row)
                    continue
                folder = ROOT / 'workspace/channels' / channel['id'] / install['artifact']
                wad, expected = artifact_wad(folder, install.get('variant', 'personal'))
                if sha256(wad) != expected:
                    raise ValueError('Selected WAD hash differs from build manifest')
                title = library.title.Title()
                title.load_wad(wad.read_bytes())
                if title.tmd.title_id.lower() != channel['title_id'].lower():
                    raise ValueError('Catalog title identity differs')
                user = ROOT / 'workspace/sandbox' / install['profile'] / 'user/Wii'
                row.update(passed=True, installed_contents=verify_installed_title(user, title.tmd.title_id, title.tmd.dump()))
            except (ValueError, OSError, KeyError):
                # Do not print underlying exceptions which could contain private data.
                row.update(passed=False, diagnostic='Artifact or installation identity check failed')
            results.append(row)
    result = dict(installs=results, all_installations_match=all(r['passed'] for r in results),
                  note='File identity checks do not establish translation or runtime coverage')
    (ROOT / 'workspace/private/channel-installation-review.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    if args.json:
        print(json.dumps(result))
    else:
        for r in results:
            state = (f"PASS native/{r['native_resources']} resources" if 'native_resources' in r
                     else f"PASS {r['installed_contents']} contents") if r['passed'] else 'FAIL'
            print(f"{r['channel']:<12} {r['profile']:<20} {r['artifact']:<17} {r['role']:<15} {state}")
        print('ALL PASS' if result['all_installations_match'] else 'SOME FAILED')
    if not result['all_installations_match']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

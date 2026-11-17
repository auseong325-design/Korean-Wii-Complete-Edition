"""Immutable Korean Kirby TV Channel local-test build. Originals are untouched.

Produces workspace/channels/kirbytv/build-v<N>/kirbytv-ko-local-test.wad, whose
service host is redirected to 127.0.0.2 (local_only). Byte-identically
reproducible into workspace/private with --reproduce.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import kirbytv_build as B
from kwce.channels import load_library


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', type=int, choices=B.REVISIONS, default=1)
    parser.add_argument('--reproduce', action='store_true')
    args = parser.parse_args()
    out = ROOT / f'workspace/channels/kirbytv/build-v{args.revision}'
    expected = None
    if args.reproduce:
        expected = (out / 'kirbytv-ko-local-test.wad').read_bytes()
        number = 1
        while (ROOT / f'workspace/private/kirbytv-reproduce-v{args.revision}-{number}').exists():
            number += 1
        out = ROOT / f'workspace/private/kirbytv-reproduce-v{args.revision}-{number}'
    if out.exists():
        raise SystemExit('Existing Kirby TV build preserved')
    title, reference, record = B.build_title(local=True, revision=args.revision)
    changed = B.changed_contents(title, reference)
    if changed != B.CHANGED:
        raise ValueError(f'Unexpected Kirby TV content change: {changed}')
    wad = title.dump_wad()
    check = load_library().title.Title()
    check.load_wad(wad)
    if [i for i in range(len(check.tmd.content_records)) if check.get_content_by_index(i) != title.get_content_by_index(i)]:
        raise ValueError('Kirby TV content roundtrip failed')
    hosts = __import__('kwce.kirbytv_swf', fromlist=['service_hosts']).service_hosts(
        __import__('kwce.channels', fromlist=['ChannelArchive']).ChannelArchive(title.get_content_by_index(2)).get('trusted/Gumball2.12.RC-1.swf'))
    if '127.0.0.2' not in hosts or any('wiilink24' in h for h in hosts):
        raise ValueError('Local build must redirect the service host')
    out.mkdir(parents=True)
    (out / 'kirbytv-ko-local-test.wad').write_bytes(wad)
    manifest = dict(
        revision=args.revision, channel='kirbytv', title_id=title.tmd.title_id, boot_index=title.tmd.boot_index,
        wad_sha256=hashlib.sha256(wad).hexdigest(), changed_contents=changed, local_only=True,
        service_hosts=hosts, full_localization_complete=False, hardware_success_verified=False,
        build=record)
    (out / 'build-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    if expected is not None and expected != wad:
        raise ValueError('Kirby TV reproduction differs')
    print('Reproduced byte-identically' if expected is not None else 'Built',
          'Kirby TV revision', args.revision, ': contents', changed, 'hosts', hosts,
          'wad', hashlib.sha256(wad).hexdigest()[:16])


if __name__ == '__main__':
    main()

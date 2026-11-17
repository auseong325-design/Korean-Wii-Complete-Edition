"""Korean Kirby TV hardware candidate: WiiLink ktv_2 service patch + Korean
resources, service host kept at kirby.wiilink24.com, fakesigned, not installed.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import kirbytv_build as B
from kwce.channels import load_library, ChannelArchive
from kwce.hardware import hardware_wad
from kwce.kirbytv_swf import service_hosts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', type=int, choices=B.REVISIONS, default=1)
    parser.add_argument('--reproduce', action='store_true')
    args = parser.parse_args()
    base = ROOT / 'workspace/channels/kirbytv'
    out = base / f'hardware-v{args.revision}'
    expected = None
    if args.reproduce:
        expected = (out / 'kirbytv-ko-hardware-test.wad').read_bytes()
        number = 1
        suffix = '' if args.revision == 1 else f'-v{args.revision}'
        while (ROOT / f'workspace/private/kirbytv-hardware-reproduce{suffix}-{number}').exists():
            number += 1
        out = ROOT / f'workspace/private/kirbytv-hardware-reproduce{suffix}-{number}'
    if out.exists():
        raise ValueError('Existing Kirby TV hardware build preserved')
    title, reference, record = B.build_title(local=False, revision=args.revision)
    if B.changed_contents(title, reference) != B.CHANGED:
        raise ValueError('Unexpected Kirby TV content change')
    hosts = service_hosts(ChannelArchive(title.get_content_by_index(2)).get('trusted/Gumball2.12.RC-1.swf'))
    if 'kirby.wiilink24.com' not in hosts or '127.0.0.2' in hosts:
        raise ValueError('Hardware build must keep the live service host')
    original = reference.dump_wad()  # WiiLink stock + ktv_2 + WiiLink TMD fields
    wad, checks = hardware_wad(title.dump_wad(), original)
    verify = load_library().title.Title()
    verify.load_wad(wad)
    if not verify.get_is_fakesigned():
        raise ValueError('Hardware WAD is not fakesigned')
    if expected is not None and expected != wad:
        raise ValueError('Kirby TV hardware reproduction differs')
    out.mkdir(parents=True)
    (out / 'kirbytv-ko-hardware-test.wad').write_bytes(wad)
    manifest = dict(
        revision=args.revision, channel='kirbytv', hardware_candidate=True, title_id=title.tmd.title_id,
        wad_sha256=hashlib.sha256(wad).hexdigest(), original_sha256=hashlib.sha256(original).hexdigest(),
        local_only=False, service_hosts=hosts, wiilink_service_patch='ktv_2 (content 2) + WiiLink TMD region',
        changed_contents=B.CHANGED, hardware_checks=checks, fakesigned=True, installed_anywhere=False,
        full_localization_complete=False, hardware_success_verified=False, build=record)
    (out / 'build-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'PASS: Kirby TV hardware v{args.revision}, service', hosts, '('
          + ('byte-identical reproduction' if expected else 'not installed') + '); wad', hashlib.sha256(wad).hexdigest()[:16])


if __name__ == '__main__':
    main()

"""Local-only Nintendo 262000 branch discriminator; never use on a console.

The four existing 262000 immediates are replaced by 262001..262004 in a new
isolated access build. This changes the displayed error number, not its condition;
it cannot identify which branch a real Wii took.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.ppc_patch import to_file
from audit_nintendo_error_sites import SITES, validate
from prepare_channel_access import stopped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--revision', type=int, choices=range(18, 24), required=True)
    args = ap.parse_args()
    stopped()
    base = ROOT / 'workspace/channels/nintendo'
    source = base / 'access-build-v17'
    out = base / f'access-build-v{args.revision}'
    if out.exists():
        raise SystemExit('Existing access build preserved')
    meta = json.loads((source / 'build-manifest.json').read_text(encoding='utf-8'))
    wad = (source / 'nintendo-local-test.wad').read_bytes()
    if hashlib.sha256(wad).hexdigest() != meta['wad_sha256']:
        raise ValueError('Source WAD differs from its manifest')
    lib = load_library()
    title = lib.title.Title(); title.load_wad(wad)
    before = title.get_content_by_index(1)
    validate(before)
    after = bytearray(before)
    for i, site in enumerate(SITES, 1):
        at = to_file(before, site, 4)
        word = struct.unpack_from('>I', before, at)[0]
        if word & 0xffff != 0xff70:
            raise ValueError('Unexpected error constant')
        struct.pack_into('>I', after, at, (word & 0xffff0000) | (0xff70 + i))
    changed = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
    if changed != {to_file(before, site, 4) + 3 for site in SITES}:
        raise ValueError('Unexpected diagnostic edits')
    title.set_content(bytes(after), 1)
    output = title.dump_wad()
    check = lib.title.Title(); check.load_wad(output)
    if check.get_content_by_index(1) != bytes(after):
        raise ValueError('Diagnostic output content differs')
    for i in range(len(check.tmd.content_records)):
        if i != 1 and check.get_content_by_index(i) != title.get_content_by_index(i):
            raise ValueError('Unexpected content changed')
    meta.update(revision=args.revision, wad_sha256=hashlib.sha256(output).hexdigest(),
                local_simulation=True, external_network_allowed=False, diagnostic_only=True,
                diagnostic_branch_codes={str(262000 + i): hex(site) for i, site in enumerate(SITES, 1)})
    out.mkdir()
    (out / 'nintendo-local-test.wad').write_bytes(output)
    (out / 'build-manifest.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    print(f'Created local-only diagnostic access-build-v{args.revision}; four error labels changed')


if __name__ == '__main__':
    main()

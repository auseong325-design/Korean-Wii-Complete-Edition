"""Build the country-disguised Everybody Votes channel: build-v18 + the 136->49 bridge.

build-v18 (the latest UI build: Korean messages, fonts, HOME menu, manual, and the
worldResult "표" fix) is the base. This layers kwce.votes_country_bridge onto content 1
(the DOL) with an in-place edit -- one instruction in the country getter plus a dead
cave -- so the section table and file size are identical and every other content is
byte-for-byte preserved. Output: workspace/channels/votes/build-v19/votes-ko-ui-test.wad
(same WAD name and TMD region 4 as v17/v18).

    build_votes_country.py                 # write build-v19 and verify
    build_votes_country.py --reproduce     # rebuild into workspace/private, require identical bytes

NOTE on numbering: the task named build-v18, but v18 already exists (the worldResult vote-
count fix from wave 3). Per the project's "new revision numbers only, older revisions must
still reproduce" rule this build is v19, layered on v18 so it keeps that fix. v17 and v18
are untouched and still reproduce (scripts/build_votes_ui.py --reproduce --revision 17/18).

No Dolphin, no SD, no network. Content 1 (the executable) changes, so the lead must boot
build-v19 to confirm on hardware/emulator.
"""
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.ppc_patch import sections
from kwce import votes_country_bridge as bridge

VOTES = ROOT / 'workspace/channels/votes'
BASE_REVISION = 18
REVISION = 19            # default; --revision 20 = in-place constant (the shipped one)
REVISIONS = (19, 20)
NAME = 'votes-ko-ui-test.wad'
NUM_CONTENTS = 14


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def build(revision=REVISION):
    if revision not in REVISIONS:
        raise ValueError('Unknown votes country revision')
    base_dir = VOTES / f'build-v{BASE_REVISION}'
    base_meta = json.loads((base_dir / 'build-manifest.json').read_text(encoding='utf-8'))
    base_wad = (base_dir / NAME).read_bytes()
    if _sha(base_wad) != base_meta['wad_sha256']:
        raise ValueError('build-v18 WAD differs from its manifest; refusing to build on it')

    lib = load_library()
    t = lib.title.Title()
    t.load_wad(base_wad)
    original = [t.get_content_by_index(i) for i in range(NUM_CONTENTS)]

    dol = original[1]
    patched = bridge.patch(dol) if revision == 19 else bridge.patch_constant(dol)
    # The bridge adds no section and changes no section-table byte or the length.
    if sections(patched) != sections(dol) or len(patched) != len(dol) or patched[:0xE8] != dol[:0xE8]:
        raise ValueError('Country bridge altered the DOL layout')
    if revision == 20 and sum(a != b for a, b in zip(dol, patched)) > 4:
        raise ValueError('Revision 20 must change at most 4 bytes')

    t.set_content(patched, 1)
    wad = t.dump_wad()

    check = lib.title.Title()
    check.load_wad(wad)
    changed = {i for i in range(NUM_CONTENTS) if check.get_content_by_index(i) != original[i]}
    if changed != {1}:
        raise ValueError(f'Expected only content 1 to change, got {sorted(changed)}')
    if check.tmd.region != t.tmd.region:
        raise ValueError('TMD region changed')

    meta = copy.deepcopy(base_meta)
    meta.update(
        revision=revision,
        parent_revision=BASE_REVISION,
        wad_sha256=_sha(wad),
        runtime_verified=False,
        installed=False,
        country_disguise={
            'from': bridge.FROM_COUNTRY,
            'to': bridge.TO_COUNTRY,
            'scope': 'country getter result only (0x800509b4); region getter + reader unchanged',
            'hook_instruction_va': hex(bridge.GETTER_SRWI),
            'cave_va': hex(bridge.CAVE),
            'dol_section_added': False,
            'language_remapped': False,
            'signature_verified': False,
            'hardware_verified': False,
            'live_service_verified': False,
        },
        changed_from_parent=[1],
    )
    if revision == 20:
        meta['country_disguise'].update(
            cave_va=None, in_place_constant=True, changed_bytes=4,
            scope='country getter returns 49 (one li instruction); region getter + reader unchanged',
            supersedes='build-v19 (cave in the .init table tail: boots into Invalid write 0x5463463e)')
    return wad, meta, base_meta['wad_sha256']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reproduce', action='store_true',
                    help='rebuild into workspace/private and require identical WAD + manifest')
    ap.add_argument('--revision', type=int, default=REVISION, choices=REVISIONS)
    args = ap.parse_args()
    revision = args.revision

    wad, meta, base_sha = build(revision)

    out = VOTES / f'build-v{revision}'
    expected = None
    if args.reproduce:
        if not out.exists():
            raise SystemExit(f'build-v{revision} does not exist yet; run without --reproduce first')
        expected = ((out / NAME).read_bytes(), (out / 'build-manifest.json').read_bytes())
        n = 1
        while (ROOT / f'workspace/private/votes-country-reproduce-{n}').exists():
            n += 1
        out = ROOT / f'workspace/private/votes-country-reproduce-{n}'

    if out.exists():
        raise SystemExit('Existing build preserved')

    manifest_bytes = json.dumps(meta, ensure_ascii=False, indent=2).encode('utf-8') + b'\n'
    if expected is not None and (wad, manifest_bytes) != expected:
        raise SystemExit(f'build-v{revision} reproduction differs from the stored build')

    out.mkdir(parents=True)
    (out / NAME).write_bytes(wad)
    (out / 'build-manifest.json').write_bytes(manifest_bytes)

    where = 'reproduced into ' + str(out.relative_to(ROOT)) if args.reproduce else 'built'
    print(json.dumps(dict(status=where, revision=revision, base=f'build-v{BASE_REVISION}',
                          base_wad_sha256=base_sha[:16], wad_sha256=meta['wad_sha256'],
                          changed_contents=meta['changed_from_parent'],
                          country=f"{bridge.FROM_COUNTRY}->{bridge.TO_COUNTRY}"), indent=2))


if __name__ == '__main__':
    main()

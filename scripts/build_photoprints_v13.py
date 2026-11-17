"""Photo Prints build-v13 (local) and hardware-v9 (candidate): Korean HOME dialogs, operations guide chrome and exit prompt.

  .venv\\Scripts\\python.exe scripts\\build_photoprints_v13.py           # create both (refuses to overwrite)
  .venv\\Scripts\\python.exe scripts\\build_photoprints_v13.py --verify  # byte-identical regeneration check

A Korean console runs this channel's HOME Button Menu in language 1 (English): the DOL
clamps SCGetLanguage() 9 to 1 and reads home.csv / network.csv from content 2
(kwce.photoprints_home_guide, which re-checks those DOL words on every build).

build-v13  = build-v12 with contents 2, 3 and 7 from kwce.photoprints_home_guide:
             content 2 home.csv (columns 0-6 = Korean column 9) and network.csv (the original
             seven columns, all Korean; replaces build-v12's ten-column variant), content 3
             HOME fonts + 12 native glyphs, content 7 guide chrome and font overrides.
             manual.jpg and the save banner stay as in build-v12.
hardware-v9 = hardware-v8 with the same three contents, fakesigned (WiiLink endpoints, IOS56,
             TMD region 4 kept). Not installed anywhere; real Wii untested.
No NAND/SD writes, no Dolphin.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import ChannelArchive, load_library  # noqa: E402
from kwce.hardware import local_reference_counts  # noqa: E402
from kwce.photoprints_home_guide import NETWORK, home_language_facts, korean_home_guide, review_sheet  # noqa: E402
from kwce.wiiroom_formats import decompress_lz11  # noqa: E402

BASE = ROOT / 'workspace/channels/photoprints'
TITLE = '000100014843444a'
IOS56 = '0000000100000038'
LOCAL, HARDWARE = BASE / 'build-v13', BASE / 'hardware-v9'
LOCAL_WAD, HARDWARE_WAD = 'photoprints-ko-local-test.wad', 'photoprints-ko-hardware-test.wad'
ORIGINAL = BASE / 'originals/digicam-japan-v1024.wad'
SHEET = BASE / 'home-guide-v13-review-sheet.png'
CHANGED = [2, 3, 7]
TMD_FAKESIGN = (0x1e2, 0x1e4)


def record_range(index):
    """TMD content record size + SHA-1 bytes of content `index`."""
    start = 0x1e4 + 36 * index
    return start + 8, start + 36


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _load(folder, name):
    lib = load_library()
    data = (folder / name).read_bytes()
    meta = json.loads((folder / 'build-manifest.json').read_text(encoding='utf-8'))
    if sha(data) != meta['wad_sha256']:
        raise ValueError(f'{folder.name} differs from its manifest')
    title = lib.title.Title()
    title.load_wad(data)
    if title.tmd.title_id.lower() != TITLE or title.tmd.ios_tid.lower() != IOS56:
        raise ValueError(f'{folder.name}: unexpected title or IOS')
    return data, meta, title


def _contents(title):
    return [title.get_content_by_index(i) for i in range(len(title.tmd.content_records))]


def _changed_bytes(a, b):
    if len(a) != len(b):
        raise ValueError('TMD length changed')
    return {i for i, (x, y) in enumerate(zip(a, b)) if x != y}


def _allowed(changed, *ranges):
    return all(any(lo <= i < hi for lo, hi in ranges) for i in changed)


def _network_original():
    lib = load_library()
    original = lib.title.Title()
    original.load_wad(ORIGINAL.read_bytes())
    return ChannelArchive(original.get_content_by_index(2)).get(NETWORK)


def _apply(title, new):
    for index, data in zip(CHANGED, new):
        title.set_content(data, index)


def _check_scope(before, check, new, name):
    after = _contents(check)
    if [i for i in range(len(before)) if after[i] != before[i]] != CHANGED or [after[i] for i in CHANGED] != list(new):
        raise ValueError(f'{name} change escaped contents 2, 3 and 7')


def build_local():
    data, meta, title = _load(BASE / 'build-v12', LOCAL_WAD)
    if not meta.get('local_only') or meta.get('revision') != 12:
        raise ValueError('build-v12 scope differs')
    before = _contents(title)
    facts = home_language_facts(decompress_lz11(before[1]))
    tmd_before, ticket_before = title.tmd.dump(), title.ticket.dump()
    new, record = korean_home_guide(before[2], before[3], before[7], _network_original())
    _apply(title, new)
    wad = title.dump_wad()
    check = load_library().title.Title()
    check.load_wad(wad)
    _check_scope(before, check, new, 'build-v13')
    if check.ticket.dump() != ticket_before or not _allowed(_changed_bytes(tmd_before, check.tmd.dump()), *map(record_range, CHANGED)):
        raise ValueError('build-v13 TMD/ticket change escaped the content 2/3/7 records')
    manifest = dict(meta)
    manifest.pop('manual_runtime_verified', None)
    manifest.update(revision=13, source_build='build-v12', source_wad_sha256=meta['wad_sha256'], wad_sha256=sha(wad),
                    changed_contents_vs_source=CHANGED, tmd_region=check.tmd.region, home_language=facts, home_guide_v13=record,
                    content_sha256={str(i): sha(d) for i, d in zip(CHANGED, new)},
                    local_only=True, full_localization_complete=False, hardware_success_verified=False,
                    manual_runtime_verified=False, home_guide_runtime_verified=False)
    return wad, manifest, new, before[7]


def build_hardware(new):
    data, meta, title = _load(BASE / 'hardware-v8', HARDWARE_WAD)
    if title.tmd.region != 4 or not title.get_is_fakesigned() or meta.get('revision') != 8:
        raise ValueError('hardware-v8 identity differs')
    before = _contents(title)
    facts = home_language_facts(decompress_lz11(before[1]))
    counts = local_reference_counts(title)
    tmd_before, ticket_before = title.tmd.dump(), title.ticket.dump()
    _apply(title, new)
    title.fakesign()
    wad = title.dump_wad()
    check = load_library().title.Title()
    check.load_wad(wad)
    if check.tmd.title_id.lower() != TITLE or check.tmd.ios_tid.lower() != IOS56 or check.tmd.region != 4 or not check.get_is_fakesigned():
        raise ValueError('hardware-v9 title/IOS/region/signature check failed')
    _check_scope(before, check, new, 'hardware-v9')
    if local_reference_counts(check) != counts:
        raise ValueError('hardware-v9 service addresses changed')
    changed = _changed_bytes(tmd_before, check.tmd.dump())
    if check.ticket.dump() != ticket_before or not _allowed(changed, TMD_FAKESIGN, *map(record_range, CHANGED)):
        raise ValueError('hardware-v9 TMD/ticket change escaped fakesign and the content 2/3/7 records')
    manifest = dict(hardware_candidate=True, hardware_success_verified=False, full_localization_complete=False,
                    local_only=False, revision=9, source='hardware-v8', source_wad_sha256=meta['wad_sha256'],
                    local_source='build-v13', source_revision=13, wad_sha256=sha(wad), title_id=check.tmd.title_id.lower(),
                    title_version=check.tmd.title_version, ios=check.tmd.ios_tid.lower(), region=check.tmd.region,
                    contents=len(before), changed_contents_vs_source=CHANGED, home_language=facts,
                    content_sha256={str(i): sha(d) for i, d in zip(CHANGED, new)},
                    service_endpoints_kept=True, local_reference_counts=counts, fakesigned=True,
                    tmd_changed_ranges=dict(fakesign=[hex(x) for x in TMD_FAKESIGN],
                                            **{f'content{i}_record': [hex(x) for x in record_range(i)] for i in CHANGED}),
                    reason='Korean HOME dialogs, operations-guide chrome and exit prompt (contents 2, 3, 7)')
    return wad, manifest


def build():
    local, local_meta, new, original7 = build_local()
    hardware, hardware_meta = build_hardware(new)
    hardware_meta['local_source_wad_sha256'] = local_meta['wad_sha256']
    return (local, local_meta), (hardware, hardware_meta), (original7, new[2])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify', action='store_true')
    args = ap.parse_args()
    (local, local_meta), (hardware, hardware_meta), (original7, new7) = build()
    outputs = ((LOCAL, LOCAL_WAD, local, local_meta), (HARDWARE, HARDWARE_WAD, hardware, hardware_meta))
    if args.verify:
        for folder, name, data, meta in outputs:
            if (folder / name).read_bytes() != data:
                raise ValueError(f'{folder.name} is not byte reproducible')
            if json.loads((folder / 'build-manifest.json').read_text(encoding='utf-8')) != json.loads(json.dumps(meta, ensure_ascii=False)):
                raise ValueError(f'{folder.name} manifest differs on regeneration')
        print('PASS: build-v13 and hardware-v9 reproduce byte-identically; only contents 2, 3 and 7 changed '
              '(hardware-v9: fakesigned, WiiLink endpoints kept)')
        return
    if LOCAL.exists() or HARDWARE.exists() or SHEET.exists():
        raise SystemExit('Existing Photo Prints output preserved')
    for folder, name, data, meta in outputs:
        folder.mkdir()
        (folder / name).write_bytes(data)
        (folder / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    sheet = review_sheet(original7, new7, SHEET)
    print(json.dumps(dict(build_v13=local_meta['wad_sha256'], hardware_v9=hardware_meta['wad_sha256'],
                          home_language=local_meta['home_language']['korean_console_home_language'],
                          added_glyphs=local_meta['home_guide_v13']['home_fonts']['archives'][0]['added_glyphs'],
                          review_sheet=sheet['size']), ensure_ascii=False))


if __name__ == '__main__':
    main()

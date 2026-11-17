"""Photo Prints build-v12 (local) and hardware-v8 (candidate): Korean manual picture, save banner, HOME network prompt.

  .venv\\Scripts\\python.exe scripts\\build_photoprints_v12.py           # create both (refuses to overwrite)
  .venv\\Scripts\\python.exe scripts\\build_photoprints_v12.py --verify  # byte-identical regeneration check

build-v12  = build-v11 with content 2 rebuilt by kwce.photoprints_manual: manual.jpg
             (Korean operation guide), banner.lz (Korean save-data banner wordmark) and
             HomeButton3/network.csv (Korean column). Every other content, every other
             file of content 2, the ticket and the TMD outside the content-2 record stay
             as in build-v11.
hardware-v8 = hardware-v7 (WiiLink service endpoints, IOS56, TMD region 4) with the same
             new content 2, fakesigned. Not installed anywhere; real Wii untested.
No NAND/SD writes, no Dolphin.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library  # noqa: E402
from kwce.hardware import local_reference_counts  # noqa: E402
from kwce.photoprints_manual import korean_content2, review_sheet  # noqa: E402
from kwce.photoprints_menu_art import font_sha256  # noqa: E402

BASE = ROOT / 'workspace/channels/photoprints'
TITLE = '000100014843444a'
IOS56 = '0000000100000038'
LOCAL, HARDWARE = BASE / 'build-v12', BASE / 'hardware-v8'
LOCAL_WAD, HARDWARE_WAD = 'photoprints-ko-local-test.wad', 'photoprints-ko-hardware-test.wad'
SHEET = BASE / 'manual-v12-review-sheet.png'
TMD_FAKESIGN = (0x1e2, 0x1e4)                 # minor version, brute-forced by fakesign
TMD_CONTENT2 = (0x1e4 + 72 + 8, 0x1e4 + 108)  # content 2 record: size + SHA-1


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


def _only_content2(before, after, content2, name):
    if [i for i in range(len(before)) if after[i] != before[i]] != [2] or after[2] != content2:
        raise ValueError(f'{name} change escaped content 2')


def build_local():
    data, meta, title = _load(BASE / 'build-v11', LOCAL_WAD)
    if not meta.get('local_only') or meta.get('revision') != 11:
        raise ValueError('build-v11 scope differs')
    before = _contents(title)
    tmd_before, ticket_before = title.tmd.dump(), title.ticket.dump()
    content2, record = korean_content2(before[2])
    title.set_content(content2, 2)
    wad = title.dump_wad()
    check = load_library().title.Title()
    check.load_wad(wad)
    _only_content2(before, _contents(check), content2, 'build-v12')
    if check.ticket.dump() != ticket_before or not _allowed(_changed_bytes(tmd_before, check.tmd.dump()), TMD_CONTENT2):
        raise ValueError('build-v12 TMD/ticket change escaped the content 2 record')
    manifest = dict(meta)
    manifest.update(revision=12, source_build='build-v11', source_wad_sha256=meta['wad_sha256'], wad_sha256=sha(wad),
                    changed_contents_vs_source=[2], tmd_region=check.tmd.region, content2_v12=record,
                    content2_sha256=sha(content2), font_sha256=font_sha256(),
                    local_only=True, full_localization_complete=False, hardware_success_verified=False,
                    manual_runtime_verified=False)
    return wad, manifest, content2, before[2]


def build_hardware(content2):
    data, meta, title = _load(BASE / 'hardware-v7', HARDWARE_WAD)
    if title.tmd.region != 4 or not title.get_is_fakesigned() or meta.get('revision') != 7:
        raise ValueError('hardware-v7 identity differs')
    before = _contents(title)
    counts = local_reference_counts(title)
    tmd_before, ticket_before = title.tmd.dump(), title.ticket.dump()
    title.set_content(content2, 2)
    title.fakesign()
    wad = title.dump_wad()
    check = load_library().title.Title()
    check.load_wad(wad)
    if check.tmd.title_id.lower() != TITLE or check.tmd.ios_tid.lower() != IOS56 or check.tmd.region != 4 or not check.get_is_fakesigned():
        raise ValueError('hardware-v8 title/IOS/region/signature check failed')
    _only_content2(before, _contents(check), content2, 'hardware-v8')
    if local_reference_counts(check) != counts:
        raise ValueError('hardware-v8 service addresses changed')
    changed = _changed_bytes(tmd_before, check.tmd.dump())
    if check.ticket.dump() != ticket_before or not _allowed(changed, TMD_FAKESIGN, TMD_CONTENT2):
        raise ValueError('hardware-v8 TMD/ticket change escaped fakesign and the content 2 record')
    manifest = dict(hardware_candidate=True, hardware_success_verified=False, full_localization_complete=False,
                    local_only=False, revision=8, source='hardware-v7', source_wad_sha256=meta['wad_sha256'],
                    local_source='build-v12', source_revision=12, wad_sha256=sha(wad), title_id=check.tmd.title_id.lower(),
                    title_version=check.tmd.title_version, ios=check.tmd.ios_tid.lower(), region=check.tmd.region,
                    contents=len(before), changed_contents_vs_source=[2], content2_sha256=sha(content2),
                    service_endpoints_kept=True, local_reference_counts=counts, fakesigned=True,
                    tmd_changed_ranges=dict(fakesign=[hex(x) for x in TMD_FAKESIGN], content2_record=[hex(x) for x in TMD_CONTENT2]),
                    reason='Korean manual.jpg, save-data banner wordmark and HOME network prompt (content 2)')
    return wad, manifest


def build():
    local, local_meta, content2, original2 = build_local()
    hardware, hardware_meta = build_hardware(content2)
    hardware_meta['local_source_wad_sha256'] = local_meta['wad_sha256']
    return (local, local_meta), (hardware, hardware_meta), (original2, content2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify', action='store_true')
    args = ap.parse_args()
    (local, local_meta), (hardware, hardware_meta), (original2, content2) = build()
    outputs = ((LOCAL, LOCAL_WAD, local, local_meta), (HARDWARE, HARDWARE_WAD, hardware, hardware_meta))
    if args.verify:
        for folder, name, data, meta in outputs:
            if (folder / name).read_bytes() != data:
                raise ValueError(f'{folder.name} is not byte reproducible')
            if json.loads((folder / 'build-manifest.json').read_text(encoding='utf-8')) != json.loads(json.dumps(meta, ensure_ascii=False)):
                raise ValueError(f'{folder.name} manifest differs on regeneration')
        print('PASS: build-v12 and hardware-v8 reproduce byte-identically; only content 2 changed '
              '(manual.jpg, banner.lz, HomeButton3/network.csv; hardware-v8: fakesigned, WiiLink endpoints kept)')
        return
    if LOCAL.exists() or HARDWARE.exists() or SHEET.exists():
        raise SystemExit('Existing Photo Prints output preserved')
    for folder, name, data, meta in outputs:
        folder.mkdir()
        (folder / name).write_bytes(data)
        (folder / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    sheet = review_sheet(original2, content2, SHEET)
    print(json.dumps(dict(build_v12=local_meta['wad_sha256'], hardware_v8=hardware_meta['wad_sha256'],
                          manual_bytes=local_meta['content2_v12']['manual']['bytes'], review_sheet=sheet['size']), ensure_ascii=False))


if __name__ == '__main__':
    main()

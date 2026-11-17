"""Photo Prints build-v11 (local) and hardware-v7 (candidate): Korean Wii Menu icon/banner.

  .venv\\Scripts\\python.exe scripts\\build_photoprints_menu_v11.py           # create both (refuses to overwrite)
  .venv\\Scripts\\python.exe scripts\\build_photoprints_menu_v11.py --verify  # byte-identical regeneration check

build-v11   = build-v10 with content 0 replaced by kwce.photoprints_menu_art (Korean
              title textures in icon.bin/banner.bin). Contents 1-12, ticket and
              everything else stay as in build-v10 (local loopback endpoints).
hardware-v7 = hardware-v5 (WiiLink service endpoints, IOS56) with the same new
              content 0, TMD region 0 -> 4 (Korean System Menu accepts 3/4 only),
              fakesigned. Not installed anywhere; real Wii untested.
No NAND/SD writes, no Dolphin.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.hardware import local_reference_counts
from kwce.photoprints_menu_art import contact_sheet, korean_menu_art

BASE = ROOT / 'workspace/channels/photoprints'
TITLE = '000100014843444a'
IOS56 = '0000000100000038'
LOCAL, HARDWARE = BASE / 'build-v11', BASE / 'hardware-v7'
LOCAL_WAD, HARDWARE_WAD = 'photoprints-ko-local-test.wad', 'photoprints-ko-hardware-test.wad'
SHEET = BASE / 'menu-art-v11-contact-sheet.png'
TMD_REGION = (0x19c, 0x19e)
TMD_FAKESIGN = (0x1e2, 0x1e4)            # minor version, brute-forced by fakesign
TMD_CONTENT0 = (0x1e4 + 8, 0x1e4 + 36)   # content 0 record: size + SHA-1


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


def build_local():
    data, meta, title = _load(BASE / 'build-v10', LOCAL_WAD)
    if not meta.get('local_only') or meta.get('revision') != 10:
        raise ValueError('build-v10 scope differs')
    before = _contents(title)
    tmd_before, ticket_before = title.tmd.dump(), title.ticket.dump()
    content0, art = korean_menu_art(before[0])
    title.set_content(content0, 0)
    wad = title.dump_wad()
    check = load_library().title.Title()
    check.load_wad(wad)
    after = _contents(check)
    if [i for i in range(len(before)) if after[i] != before[i]] != [0] or after[0] != content0:
        raise ValueError('build-v11 change escaped content 0')
    if check.ticket.dump() != ticket_before or not _allowed(_changed_bytes(tmd_before, check.tmd.dump()), TMD_CONTENT0):
        raise ValueError('build-v11 TMD/ticket change escaped the content 0 record')
    manifest = dict(meta)
    manifest.update(revision=11, source_build='build-v10', source_wad_sha256=meta['wad_sha256'], wad_sha256=sha(wad),
                    changed_contents_vs_source=[0], tmd_region=check.tmd.region, menu_art=art,
                    local_only=True, full_localization_complete=False, hardware_success_verified=False,
                    menu_art_runtime_verified=False)
    return wad, manifest, content0, before[0]


def build_hardware(content0):
    data, meta, title = _load(BASE / 'hardware-v5', HARDWARE_WAD)
    if title.tmd.region != 0 or not title.get_is_fakesigned() or meta.get('source_revision') != 10:
        raise ValueError('hardware-v5 identity differs')
    before = _contents(title)
    counts = local_reference_counts(title)
    tmd_before, ticket_before = title.tmd.dump(), title.ticket.dump()
    title.set_content(content0, 0)
    title.tmd.region = 4
    title.fakesign()
    wad = title.dump_wad()
    check = load_library().title.Title()
    check.load_wad(wad)
    after = _contents(check)
    if check.tmd.title_id.lower() != TITLE or check.tmd.ios_tid.lower() != IOS56 or check.tmd.region != 4 or not check.get_is_fakesigned():
        raise ValueError('hardware-v7 title/IOS/region/signature check failed')
    if [i for i in range(len(before)) if after[i] != before[i]] != [0] or after[0] != content0:
        raise ValueError('hardware-v7 change escaped content 0')
    if local_reference_counts(check) != counts:
        raise ValueError('hardware-v7 service addresses changed')
    changed = _changed_bytes(tmd_before, check.tmd.dump())
    if check.ticket.dump() != ticket_before or not _allowed(changed, TMD_REGION, TMD_FAKESIGN, TMD_CONTENT0):
        raise ValueError('hardware-v7 TMD/ticket change escaped region, fakesign and content 0 record')
    manifest = dict(hardware_candidate=True, hardware_success_verified=False, full_localization_complete=False,
                    local_only=False, revision=7, source='hardware-v5', source_wad_sha256=meta['wad_sha256'],
                    local_source='build-v11', source_revision=11, wad_sha256=sha(wad), title_id=check.tmd.title_id.lower(),
                    title_version=check.tmd.title_version, ios=check.tmd.ios_tid.lower(), region_before=0, region_after=4,
                    contents=len(after), changed_contents_vs_source=[0], content0_sha256=sha(content0),
                    service_endpoints_kept=True, local_reference_counts=counts, fakesigned=True,
                    tmd_changed_ranges=dict(region=[hex(x) for x in TMD_REGION], fakesign=[hex(x) for x in TMD_FAKESIGN],
                                            content0_record=[hex(x) for x in TMD_CONTENT0]),
                    reason='Korean Wii Menu icon/banner title (content 0) + TMD region 4 for the Korean System Menu check')
    return wad, manifest


def build():
    local, local_meta, content0, original0 = build_local()
    hardware, hardware_meta = build_hardware(content0)
    hardware_meta['local_source_wad_sha256'] = local_meta['wad_sha256']
    return (local, local_meta), (hardware, hardware_meta), (original0, content0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify', action='store_true')
    args = ap.parse_args()
    (local, local_meta), (hardware, hardware_meta), (original0, content0) = build()
    if args.verify:
        for folder, name, data, meta in ((LOCAL, LOCAL_WAD, local, local_meta), (HARDWARE, HARDWARE_WAD, hardware, hardware_meta)):
            if (folder / name).read_bytes() != data:
                raise ValueError(f'{folder.name} is not byte reproducible')
            if json.loads((folder / 'build-manifest.json').read_text(encoding='utf-8')) != json.loads(json.dumps(meta, ensure_ascii=False)):
                raise ValueError(f'{folder.name} manifest differs on regeneration')
        print('PASS: build-v11 and hardware-v7 reproduce byte-identically; only content 0 changed '
              '(hardware-v7: + TMD region 4, fakesigned, WiiLink endpoints kept)')
        return
    if LOCAL.exists() or HARDWARE.exists() or SHEET.exists():
        raise SystemExit('Existing Photo Prints output preserved')
    for folder, name, data, meta in ((LOCAL, LOCAL_WAD, local, local_meta), (HARDWARE, HARDWARE_WAD, hardware, hardware_meta)):
        folder.mkdir()
        (folder / name).write_bytes(data)
        (folder / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    sheet = contact_sheet(original0, content0, SHEET)
    print(json.dumps(dict(build_v11=local_meta['wad_sha256'], hardware_v7=hardware_meta['wad_sha256'],
                          hardware_v7_region=4, contact_sheet=sheet['size']), ensure_ascii=False))


if __name__ == '__main__':
    main()

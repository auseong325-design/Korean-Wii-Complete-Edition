"""Photo Prints build-v14 (local) and hardware-v10 (candidate): RC6 wave-2 fixes.

  .venv\\Scripts\\python.exe scripts\\build_photoprints_v14.py           # create both (refuses to overwrite)
  .venv\\Scripts\\python.exe scripts\\build_photoprints_v14.py --verify  # byte-identical regeneration check

build-v14  = build-v13 with content 2 (layout.arc.LZ) button-caption centering,
             OK->확인, tilde U+007E->U+FF5E, order-label char-spacing; and content 1
             (DOL) in-place literals: board self-name spacing, card '〒' drop,
             '<error>'->'오류'. See kwce/photoprints_rc6.py.
hardware-v10 = hardware-v9 with the same content 1 and content 2, fakesigned
             (WiiLink endpoints, IOS56, TMD region 4 kept). Not installed; real Wii untested.
Only contents 1 and 2 change. Content 1 changes -> lead Dolphin verification required.
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
from kwce.photoprints_rc6 import patch_content1, patch_layout  # noqa: E402
from build_photoprints import _lz_recompress  # noqa: E402

BASE = ROOT / 'workspace/channels/photoprints'
TITLE = '000100014843444a'
IOS56 = '0000000100000038'
LOCAL, HARDWARE = BASE / 'build-v14', BASE / 'hardware-v10'
LOCAL_WAD, HARDWARE_WAD = 'photoprints-ko-local-test.wad', 'photoprints-ko-hardware-test.wad'
CHANGED = [1, 2]
TMD_FAKESIGN = (0x1e2, 0x1e4)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def record_range(index):
    start = 0x1e4 + 36 * index
    return start + 8, start + 36


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


def _new_content2(c2_bytes, layout_rec_out):
    """Patch content 2's layout.arc.LZ; keep every other file byte-identical."""
    c2 = ChannelArchive(c2_bytes)
    lib = load_library()
    from libWiiPy.archive import decompress_lz77
    font = c2.get('font_rodan_28.brfna')
    raw = decompress_lz77(c2.get('layout.arc.LZ'))
    edited, rec = patch_layout(raw, font)
    layout_rec_out.update(rec)
    compact = ChannelArchive(edited).compact()
    comp = _lz_recompress(c2.get('layout.arc.LZ'), compact)
    c2 = ChannelArchive(c2.replace('layout.arc.LZ', comp))
    return c2.compact()


def build_common():
    """Return patched (content1_local, content1_hw, content2, records)."""
    _, lmeta, ltitle = _load(BASE / 'build-v13', LOCAL_WAD)
    _, hmeta, htitle = _load(BASE / 'hardware-v9', HARDWARE_WAD)
    if not lmeta.get('local_only') or lmeta.get('revision') != 13:
        raise ValueError('build-v13 scope differs')
    if hmeta.get('revision') != 9 or htitle.tmd.region != 4 or not htitle.get_is_fakesigned():
        raise ValueError('hardware-v9 identity differs')
    lc, hc = _contents(ltitle), _contents(htitle)
    if lc[2] != hc[2]:
        raise ValueError('build-v13 and hardware-v9 content 2 differ; cannot share the patch')
    layout_rec = {}
    new_c2 = _new_content2(lc[2], layout_rec)
    new_c1_local, c1rec = patch_content1(lc[1])
    new_c1_hw, c1rec_hw = patch_content1(hc[1])
    if c1rec['dol_literals'] != c1rec_hw['dol_literals']:
        raise ValueError('content 1 literal edits diverged between local and hardware')
    records = dict(content1=c1rec, content2=layout_rec,
                   content2_sha256=sha(new_c2),
                   content1_local_sha256=sha(new_c1_local), content1_hw_sha256=sha(new_c1_hw))
    return new_c1_local, new_c1_hw, new_c2, (lmeta, hmeta), records


def build_local(new_c1, new_c2, lmeta):
    _, _, title = _load(BASE / 'build-v13', LOCAL_WAD)
    before = _contents(title)
    tmd_before, ticket_before = title.tmd.dump(), title.ticket.dump()
    loop_before = local_reference_counts(title)
    title.set_content(new_c1, 1)
    title.set_content(new_c2, 2)
    wad = title.dump_wad()
    check = load_library().title.Title()
    check.load_wad(wad)
    after = _contents(check)
    if [i for i in range(len(before)) if after[i] != before[i]] != CHANGED:
        raise ValueError('build-v14 changed contents other than 1 and 2')
    if check.ticket.dump() != ticket_before or not _allowed(_changed_bytes(tmd_before, check.tmd.dump()), *map(record_range, CHANGED)):
        raise ValueError('build-v14 TMD/ticket change escaped the content 1/2 records')
    if local_reference_counts(check) != loop_before:
        raise ValueError('build-v14 loopback reference counts changed')
    manifest = dict(lmeta)
    for k in ('home_guide_v13', 'home_guide_runtime_verified'):
        manifest.pop(k, None)
    manifest.update(revision=14, source_build='build-v13', source_wad_sha256=lmeta['wad_sha256'],
                    wad_sha256=sha(wad), changed_contents_vs_source=CHANGED, tmd_region=check.tmd.region,
                    rc6_wave2=True, content_sha256={str(i): sha(after[i]) for i in CHANGED},
                    local_only=True, full_localization_complete=False, hardware_success_verified=False,
                    lead_dolphin_verification_required=True)
    return wad, manifest


def build_hardware(new_c1, new_c2, hmeta):
    _, _, title = _load(BASE / 'hardware-v9', HARDWARE_WAD)
    before = _contents(title)
    counts = local_reference_counts(title)
    tmd_before, ticket_before = title.tmd.dump(), title.ticket.dump()
    title.set_content(new_c1, 1)
    title.set_content(new_c2, 2)
    title.fakesign()
    wad = title.dump_wad()
    check = load_library().title.Title()
    check.load_wad(wad)
    if check.tmd.title_id.lower() != TITLE or check.tmd.ios_tid.lower() != IOS56 or check.tmd.region != 4 or not check.get_is_fakesigned():
        raise ValueError('hardware-v10 title/IOS/region/signature check failed')
    after = _contents(check)
    if [i for i in range(len(before)) if after[i] != before[i]] != CHANGED:
        raise ValueError('hardware-v10 changed contents other than 1 and 2')
    if local_reference_counts(check) != counts:
        raise ValueError('hardware-v10 service/loopback reference counts changed')
    changed = _changed_bytes(tmd_before, check.tmd.dump())
    if check.ticket.dump() != ticket_before or not _allowed(changed, TMD_FAKESIGN, *map(record_range, CHANGED)):
        raise ValueError('hardware-v10 TMD/ticket change escaped fakesign and the content 1/2 records')
    manifest = dict(hardware_candidate=True, hardware_success_verified=False, full_localization_complete=False,
                    local_only=False, revision=10, source='hardware-v9', source_wad_sha256=hmeta['wad_sha256'],
                    local_source='build-v14', source_revision=14, wad_sha256=sha(wad),
                    title_id=check.tmd.title_id.lower(), title_version=check.tmd.title_version,
                    ios=check.tmd.ios_tid.lower(), region=check.tmd.region, contents=len(before),
                    changed_contents_vs_source=CHANGED, rc6_wave2=True,
                    content_sha256={str(i): sha(after[i]) for i in CHANGED},
                    service_endpoints_kept=True, local_reference_counts=counts, fakesigned=True,
                    lead_dolphin_verification_required=True,
                    reason='RC6 wave-2: button centering, OK->확인, tilde, label spacing (content 2); '
                           'board self-name spacing, card 〒 drop, <error>->오류 (content 1)')
    return wad, manifest


def build():
    new_c1_local, new_c1_hw, new_c2, (lmeta, hmeta), records = build_common()
    local, local_meta = build_local(new_c1_local, new_c2, lmeta)
    hardware, hardware_meta = build_hardware(new_c1_hw, new_c2, hmeta)
    local_meta['rc6_fix_record'] = records['content1'] | {'content2': records['content2']['summary']}
    hardware_meta['rc6_fix_record'] = local_meta['rc6_fix_record']
    hardware_meta['local_source_wad_sha256'] = local_meta['wad_sha256']
    return (local, local_meta), (hardware, hardware_meta), records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify', action='store_true')
    args = ap.parse_args()
    (local, local_meta), (hardware, hardware_meta), records = build()
    outputs = ((LOCAL, LOCAL_WAD, local, local_meta), (HARDWARE, HARDWARE_WAD, hardware, hardware_meta))
    if args.verify:
        for folder, name, data, meta in outputs:
            if (folder / name).read_bytes() != data:
                raise ValueError(f'{folder.name} is not byte reproducible')
            if json.loads((folder / 'build-manifest.json').read_text(encoding='utf-8')) != json.loads(json.dumps(meta, ensure_ascii=False)):
                raise ValueError(f'{folder.name} manifest differs on regeneration')
        print('PASS: build-v14 and hardware-v10 reproduce byte-identically; only contents 1 and 2 changed '
              '(hardware-v10: fakesigned, WiiLink endpoints kept)')
        return
    if LOCAL.exists() or HARDWARE.exists():
        raise SystemExit('Existing Photo Prints output preserved')
    for folder, name, data, meta in outputs:
        folder.mkdir()
        (folder / name).write_bytes(data)
        (folder / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(build_v14=local_meta['wad_sha256'], hardware_v10=hardware_meta['wad_sha256'],
                          content2=records['content2']['summary'],
                          dol_literals=[d['va'] for d in records['content1']['dol_literals']]), ensure_ascii=False))


if __name__ == '__main__':
    main()

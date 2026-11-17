"""Photo Prints build-v15 (local) and hardware-v11 (candidate): restore the name-card phone header.

  .venv\\Scripts\\python.exe scripts\\build_photoprints_v15.py           # create both (refuses to overwrite)
  .venv\\Scripts\\python.exe scripts\\build_photoprints_v15.py --verify  # byte-identical regeneration check

The Mii name-card template arc/blyt/Ref_print_template_name_cardC.brlyt (content 2, layout.arc.LZ)
has two header text boxes that the channel copies into the order's INI (serviceData_1, Text="..."):
WiiAdrHead ('W i i 番 号', never translated) and TelNumHead. The WiiLink print server
(references/cam-server-ab059bc0/render.py) replaces exactly 'W i i 番 号' with 'Wii Number:' and
exactly '電話番号' with 'Phone Number:'; any other text is drawn as is with its Japanese font.
Revisions up to 14 translated TelNumHead to '전화번호', so the printed card lost the 'Phone Number:'
header (RC7 server-compatibility review, workspace/private/rc7-work/S3.md section 2).

build-v15    = build-v14 with that one txt1 section byte-identical to the stock Japanese channel.
hardware-v11 = hardware-v10 with the same content 2, fakesigned (WiiLink endpoints, IOS56, TMD region 4).
Only content 2 changes (boot-safe resource); content 1 and every other file are unchanged.
No NAND/SD writes, no Dolphin.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import ChannelArchive, layout_sections, load_library, rebuild_layout, textbox  # noqa: E402
from kwce.hardware import local_reference_counts  # noqa: E402
from build_photoprints import _lz_recompress  # noqa: E402

BASE = ROOT / 'workspace/channels/photoprints'
STOCK = BASE / 'originals/digicam-japan-v1024.wad'
TITLE = '000100014843444a'
IOS56 = '0000000100000038'
LOCAL, HARDWARE = BASE / 'build-v15', BASE / 'hardware-v11'
LOCAL_WAD, HARDWARE_WAD = 'photoprints-ko-local-test.wad', 'photoprints-ko-hardware-test.wad'
CHANGED = [2]
TMD_FAKESIGN = (0x1e2, 0x1e4)
LAYOUT = 'layout.arc.LZ'
BRLYT = 'arc/blyt/Ref_print_template_name_cardC.brlyt'
PANE = 'TelNumHead'
STOCK_TEXT = '電話番号'


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


def _layout_u8(content2):
    load_library()
    from libWiiPy.archive import decompress_lz77
    return decompress_lz77(ChannelArchive(content2).get(LAYOUT))


def _pane_index(sections, name):
    hits = [i for i, s in enumerate(sections) if (textbox(s) or ('',))[0] == name]
    if len(hits) != 1:
        raise ValueError(f'{name} found {len(hits)} times')
    return hits[0]


def restore_phone_header(content2, stock_content2):
    """Return (content 2 with the stock TelNumHead section, record)."""
    stock_sections = layout_sections(ChannelArchive(_layout_u8(stock_content2)).get(BRLYT))
    layout = ChannelArchive(_layout_u8(content2))
    sections = layout_sections(layout.get(BRLYT))
    i, j = _pane_index(sections, PANE), _pane_index(stock_sections, PANE)
    if i != j or len(sections) != len(stock_sections):
        raise ValueError('Name-card layout structure differs from the stock channel')
    if textbox(stock_sections[j])[1] != STOCK_TEXT:
        raise ValueError('Stock TelNumHead text differs')
    before = textbox(sections[i])[1]
    if before == STOCK_TEXT:
        raise ValueError('TelNumHead already carries the stock text')
    sections[i] = stock_sections[j]
    new_brlyt = rebuild_layout(layout.get(BRLYT), sections)
    edited = ChannelArchive(layout.replace(BRLYT, new_brlyt)).compact()
    check = ChannelArchive(edited)
    if layout_sections(check.get(BRLYT))[i] != stock_sections[j]:
        raise ValueError('TelNumHead section did not round-trip')
    if any(check.get(n) != layout.get(n) for n in layout.files if n != BRLYT):
        raise ValueError('Another layout file changed')
    outer = ChannelArchive(content2)
    comp = _lz_recompress(outer.get(LAYOUT), edited)
    new = ChannelArchive(outer.replace(LAYOUT, comp)).compact()
    after = ChannelArchive(new)
    if set(after.files) != set(outer.files) or any(after.get(n) != outer.get(n) for n in outer.files if n != LAYOUT):
        raise ValueError('A content 2 file other than layout.arc.LZ changed')
    return new, dict(file=f'{LAYOUT}:{BRLYT}', pane=PANE, section_index=i, before=before, after=STOCK_TEXT,
                     section_sha256=sha(stock_sections[j]), server_rule='cam-server render.py: "電話番号" -> "Phone Number:"')


def build():
    lib = load_library()
    _, lmeta, ltitle = _load(BASE / 'build-v14', LOCAL_WAD)
    _, hmeta, htitle = _load(BASE / 'hardware-v10', HARDWARE_WAD)
    if lmeta.get('revision') != 14 or not lmeta.get('local_only'):
        raise ValueError('build-v14 scope differs')
    if hmeta.get('revision') != 10 or htitle.tmd.region != 4 or not htitle.get_is_fakesigned():
        raise ValueError('hardware-v10 identity differs')
    lc, hc = _contents(ltitle), _contents(htitle)
    if lc[2] != hc[2]:
        raise ValueError('build-v14 and hardware-v10 content 2 differ; cannot share the patch')
    stock = lib.title.Title()
    stock.load_wad(STOCK.read_bytes())
    new_c2, rec = restore_phone_header(lc[2], stock.get_content_by_index(2))
    outputs = []
    for folder_src, name, meta_src, title, hardware in ((BASE / 'build-v14', LOCAL_WAD, lmeta, ltitle, False),
                                                        (BASE / 'hardware-v10', HARDWARE_WAD, hmeta, htitle, True)):
        before = _contents(title)
        counts = local_reference_counts(title)
        tmd_before, ticket_before = title.tmd.dump(), title.ticket.dump()
        title.set_content(new_c2, 2)
        if hardware:
            title.fakesign()
        wad = title.dump_wad()
        check = lib.title.Title()
        check.load_wad(wad)
        after = _contents(check)
        if [i for i in range(len(before)) if after[i] != before[i]] != CHANGED:
            raise ValueError(f'{name}: contents other than 2 changed')
        if local_reference_counts(check) != counts:
            raise ValueError(f'{name}: service/loopback reference counts changed')
        ranges = (TMD_FAKESIGN, record_range(2)) if hardware else (record_range(2),)
        if check.ticket.dump() != ticket_before or not _allowed(_changed_bytes(tmd_before, check.tmd.dump()), *ranges):
            raise ValueError(f'{name}: TMD/ticket change escaped the content 2 record')
        if hardware and (check.tmd.region != 4 or not check.get_is_fakesigned()):
            raise ValueError('hardware-v11 region/signature check failed')
        meta = dict(meta_src)
        meta.pop('rc6_fix_record', None)
        meta.pop('local_source_wad_sha256', None)
        common = dict(wad_sha256=sha(wad), changed_contents_vs_source=CHANGED, rc7_server_compat=rec,
                      content_sha256={'2': sha(after[2])}, full_localization_complete=False,
                      hardware_success_verified=False)
        if hardware:
            meta.update(revision=11, source='hardware-v10', source_wad_sha256=meta_src['wad_sha256'],
                        local_source='build-v15', source_revision=15, fakesigned=True, region=check.tmd.region,
                        reason='RC7 server-compatibility review: name-card TelNumHead back to the stock '
                               '電話番号 so the WiiLink print server writes "Phone Number:" (content 2 only)',
                        lead_dolphin_verification_required=False, **common)
        else:
            meta.update(revision=15, source_build='build-v14', source_wad_sha256=meta_src['wad_sha256'],
                        tmd_region=check.tmd.region, local_only=True, lead_dolphin_verification_required=False,
                        **common)
        outputs.append((LOCAL if not hardware else HARDWARE, name, wad, meta))
    outputs[1][3]['local_source_wad_sha256'] = outputs[0][3]['wad_sha256']
    return outputs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify', action='store_true')
    args = ap.parse_args()
    outputs = build()
    if args.verify:
        for folder, name, data, meta in outputs:
            if (folder / name).read_bytes() != data:
                raise ValueError(f'{folder.name} is not byte reproducible')
            if json.loads((folder / 'build-manifest.json').read_text(encoding='utf-8')) != json.loads(json.dumps(meta, ensure_ascii=False)):
                raise ValueError(f'{folder.name} manifest differs on regeneration')
        print('PASS: build-v15 and hardware-v11 reproduce byte-identically; only content 2 changed '
              '(TelNumHead = stock 電話番号; hardware-v11 fakesigned, WiiLink endpoints kept)')
        return
    if LOCAL.exists() or HARDWARE.exists():
        raise SystemExit('Existing Photo Prints output preserved')
    for folder, name, data, meta in outputs:
        folder.mkdir()
        (folder / name).write_bytes(data)
        (folder / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(build_v15=outputs[0][3]['wad_sha256'], hardware_v11=outputs[1][3]['wad_sha256'],
                          change=outputs[0][3]['rc7_server_compat']), ensure_ascii=False))


if __name__ == '__main__':
    main()

"""Food hardware-v14: hardware-v12 plus overlay panes moved onto the Korean blank runs.

Derived from the preserved hardware-v12 WAD so every texture stays byte-identical
(regenerating content 2 on Linux redraws 14 label textures differently from the
Windows build; that regenerated candidate is hardware-v13 and is not used).
Only content 2 changes, and in it only three layouts. See kwce/food_overlay_align.py.

python scripts/build_food_overlay_fix.py [--reproduce]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import ChannelArchive, load_library
from kwce import food_overlay_align, food_textfit

PARENT, REVISION = 12, 14
WAD = 'food-ko-hardware-test.wad'
LAYOUTS = {'Dtest/DtestDialog.arc': {'Dialog/blyt/dialogue_layout.brlyt'},
           'Dtest/DtestOrder.arc': {'Order/blyt/08_m_layout.brlyt', 'Order/blyt/11_m_layout.brlyt'}}


def build():
    base = ROOT / 'workspace/channels/food'
    parent = base / f'hardware-v{PARENT}'
    meta = json.loads((parent / 'build-manifest.json').read_text(encoding='utf-8'))
    raw = (parent / WAD).read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta['wad_sha256']: raise ValueError('Food hardware-v12 parent differs')
    lib = load_library()
    stock = lib.title.Title(); stock.load_wad((base / 'originals/food-japan-v512.wad').read_bytes())
    title = lib.title.Title(); title.load_wad(raw)
    count = len(title.tmd.content_records)
    original = [title.get_content_by_index(i) for i in range(count)]
    content2, record = food_overlay_align.align(original[2], stock.get_content_by_index(2),
                                                food_textfit.stock_metrics(stock.get_content_by_index(3)),
                                                food_textfit.korean_metrics())
    before, after = ChannelArchive(original[2]), ChannelArchive(content2)
    if set(before.files) != set(after.files): raise ValueError('Resource file set changed')
    for name in before.files:
        if before.get(name) == after.get(name): continue
        a, b = ChannelArchive(before.get(name)), ChannelArchive(after.get(name))
        changed = {f for f in a.files if a.get(f) != b.get(f)}
        if set(a.files) != set(b.files) or changed != LAYOUTS.get(name): raise ValueError('Unexpected resource change in ' + name)
    title.set_content(content2, 2)
    wad = title.dump_wad()
    check = lib.title.Title(); check.load_wad(wad)
    if [i for i in range(count) if check.get_content_by_index(i) != original[i]] != [2]: raise ValueError('Unexpected content change')
    if (check.tmd.region, check.tmd.title_version, check.tmd.title_id) != (title.tmd.region, title.tmd.title_version, title.tmd.title_id):
        raise ValueError('TMD identity changed')
    return wad, meta, record


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--reproduce', action='store_true'); args = ap.parse_args()
    out = ROOT / f'workspace/channels/food/hardware-v{REVISION}'
    wad, meta, record = build()
    digest = hashlib.sha256(wad).hexdigest()
    if args.reproduce:
        if (out / WAD).read_bytes() != wad: raise SystemExit('Food hardware-v14 reproduction differs')
        print('PASS: Food hardware-v14 reproduced byte-identically'); return
    if out.exists(): raise SystemExit('Existing Food hardware-v14 preserved')
    meta = dict(meta)
    meta.update(revision=REVISION, parent_revision=PARENT, parent_wad_sha256=meta['wad_sha256'], wad_sha256=digest,
                changed_from_parent=[2], overlay_alignment=record, hardware_success_verified=False)
    out.mkdir(parents=True); (out / WAD).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'PASS: Food hardware-v14 from v12, content 2 layouts only ({len(record)} panes moved), wad {digest[:12]}')


if __name__ == '__main__':
    main()

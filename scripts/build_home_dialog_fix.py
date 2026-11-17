"""HOME dialog size (+ Food HOME projection) fixes: kwce/home_dialog_fix.py.

  python scripts/build_home_dialog_fix.py --channel food|nintendo [--reproduce]
food: hardware-v17 -> hardware-v18 (content 1, LZ11); nintendo: build-v19 -> build-v20 (content 1).
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce import home_dialog_fix as fix
from kwce.wiiroom_formats import decompress_lz11, compress_lz11_optimal

PINS = dict(food=('hardware-v17', 'hardware-v18', 'food-ko-hardware-test.wad', fix.FOOD, True),
            nintendo=('build-v19', 'build-v20', 'nintendo-ko-ui-test.wad', fix.NINTENDO, False))


def build(channel):
    parent, child, name, spec, compressed = PINS[channel]
    src = ROOT / f'workspace/channels/{channel}/{parent}'
    meta = json.loads((src / 'build-manifest.json').read_text(encoding='utf-8'))
    raw = (src / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta['wad_sha256']: raise ValueError('Parent WAD differs')
    lib = load_library(); title = lib.title.Title(); title.load_wad(raw)
    count = len(title.tmd.content_records); original = [title.get_content_by_index(i) for i in range(count)]
    exe = decompress_lz11(original[1]) if compressed else original[1]
    edited, record = fix.patch(exe, spec)
    packed = compress_lz11_optimal(edited) if compressed else edited
    if compressed and decompress_lz11(packed) != edited: raise ValueError('LZ11 roundtrip')
    title.set_content(packed, 1); wad = title.dump_wad()
    check = lib.title.Title(); check.load_wad(wad)
    if [i for i in range(count) if check.get_content_by_index(i) != original[i]] != [1]: raise ValueError('Unexpected content change')
    meta = dict(meta); meta.update(revision=int(child.rsplit('v', 1)[1]), parent_revision=int(parent.rsplit('v', 1)[1]),
                                   parent_wad_sha256=meta['wad_sha256'], wad_sha256=hashlib.sha256(wad).hexdigest(),
                                   changed_from_parent=[1], runtime_verified=False, home_dialog_fix=record)
    return child, name, wad, meta


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--channel', choices=sorted(PINS), required=True)
    ap.add_argument('--reproduce', action='store_true'); a = ap.parse_args()
    child, name, wad, meta = build(a.channel); out = ROOT / f'workspace/channels/{a.channel}/{child}'
    if a.reproduce:
        if (out / name).read_bytes() != wad: raise SystemExit('reproduction differs')
        print(f'PASS: {a.channel} {child} reproduced byte-identically'); return
    if out.exists(): raise SystemExit('Existing build preserved')
    out.mkdir(parents=True); (out / name).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: {a.channel} {child}, content 1 only, wad {meta["wad_sha256"][:16]}')


if __name__ == '__main__': main()

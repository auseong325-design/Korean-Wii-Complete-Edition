"""Food hardware-v17 = hardware-v16 + showcase mode (kwce/food_showcase.py).

Orders (webApi_order_done) and shop requests (webApi_inquiry_done) complete on the console only;
two Shift-JIS order texts become ASCII; the item help dialog uses 「」. Contents 1 and 2 change.
  python scripts/build_food_showcase.py [--reproduce]
  python scripts/build_food_showcase.py --diagnostic   LOCAL ONLY copy with host 127.0.0.1:8080 (proxy trace)
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce import food_showcase as fs
from kwce.wiiroom_formats import decompress_lz11, compress_lz11_optimal

PARENT, CHILD = 'hardware-v16', 'hardware-v17'


def build(diagnostic=False):
    src = ROOT / f'workspace/channels/food/{PARENT}'
    meta = json.loads((src / 'build-manifest.json').read_text(encoding='utf-8'))
    wad_path = next(src.glob('*.wad')); raw = wad_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta['wad_sha256']: raise ValueError('Parent WAD differs')
    lib = load_library(); title = lib.title.Title(); title.load_wad(raw)
    count = len(title.tmd.content_records); original = [title.get_content_by_index(i) for i in range(count)]
    exe = decompress_lz11(original[1])
    patched, record = fs.patch(exe, hashlib.sha256(exe).hexdigest())
    patched, sjis = fs.sjis_text(patched)
    if diagnostic:
        import re
        b = bytearray(patched)
        for m in list(re.finditer(rb'food\.wiilink24\.com[^\0]*', bytes(b))):
            s = m.group().replace(b'food.wiilink24.com', b'127.0.0.1:8080', 1); b[m.start():m.end()] = s + bytes(m.end() - m.start() - len(s))
        patched = bytes(b)
    packed = compress_lz11_optimal(patched)
    if decompress_lz11(packed) != patched: raise ValueError('LZ11 roundtrip')
    title.set_content(packed, 1); title.set_content(fs.dialog_quotes(original[2]), 2)
    wad = title.dump_wad(); check = lib.title.Title(); check.load_wad(wad)
    if [i for i in range(count) if check.get_content_by_index(i) != original[i]] != [1, 2]: raise ValueError('Unexpected content change')
    meta = dict(meta); meta.update(revision=17, parent_revision=16, parent_wad_sha256=meta['wad_sha256'], wad_sha256=hashlib.sha256(wad).hexdigest(),
                                   changed_from_parent=[1, 2], runtime_verified=False,
                                   showcase=dict(record, executable_sha256=hashlib.sha256(patched).hexdigest(), sjis_ascii=sjis, dialog_quotes=True))
    if diagnostic: meta.update(diagnostic='LOCAL ONLY: host 127.0.0.1:8080; never package')
    return wad_path.name, wad, meta


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--reproduce', action='store_true'); ap.add_argument('--diagnostic', action='store_true')
    a = ap.parse_args(); name, wad, meta = build(a.diagnostic)
    if a.diagnostic:
        n = 3
        while (ROOT / f'workspace/channels/food/diagnostic-proxy-v{n}').exists() and not a.reproduce: n += 1
        out = ROOT / f'workspace/channels/food/diagnostic-proxy-v{n}'
    else:
        out = ROOT / 'workspace/channels/food' / CHILD
    if a.reproduce:
        if (out / name).read_bytes() != wad: raise SystemExit('reproduction differs')
        print(f'PASS: food {out.name} reproduced byte-identically'); return
    if out.exists(): raise SystemExit('Existing build preserved')
    out.mkdir(parents=True); (out / name).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: food {out.name}, contents [1, 2], wad {meta["wad_sha256"][:16]}')


if __name__ == '__main__': main()

"""Derive the 2026-11-16 text/display fix builds (kwce/text_fixes_1116.py) from their parent WADs.

python scripts/build_text_fixes.py --channel forecast|news|nintendo|food|wiiroom|mii-contest [--reproduce]
Only the contents a fix names may change; everything else is checked byte-identical to the parent.
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce import text_fixes_1116 as fixes


def build(channel):
    parent, child, fix = fixes.STEPS[channel]
    src = ROOT / f'workspace/channels/{channel}/{parent}'
    meta = json.loads((src / 'build-manifest.json').read_text(encoding='utf-8'))
    wad_path = next(src.glob('*.wad')); raw = wad_path.read_bytes()
    expected = meta.get('wad_sha256') or next(iter(meta.get('wads', {}).values()), {}).get('sha256')
    if hashlib.sha256(raw).hexdigest() != expected: raise ValueError('Parent WAD differs from its manifest')
    lib = load_library(); title = lib.title.Title(); title.load_wad(raw)
    count = len(title.tmd.content_records); original = [title.get_content_by_index(i) for i in range(count)]
    changed, record = fix(original)
    for index, data in changed.items(): title.set_content(data, index)
    wad = title.dump_wad(); check = lib.title.Title(); check.load_wad(wad)
    diff = [i for i in range(count) if check.get_content_by_index(i) != original[i]]
    if diff != sorted(changed): raise ValueError(f'Unexpected content change {diff}')
    if check.tmd.region != title.tmd.region: raise ValueError('Region changed')
    meta = dict(meta); digest = hashlib.sha256(wad).hexdigest()
    meta.update(revision=int(child.split('-v')[1]), parent_revision=int(parent.split('-v')[1]), parent_wad_sha256=expected,
                wad_sha256=digest, changed_from_parent=diff, runtime_verified=False, text_fix_1116=record)
    if 'wads' in meta:
        meta['wads'] = {k: dict(v, sha256=digest) for k, v in meta['wads'].items()}
    return wad_path.name, wad, meta, child


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--channel', choices=sorted(fixes.STEPS), required=True)
    ap.add_argument('--reproduce', action='store_true'); a = ap.parse_args()
    name, wad, meta, child = build(a.channel); out = ROOT / f'workspace/channels/{a.channel}/{child}'
    if a.reproduce:
        if (out / name).read_bytes() != wad: raise SystemExit(f'{a.channel} {child} reproduction differs')
        print(f'PASS: {a.channel} {child} reproduced byte-identically'); return
    if out.exists(): raise SystemExit('Existing build preserved')
    out.mkdir(parents=True); (out / name).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: {a.channel} {child}, contents {meta["changed_from_parent"]}, wad {meta["wad_sha256"][:16]}')


if __name__ == '__main__': main()

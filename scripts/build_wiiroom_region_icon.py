"""Wii Room v70 = v69 + Korean peninsula settings region icon (kwce/wiiroom_region_icon.py). Content 2 only.

  python scripts/build_wiiroom_region_icon.py [--reproduce]
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce import wiiroom_region_icon as icon

PARENT, CHILD, WAD = 69, 70, 'wiiroom-ko-local-test.wad'


def build():
    src = ROOT / f'workspace/channels/wiiroom/build-v{PARENT}'
    meta = json.loads((src / 'build-manifest.json').read_text(encoding='utf-8'))
    raw = (src / WAD).read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta['wad_sha256']: raise ValueError('Parent WAD differs')
    lib = load_library(); title = lib.title.Title(); title.load_wad(raw)
    count = len(title.tmd.content_records); original = [title.get_content_by_index(i) for i in range(count)]
    content2, record = icon.patch_content2(original[2])
    title.set_content(content2, 2); wad = title.dump_wad()
    check = lib.title.Title(); check.load_wad(wad)
    if [i for i in range(count) if check.get_content_by_index(i) != original[i]] != [2]: raise ValueError('Unexpected content change')
    meta = dict(meta); meta.update(revision=CHILD, parent_revision=PARENT, parent_wad_sha256=meta['wad_sha256'],
                                   wad_sha256=hashlib.sha256(wad).hexdigest(), changed_from_parent=[2], runtime_verified=False,
                                   region_icon=record)
    return wad, meta


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--reproduce', action='store_true'); a = ap.parse_args()
    wad, meta = build(); out = ROOT / f'workspace/channels/wiiroom/build-v{CHILD}'
    if a.reproduce:
        if (out / WAD).read_bytes() != wad: raise SystemExit('reproduction differs')
        print(f'PASS: wiiroom v{CHILD} reproduced byte-identically'); return
    if out.exists(): raise SystemExit('Existing build preserved')
    out.mkdir(parents=True); (out / WAD).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: wiiroom v{CHILD}, content 2 only, wad {meta["wad_sha256"][:16]}')


if __name__ == '__main__': main()

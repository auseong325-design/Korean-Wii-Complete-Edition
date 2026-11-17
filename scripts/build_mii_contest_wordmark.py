"""Mii Contest build-v32 from build-v31: block-face banner syllables (content 0 only).

python scripts/build_mii_contest_wordmark.py [--reproduce]
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce import mii_contest_wordmark_v32 as wm

PARENT, REVISION, WAD = 31, 32, 'mii-contest-ko-ui-test.wad'


def build():
    parent = ROOT / f'workspace/channels/mii-contest/build-v{PARENT}'
    meta = json.loads((parent / 'build-manifest.json').read_text(encoding='utf-8'))
    raw = (parent / WAD).read_bytes(); pinned = meta.get('wad_sha256') or meta['wads']['ui']['sha256']
    if hashlib.sha256(raw).hexdigest() != pinned: raise ValueError('Mii Contest v31 parent differs')
    lib = load_library(); title = lib.title.Title(); title.load_wad(raw)
    count = len(title.tmd.content_records); original = [title.get_content_by_index(i) for i in range(count)]
    c0, record = wm.banner(original[0]); title.set_content(c0, 0); wad = title.dump_wad()
    check = lib.title.Title(); check.load_wad(wad)
    if [i for i in range(count) if check.get_content_by_index(i) != original[i]] != [0]: raise ValueError('Unexpected content change')
    meta = dict(meta); meta.update(revision=REVISION, parent_revision=PARENT, parent_wad_sha256=pinned,
                                   wad_sha256=hashlib.sha256(wad).hexdigest(), changed_from_parent=[0], banner_wordmark_v32=record)
    return wad, meta


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--reproduce', action='store_true'); a = ap.parse_args()
    out = ROOT / f'workspace/channels/mii-contest/build-v{REVISION}'; wad, meta = build()
    if a.reproduce:
        if (out / WAD).read_bytes() != wad: raise SystemExit('Mii Contest v32 reproduction differs')
        print('PASS: Mii Contest v32 reproduced byte-identically'); return
    if out.exists(): raise SystemExit('Existing Mii Contest build preserved')
    out.mkdir(parents=True); (out / WAD).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: Mii Contest v32 from v31, content 0 (6 banner letters), wad {meta["wad_sha256"][:12]}')


if __name__ == '__main__': main()

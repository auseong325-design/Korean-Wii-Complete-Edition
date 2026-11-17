"""Nintendo Channel build-v25 -> build-v26: even, faster flip-in of the Korean opening logo
(kwce/nintendo_opening_timing.py). Content 5 only (layout/option.arc opening_00_in/_loop.brlan).

  python scripts/build_nintendo_opening_v26.py [--reproduce]
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.nintendo_opening_timing import opening_timing, STARTS, DURATION

BASE = ROOT / 'workspace/channels/nintendo'
PARENT, CHILD, NAME = 'build-v25', 'build-v26', 'nintendo-ko-ui-test.wad'


def build():
    meta = json.loads((BASE / PARENT / 'build-manifest.json').read_text(encoding='utf-8'))
    raw = (BASE / PARENT / NAME).read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta['wad_sha256']:
        raise ValueError('Parent WAD differs')
    lib = load_library(); title = lib.title.Title(); title.load_wad(raw)
    count = len(title.tmd.content_records); original = [title.get_content_by_index(i) for i in range(count)]
    c5, record = opening_timing(original[5])
    title.set_content(c5, 5)
    wad = title.dump_wad(); check = lib.title.Title(); check.load_wad(wad)
    if [i for i in range(count) if check.get_content_by_index(i) != original[i]] != [5]:
        raise ValueError('Unexpected content change')
    meta = dict(meta)
    meta.update(revision=26, parent_revision=25, parent_wad_sha256=meta['wad_sha256'], wad_sha256=hashlib.sha256(wad).hexdigest(),
                changed_from_parent=[5], runtime_verified=False,
                opening_timing=dict(starts=list(STARTS), duration_frames=DURATION, panes=record,
                                    why='letters settled before the channel switches to opening_00_out (user report 2026-11-17)'))
    if isinstance(meta.get('content_sha256'), dict):
        meta['content_sha256'] = dict(meta['content_sha256'], **{'5': hashlib.sha256(c5).hexdigest()})
    if 'wad_size' in meta:
        meta['wad_size'] = len(wad)
    if isinstance(meta.get('wads'), dict) and 'personal' in meta['wads']:
        meta['wads'] = dict(meta['wads'], personal=dict(meta['wads']['personal'], sha256=meta['wad_sha256'], size=len(wad)))
    return wad, meta


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--reproduce', action='store_true'); a = ap.parse_args()
    wad, meta = build(); out = BASE / CHILD
    if a.reproduce:
        if (out / NAME).read_bytes() != wad: raise SystemExit('reproduction differs')
        print('PASS: nintendo build-v26 reproduced byte-identically'); return
    if out.exists(): raise SystemExit('Existing build preserved')
    out.mkdir(parents=True); (out / NAME).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: nintendo build-v26, contents [5], wad {meta["wad_sha256"][:16]}')


if __name__ == '__main__':
    main()

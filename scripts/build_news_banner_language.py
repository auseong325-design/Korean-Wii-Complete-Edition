"""News v31 = v30 + banner/icon scripts use the saved news language (kwce/news_banner_language.py).

  python scripts/build_news_banner_language.py [--reproduce]
Contents 4 and 5 change; everything else is byte-identical to v30.
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce import news_banner_language as nbl

PARENT, CHILD, WAD = 30, 31, 'news-ko-personal.wad'


def build():
    src = ROOT / f'workspace/channels/news/build-v{PARENT}'
    meta = json.loads((src / 'build-manifest.json').read_text(encoding='utf-8'))
    raw = (src / WAD).read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta['wad_sha256']: raise ValueError('Parent WAD differs')
    lib = load_library(); title = lib.title.Title(); title.load_wad(raw)
    count = len(title.tmd.content_records); original = [title.get_content_by_index(i) for i in range(count)]
    changed, record = nbl.patch_contents(original)
    for index, data in changed.items(): title.set_content(data, index)
    wad = title.dump_wad(); check = lib.title.Title(); check.load_wad(wad)
    if [i for i in range(count) if check.get_content_by_index(i) != original[i]] != sorted(changed): raise ValueError('Unexpected content change')
    meta = dict(meta); meta.update(revision=CHILD, parent_revision=PARENT, parent_wad_sha256=meta['wad_sha256'],
                                   wad_sha256=hashlib.sha256(wad).hexdigest(), changed_from_parent=sorted(changed),
                                   runtime_verified=False, banner_language=record)
    if isinstance(meta.get('wads'), dict) and 'personal' in meta['wads']:   # export_rc_hardware reads this pin first
        meta['wads'] = dict(meta['wads'], personal=dict(meta['wads']['personal'], sha256=meta['wad_sha256'], size=len(wad)))
    return wad, meta


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--reproduce', action='store_true'); a = ap.parse_args()
    wad, meta = build(); out = ROOT / f'workspace/channels/news/build-v{CHILD}'
    if a.reproduce:
        if (out / WAD).read_bytes() != wad: raise SystemExit('reproduction differs')
        print(f'PASS: news v{CHILD} reproduced byte-identically'); return
    if out.exists(): raise SystemExit('Existing build preserved')
    out.mkdir(parents=True); (out / WAD).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: news v{CHILD}, contents {meta["changed_from_parent"]}, wad {meta["wad_sha256"][:16]}')


if __name__ == '__main__': main()

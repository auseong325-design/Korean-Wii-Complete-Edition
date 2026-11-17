"""News v27 (from v25: fallback path) and v28 (from v27: universal time from the console clock).

Only content 1 changes. v26 (branch diagnostic) is not an ancestor. --reproduce rebuilds in
memory and compares with the preserved WAD.
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.news_utc import patch, patch_universal

STEPS = {27: (25, patch, 'utc_fallback'), 28: (27, lambda raw, sha: patch_universal(raw, sha, unix_epoch=False), 'utc_universal'),
         29: (27, patch_universal, 'utc_universal')}   # 28: wrong epoch (unused)


def build(REVISION):
    PARENT, fix, key = STEPS[REVISION]
    previous = ROOT / f'workspace/channels/news/build-v{PARENT}'
    meta = json.loads((previous / 'build-manifest.json').read_text(encoding='utf-8'))
    raw = (previous / 'news-ko-personal.wad').read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta['wads']['personal']['sha256']: raise ValueError('News parent WAD differs')
    lib = load_library(); title = lib.title.Title(); title.load_wad(raw)
    count = len(title.tmd.content_records)
    original = [title.get_content_by_index(i) for i in range(count)]
    pins = json.loads((ROOT / f'configs/news-utc-v{REVISION}.json').read_text())
    exe, record = fix(original[1], pins['parent_executable_sha256'])
    title.set_content(exe, 1); wad = title.dump_wad()
    check = lib.title.Title(); check.load_wad(wad)
    changed = [i for i in range(count) if original[i] != check.get_content_by_index(i)]
    if changed != [1]: raise ValueError('News UTC fix changed unexpected content')
    meta.update(revision=REVISION, parent_revision=PARENT, installed_variant='personal',
                wads=dict(personal=dict(file='news-ko-personal.wad', sha256=hashlib.sha256(wad).hexdigest())),
                wad_sha256=hashlib.sha256(wad).hexdigest(), changed_from_parent=[1],
                live_service_verified=False)
    meta[key] = record
    return wad, meta, record


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--reproduce', action='store_true')
    ap.add_argument('--revision', type=int, choices=sorted(STEPS), default=27); a = ap.parse_args(); REVISION = a.revision
    out = ROOT / f'workspace/channels/news/build-v{REVISION}'
    wad, meta, record = build(REVISION)
    if a.reproduce:
        if (out / 'news-ko-personal.wad').read_bytes() != wad: raise SystemExit(f'News v{REVISION} reproduction differs')
        print(f'PASS: News v{REVISION} reproduced byte-identically'); return
    if out.exists(): raise SystemExit(f'News v{REVISION} preserved')
    out.mkdir(parents=True); (out / 'news-ko-personal.wad').write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: News v{REVISION}, only executable content changed;', record['bytes'], 'bytes at', record.get('cave') or record['function'],
          'wad', hashlib.sha256(wad).hexdigest()[:16])


if __name__ == '__main__': main()

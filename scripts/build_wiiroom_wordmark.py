"""Wii Room build-v66 (from hardware v60) / build-v67 (from local v61): Hangul wordmark candidate K.

Contents 0 and 2 change (wordmark textures only); the executable and all other contents are
byte-identical to the parent. python scripts/build_wiiroom_wordmark.py --revision 66|67 [--reproduce]
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce import wiiroom_wordmark_v62 as wm

PARENTS = {62: 60, 64: 60, 66: 60, 67: 61}   # 62 small glyphs, 64 wide gaps (both unused); 66 hardware, 67 local
WAD = 'wiiroom-ko-local-test.wad'


def build(revision):
    wm.FIT = revision != 62; wm.TIGHT = revision >= 66
    parent = ROOT / f'workspace/channels/wiiroom/build-v{PARENTS[revision]}'
    meta = json.loads((parent / 'build-manifest.json').read_text(encoding='utf-8'))
    raw = (parent / WAD).read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta['wad_sha256']: raise ValueError('Wii Room parent differs')
    lib = load_library(); title = lib.title.Title(); title.load_wad(raw)
    count = len(title.tmd.content_records); original = [title.get_content_by_index(i) for i in range(count)]
    c0, banner_record = wm.banner(original[0]); c2, resource_record = wm.resources(original[2])
    if len(c2) != len(original[2]): raise ValueError('Content 2 size changed')
    title.set_content(c0, 0); title.set_content(c2, 2); wad = title.dump_wad()
    check = lib.title.Title(); check.load_wad(wad)
    if [i for i in range(count) if check.get_content_by_index(i) != original[i]] != [0, 2]: raise ValueError('Unexpected content change')
    meta = dict(meta); meta.update(revision=revision, parent_revision=PARENTS[revision], parent_wad_sha256=meta['wad_sha256'],
                                   wad_sha256=hashlib.sha256(wad).hexdigest(), changed_from_parent=[0, 2],
                                   wordmark_v62=dict(font='Noto Sans CJK KR Black', font_sha256=wm.FONT_SHA256, narrow=wm.NARROW,
                                                     banner=banner_record, resources=resource_record), runtime_verified=False)
    return wad, meta


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--revision', type=int, choices=sorted(PARENTS), required=True)
    ap.add_argument('--reproduce', action='store_true'); a = ap.parse_args()
    out = ROOT / f'workspace/channels/wiiroom/build-v{a.revision}'; wad, meta = build(a.revision)
    if a.reproduce:
        if (out / WAD).read_bytes() != wad: raise SystemExit('Wii Room wordmark reproduction differs')
        print(f'PASS: Wii Room v{a.revision} reproduced byte-identically'); return
    if out.exists(): raise SystemExit('Existing Wii Room build preserved')
    out.mkdir(parents=True); (out / WAD).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: Wii Room v{a.revision} from v{PARENTS[a.revision]}, contents 0 and 2 (wordmark textures), wad {meta["wad_sha256"][:12]}')


if __name__ == '__main__': main()

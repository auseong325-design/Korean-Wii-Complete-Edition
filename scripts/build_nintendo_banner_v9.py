"""Nintendo Channel wordmark v9: build-v9 (from build-v4) and access-build-v10 (from access-build-v5).
--revision 10..13 make build-v10..v13 / access-build-v11..v14 the same way (13: ink-based word space).
--revision 14 makes build-v14 / access-build-v15: revision 13 + the Wii Menu icon pane the channel
script shows on a Korean console (P_logoJ_00 <-> P_logoE_00), so the icon shows the Korean wordmark.
--revision 15 makes build-v15 / access-build-v16: revision 14 + heavier, tighter lettering on the banner,
the icon and the in-channel opening (candidate H; final choice is the lead's/user's).

Changes content 0 (Wii Menu banner + icon: one Korean lettering, icon KOR group) and content 5
(the in-channel opening logo layout/option.arc opening_00 in the same lettering). No NAND/SD
installation. Existing build numbers are never overwritten; --reproduce rebuilds in memory and
compares byte for byte with the saved WADs.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.nintendo_menu_art_v9 import korean_menu_art, korean_opening


def sha(data):
    return hashlib.sha256(data).hexdigest()


OUTPUTS = {9: ('build-v9', 'access-build-v10'), 10: ('build-v10', 'access-build-v11'), 11: ('build-v11', 'access-build-v12'),
           12: ('build-v12', 'access-build-v13'), 13: ('build-v13', 'access-build-v14'),
           14: ('build-v14', 'access-build-v15'), 15: ('build-v15', 'access-build-v16')}


def build(lib, source_wad, revision):
    title = lib.title.Title()
    title.load_wad(source_wad.read_bytes())
    before = [title.get_content_by_index(i) for i in range(len(title.tmd.content_records))]
    content0, menu = korean_menu_art(before[0], revision)
    content5, opening = korean_opening(before[5], revision)
    title.set_content(content0, 0)
    title.set_content(content5, 5)
    wad = title.dump_wad()
    check = lib.title.Title()
    check.load_wad(wad)
    changed = [i for i in range(len(before)) if check.get_content_by_index(i) != before[i]]
    if changed != [0, 5]:
        raise ValueError(f'Changes escaped the wordmark contents: {changed}')
    return wad, dict(menu_art=menu, opening=opening, changed_content_indices=changed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reproduce', action='store_true')
    ap.add_argument('--revision', type=int, choices=sorted(OUTPUTS), default=9)
    args = ap.parse_args()
    root = ROOT / 'workspace/channels/nintendo'
    ui_name, test_name = OUTPUTS[args.revision]
    ui_dir, test_dir = root / ui_name, root / test_name
    lib = load_library()
    ui_bytes, ui_rec = build(lib, root / 'build-v4/nintendo-ko-ui-test.wad', args.revision)
    test_bytes, test_rec = build(lib, root / 'access-build-v5/nintendo-local-test.wad', args.revision)
    if args.reproduce:
        same = ((ui_dir / 'nintendo-ko-ui-test.wad').read_bytes() == ui_bytes and
                (test_dir / 'nintendo-local-test.wad').read_bytes() == test_bytes)
        print(json.dumps({'reproduced_byte_identical': same, 'build': sha(ui_bytes)[:16], 'access': sha(test_bytes)[:16]}))
        raise SystemExit(0 if same else 1)
    if ui_dir.exists() or test_dir.exists():
        raise SystemExit('Existing build preserved')
    ui_meta = json.loads((root / 'build-v4/build-manifest.json').read_text())
    ui_meta.update(revision=args.revision, source_build='build-v4', wad_sha256=sha(ui_bytes), runtime_verified=False, **ui_rec)
    test_meta = json.loads((root / 'access-build-v5/build-manifest.json').read_text())
    test_meta.update(revision=int(test_name.rsplit('-v', 1)[1]), source_build=ui_name, source_access_revision=5, source_wad_sha256=sha(ui_bytes),
                     wad_sha256=sha(test_bytes), runtime_verified=False, **test_rec)
    for folder, name, data, meta in [(ui_dir, 'nintendo-ko-ui-test.wad', ui_bytes, ui_meta),
                                     (test_dir, 'nintendo-local-test.wad', test_bytes, test_meta)]:
        folder.mkdir()
        (folder / name).write_bytes(data)
        (folder / 'build-manifest.json').write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'build': ui_name, 'access_build': test_name, 'wad': sha(ui_bytes)[:16], 'access_wad': sha(test_bytes)[:16],
                      'menu_x': [r.get('x') for r in ui_rec['menu_art']], 'opening_x': ui_rec['opening']['x']},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()

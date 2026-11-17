"""Create a new Nintendo menu-art candidate and isolated access candidate.

No NAND/SD installation. Existing build numbers are never overwritten.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.nintendo_menu_art_v5 import korean_menu_art


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    root = ROOT / 'workspace/channels/nintendo'
    ui_dir, test_dir = root / 'build-v5', root / 'access-build-v6'
    if ui_dir.exists() or test_dir.exists():
        raise SystemExit('Existing build preserved')
    lib = load_library()
    ui = lib.title.Title()
    ui.load_wad((root / 'build-v4/nintendo-ko-ui-test.wad').read_bytes())
    source_contents = [ui.get_content_by_index(i) for i in range(len(ui.tmd.content_records))]
    content, report = korean_menu_art(source_contents[0])
    ui.set_content(content, 0)
    ui_bytes = ui.dump_wad()
    check = lib.title.Title()
    check.load_wad(ui_bytes)
    if [i for i in range(len(source_contents)) if check.get_content_by_index(i) != source_contents[i]] != [0]:
        raise ValueError('UI changes escaped menu art')

    isolated = lib.title.Title()
    isolated.load_wad((root / 'access-build-v5/nintendo-local-test.wad').read_bytes())
    before = [isolated.get_content_by_index(i) for i in range(len(isolated.tmd.content_records))]
    isolated.set_content(content, 0)
    test_bytes = isolated.dump_wad()
    verify = lib.title.Title()
    verify.load_wad(test_bytes)
    if [i for i in range(len(before)) if verify.get_content_by_index(i) != before[i]] != [0]:
        raise ValueError('Access changes escaped menu art')

    ui_meta = json.loads((root / 'build-v4/build-manifest.json').read_text())
    ui_meta.update(revision=5, source_build='build-v4', wad_sha256=sha(ui_bytes),
                   menu_art=report, runtime_verified=False)
    test_meta = json.loads((root / 'access-build-v5/build-manifest.json').read_text())
    test_meta.update(revision=6, source_build='build-v5', source_access_revision=5,
                     source_wad_sha256=sha(ui_bytes), wad_sha256=sha(test_bytes),
                     menu_art=report, runtime_verified=False)
    for folder, wad_name, data, meta in [
        (ui_dir, 'nintendo-ko-ui-test.wad', ui_bytes, ui_meta),
        (test_dir, 'nintendo-local-test.wad', test_bytes, test_meta),
    ]:
        folder.mkdir()
        (folder / wad_name).write_bytes(data)
        (folder / 'build-manifest.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print(json.dumps({'build': 5, 'access_build': 6, 'changed_content_indices': [0],
                      'menu_art': report}))


if __name__ == '__main__':
    main()

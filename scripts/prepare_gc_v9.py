"""Preserve v6 in full; clone it to v9 = v6 + GameCube-only disc channel layout.

Menu content 6 = kwce.gc_native (Japanese card encoding + comments, the v6 build)
+ kwce.gc_disc_layout (original two-disc layout names), i.e. exactly what the
Priiloader entries "KWCE GC: ..." x3 + "KWCE GC: GC-only disc layout (DVD off)"
produce on a 43K console. No DVD hook, no DVD player channel. The v6 resource
(content 1) and the catalogued GC test disc are kept. Test NAND only.
"""
import hashlib
import json
import shutil
import struct
import subprocess
import sys

from audit_sd import ROOT, PRIVATE, sha256
sys.path.insert(0, str(ROOT))
from kwce.gc_native import patch_gc_native  # noqa: E402
from kwce.gc_disc_layout import patch_gc_only_layout, check_resource  # noqa: E402
from launch_dolphin import scrub_download_tasks, validate_native_runtime  # noqa: E402


def snapshot(folder):
    return [dict(path=p.relative_to(folder).as_posix(), size=p.stat().st_size, mtime_ns=p.stat().st_mtime_ns,
                 sha256=sha256(p)) for p in sorted(folder.rglob('*')) if p.is_file()]


def main():
    tasks = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Dolphin.exe', '/FO', 'CSV', '/NH'], capture_output=True, text=True)
    if 'dolphin.exe' in tasks.stdout.lower():
        raise SystemExit('Close Dolphin before cloning profiles')
    parent = ROOT / 'workspace/sandbox/gc-v6'
    target = ROOT / 'workspace/sandbox/gc-v9'
    out = ROOT / 'workspace/experiments/gc-native-v9'
    if target.exists() or out.exists():
        raise SystemExit('Existing v9 preserved')
    validate_native_runtime('gc-native-v6-user')
    before = snapshot(parent)
    (PRIVATE / 'gc-v6-before-v9-manifest.json').write_text(json.dumps(before, indent=2))
    for folder in ['user', 'Dolphin-x64', 'disc']:
        shutil.copytree(parent / folder, target / folder, ignore=shutil.ignore_patterns('Logs', 'ScreenShots', 'Cache', 'StateSaves'))
    shutil.copy2(parent / 'NetProbe.exe', target / 'NetProbe.exe')
    cfg = target / 'user/Config/Dolphin.ini'
    cfg.write_text(cfg.read_text(encoding='utf-8-sig').replace(str(parent), str(target)), encoding='utf-8')
    original = (ROOT / 'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    gc_menu, _ = patch_gc_native(original, japanese_cards=True, japanese_comments=True)
    menu, layout = patch_gc_only_layout(gc_menu, require_original=False)
    content = target / 'user/Wii/title/00000001/00000002/content'
    tmd = bytearray((content / 'title.tmd').read_bytes())
    found = False
    resource_record = None
    for i in range(int.from_bytes(tmd[0x1de:0x1e0], 'big')):
        at = 0x1e4 + 36 * i
        cid, index = struct.unpack_from('>IH', tmd, at)
        path = content / f'{cid:08x}.app'
        if index == 6:
            if path.read_bytes() != gc_menu:
                raise ValueError('v6 menu content differs from the GC native build')
            path.write_bytes(menu)
            struct.pack_into('>Q', tmd, at + 8, len(menu))
            tmd[at + 16:at + 36] = hashlib.sha1(menu).digest()
            found = True
        elif index == 1:
            resource_record = check_resource(path.read_bytes())
    if not found or resource_record is None:
        raise ValueError('Menu DOL or resource content missing')
    (content / 'title.tmd').write_bytes(tmd)
    scrub_download_tasks('gc-native-v9-user')
    out.mkdir(parents=True)
    (out / 'menu-gc-only-layout.dol').write_bytes(menu)
    (out / 'build-manifest.json').write_text(json.dumps(dict(
        parent='gc-native-v6-user', menu_sha256=hashlib.sha256(menu).hexdigest(), gc_only_layout=layout,
        resource_original_layout=resource_record, dvd_hook=False, dvd_player_installed=False,
        TMD_signature_valid=False, test_nand_only=True), ensure_ascii=False, indent=2), encoding='utf-8')
    if snapshot(parent) != before:
        raise ValueError('Preserved v6 changed during clone')
    print(json.dumps(dict(built=True, menu_bytes=len(menu), parent_files_preserved=len(before),
                          next='python scripts/prepare_gc_sandbox_rev.py --revision 9')))


if __name__ == '__main__':
    main()

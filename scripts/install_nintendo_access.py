"""Install an existing Nintendo access-build candidate into its stopped,
isolated local-response test NAND for on-screen banner/icon/in-channel review.

Reuses the verified NAND-write path of install_nintendo_banner_test_v9.py
(back up the prior title first, install the WAD unchanged, record the active
revision) but takes the revision as an argument so RC2 candidates (e.g. the
access-build-v13 banner/icon + Korean in-channel logo) can be reviewed without
a new per-build script. It does NOT touch configs/channels.catalog.json: the
emulator catalog's active builds stay as they are; this only stages the
candidate WAD in the isolated nintendo-test-v1 NAND. Dolphin must be stopped.
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from kwce.channels import load_library
from prepare_channel_access import stopped

TITLE_DIR = 'title/00010001/48415445'  # HATE (Nintendo Channel test title)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--access', type=int, required=True,
                    help='access-build-vN revision to stage in the test NAND')
    args = ap.parse_args()

    stopped()
    base = ROOT / 'workspace/channels/nintendo'
    build_dir = base / f'access-build-v{args.access}'
    wad = build_dir / 'nintendo-local-test.wad'
    manifest = build_dir / 'build-manifest.json'
    if not wad.is_file() or not manifest.is_file():
        raise SystemExit(f'Missing access-build-v{args.access} WAD or manifest')

    meta = json.loads(manifest.read_text(encoding='utf-8'))
    payload = wad.read_bytes()
    if hashlib.sha256(payload).hexdigest() != meta['wad_sha256']:
        raise ValueError('Candidate WAD hash mismatch vs build-manifest.json')

    nand = ROOT / 'workspace/sandbox/nintendo-test-v1/user/Wii'
    if not (nand / TITLE_DIR).is_dir():
        raise SystemExit('Nintendo test NAND title not found')
    backup = ROOT / f'workspace/private/nintendo-test-before-access-v{args.access}'
    if backup.exists():
        raise SystemExit('Previous title backup preserved; refusing to overwrite')
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(nand / TITLE_DIR, backup)

    lib = load_library()
    title = lib.title.Title()
    title.load_wad(payload)
    lib.nand.EmuNAND(nand).install_title(title)

    active = base / 'active-access.json'
    active.write_text(json.dumps({'revision': args.access}), encoding='utf-8')
    print(json.dumps(dict(channel='nintendo', access=args.access,
                          wad_sha256=hashlib.sha256(payload).hexdigest(),
                          backup=str(backup.relative_to(ROOT)))))


if __name__ == '__main__':
    main()

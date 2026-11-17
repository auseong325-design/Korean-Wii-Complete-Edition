"""Install the v8 artwork candidate in the stopped Nintendo test NAND only."""
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


def main():
    stopped()
    base = ROOT / 'workspace/channels/nintendo'
    active = base / 'active-access.json'
    if json.loads(active.read_text())['revision'] != 7:
        raise SystemExit('Unexpected active test revision')
    wad = base / 'access-build-v8/nintendo-local-test.wad'
    meta = json.loads((wad.parent / 'build-manifest.json').read_text())
    payload = wad.read_bytes()
    if hashlib.sha256(payload).hexdigest() != meta['wad_sha256']:
        raise ValueError('Candidate hash mismatch')
    nand = ROOT / 'workspace/sandbox/nintendo-test-v1/user/Wii'
    backup = ROOT / 'workspace/private/nintendo-test-before-access-v8'
    if backup.exists():
        raise SystemExit('Previous title backup preserved')
    catalog_path = ROOT / 'configs/channels.catalog.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    channel = next(c for c in catalog['channels'] if c['id'] == 'nintendo')
    row = next(i for i in channel['installs'] if i['role'] == 'active')
    if row['profile'] != 'nintendo-test-v1' or row['artifact'] != 'access-build-v7':
        raise ValueError('Unexpected test catalog')
    shutil.copytree(nand / 'title/00010001/48415445', backup)
    lib = load_library()
    title = lib.title.Title()
    title.load_wad(payload)
    lib.nand.EmuNAND(nand).install_title(title)
    active.write_text(json.dumps({'revision': 8}), encoding='utf-8')
    row['artifact'] = 'access-build-v8'
    channel['source_build'] = 7
    channel['stage'] = 'in_progress'
    channel['remaining'] = '배너 후보 화면 검수; 실기 262000 원인 및 본문 진입 미해결'
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Installed v8 in the isolated Nintendo test NAND; prior title backed up')


if __name__ == '__main__':
    main()

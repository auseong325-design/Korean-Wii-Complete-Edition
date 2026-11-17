"""Minimal r16 update for an existing Recent Channels v1 SD; no SD writes."""
import argparse, hashlib, json, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.channel_hardware import sd_files
from kwce.hardware import hardware_wad
from kwce.news_loading import patch

PACKAGE = ROOT / 'workspace/hardware/kwce-news-update-v2'
ARCHIVE = PACKAGE.with_suffix('.zip')
README = 'KWCE-NEWS-UPDATE-README-ko.txt'
MANIFEST = 'KWCE-NEWS-UPDATE-manifest.json'
ALLOWED = {'kwce/news/korean.wad', 'kwce/packages.txt', README, MANIFEST}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def validate(folder=PACKAGE, archive=ARCHIVE):
    folder, archive = Path(folder), Path(archive)
    record = json.loads((folder / MANIFEST).read_text(encoding='utf-8'))
    if (record['revision'] != 16 or record['kind'] != 'news-existing-sd-update-v1'
            or record['diagnostic_only'] or record['hardware_success_verified']
            or {r['path'] for r in record['files']} != ALLOWED - {MANIFEST}):
        raise ValueError('News update scope differs')
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    if actual != ALLOWED:
        raise ValueError('Unexpected update files')
    for row in record['files']:
        data = (folder / row['path']).read_bytes()
        if len(data) != row['bytes'] or sha(data) != row['sha256']:
            raise ValueError('News update hash differs')
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist()) != len(ALLOWED) or set(z.namelist()) != ALLOWED or z.testzip():
            raise ValueError('ZIP entries/CRC differ')
        for name in ALLOWED:
            if z.read(name) != (folder / name).read_bytes():
                raise ValueError('ZIP roundtrip differs')
    return record

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--check', action='store_true'); args = ap.parse_args()
    if args.check:
        validate(); print('PASS: News r16 ZIP, four exact entries, hashes/CRC/roundtrip'); return
    if PACKAGE.exists() or ARCHIVE.exists():
        raise ValueError('Existing numbered package preserved')
    prior = ROOT / 'workspace/hardware/kwce-channels-v1'
    sd_files(prior)  # Exact, frozen existing installer/list and five-channel scope.
    base = ROOT / 'workspace/channels/news'
    meta = json.loads((base / 'build-v16/build-manifest.json').read_text(encoding='utf-8'))
    if meta.get('diagnostic_only') or meta.get('hardware_allowed') is False or meta['revision'] != 16 or meta['parent_revision'] != 15:
        raise ValueError('Only production r16 is accepted')
    raw = (base / 'build-v16/news-ko-personal.wad').read_bytes()
    if sha(raw) != meta['wads']['personal']['sha256']:
        raise ValueError('Production WAD identity differs')
    lib = load_library(); old, new = lib.title.Title(), lib.title.Title()
    old.load_wad((base / 'build-v15/news-ko-personal.wad').read_bytes()); new.load_wad(raw)
    if patch(old.get_content_by_index(1))[0] != new.get_content_by_index(1):
        raise ValueError('Production loading code reproduction differs')
    if [i for i in range(12) if old.get_content_by_index(i) != new.get_content_by_index(i)] != [1]:
        raise ValueError('Unexpected production content changes')
    wad, checks = hardware_wad(raw, (base / 'originals/news-usa-wiilink-archive.wad').read_bytes())
    if checks['title_id'] != '0001000248414745' or checks['contents'] != 12:
        raise ValueError('Unexpected News channel boundary')
    listing = (prior / 'kwce/packages.txt').read_bytes()
    before, after = b'News r15 (retest)', b'News r16 (loading fix)'
    if listing.count(before) != 1:
        raise ValueError('Frozen previous list differs')
    files = {'kwce/news/korean.wad': wad, 'kwce/packages.txt': listing.replace(before, after),
             README: (ROOT / 'docs/hardware/NEWS-V16-README-ko.txt').read_bytes()}
    record = dict(kind='news-existing-sd-update-v1', revision=16, diagnostic_only=False,
                  hardware_success_verified=False, prerequisite='kwce-channels-v1 already on same Wii SD',
                  source_sha256=sha(raw), hardware_checks=checks,
                  files=[dict(path=n, bytes=len(b), sha256=sha(b)) for n, b in sorted(files.items())])
    files[MANIFEST] = (json.dumps(record, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    PACKAGE.mkdir(parents=True)
    for name, data in files.items():
        p = PACKAGE / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
    with zipfile.ZipFile(ARCHIVE, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 26, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16; z.writestr(info, data)
    validate(); print(f'PASS: {ARCHIVE.name}, production r16 only, four entries, no SD write')

if __name__ == '__main__':
    main()

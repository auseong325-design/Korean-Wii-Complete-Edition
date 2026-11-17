"""Forecast build-v106: build-v103 plus the Wii Menu icon/banner language fix.

Only content 4 (icon channel script) and content 5 (banner RSO) change; the
executable (content 1) and every other content stay byte-identical to v103.
See kwce/forecast_banner_language.py for the cause and the exact edits.

python scripts/build_forecast_banner_language.py [--reproduce]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.forecast_banner_language import patch_contents

PARENT = 103
REVISION = 106
WAD = 'forecast-ko-personal-test.wad'


def build():
    parent = ROOT / f'workspace/channels/forecast/build-v{PARENT}'
    meta = json.loads((parent / 'build-manifest.json').read_text(encoding='utf-8'))
    raw = (parent / WAD).read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta['wad_sha256']:
        raise ValueError('Forecast v103 parent differs')
    lib = load_library()
    title = lib.title.Title()
    title.load_wad(raw)
    if title.tmd.title_id != '0001000248414645' or len(title.tmd.content_records) != 12:
        raise ValueError('Wrong Forecast parent')
    original = [title.get_content_by_index(i) for i in range(12)]
    c4, c5, record = patch_contents(original[4], original[5])
    title.set_content(c4, 4)
    title.set_content(c5, 5)
    wad = title.dump_wad()
    check = lib.title.Title()
    check.load_wad(wad)
    changed = sorted(i for i in range(12) if check.get_content_by_index(i) != original[i])
    if changed != [4, 5] or check.get_content_by_index(1) != original[1]:
        raise ValueError(f'Forecast v106 changed unexpected contents: {changed}')
    if check.tmd.region != title.tmd.region or check.tmd.title_version != title.tmd.title_version:
        raise ValueError('TMD identity changed')
    return wad, meta, record, changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reproduce', action='store_true')
    args = ap.parse_args()
    out = ROOT / f'workspace/channels/forecast/build-v{REVISION}'
    expected = None
    if args.reproduce:
        if not (out / WAD).exists():
            raise SystemExit('No build-v106 to reproduce yet')
        expected = (out / WAD).read_bytes()
        n = 1
        while (ROOT / f'workspace/private/forecast-banner-language-reproduce-{n}').exists():
            n += 1
        out = ROOT / f'workspace/private/forecast-banner-language-reproduce-{n}'
    if out.exists():
        raise SystemExit('Existing Forecast build-v106 preserved')
    wad, meta, record, changed = build()
    if expected is not None and wad != expected:
        raise SystemExit('Forecast v106 byte-identical reproduction differs')
    h = hashlib.sha256(wad).hexdigest()
    meta = dict(meta)
    meta.update(revision=REVISION, parent_revision=PARENT, parent_wad_sha256=meta['wad_sha256'],
                changed_from_parent=changed, executable_changed=False, wad_sha256=h,
                banner_language_fix=dict(record, cause='Wii Menu icon script and banner RSO compare the data language '
                                                       'with raw SCGetLanguage(); Korean 9 never equals the English (1) data '
                                                       'the channel downloads for language >= 7',
                                         adds_new_section=False, hardware_verified=False, dolphin_verified=False),
                wiilink_live_compatibility_verified=False, full_localization_complete=False)
    out.mkdir()
    (out / WAD).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: Forecast build-v{REVISION} (banner/icon language fix); contents {changed} only; '
          f'content1 identical; sha {h[:16]}' + (' (byte-identical reproduction)' if expected is not None else ''))


if __name__ == '__main__':
    main()

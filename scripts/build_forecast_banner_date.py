"""Forecast build-v107: build-v106 plus a Korean "issued at" line in the Wii Menu banner.

Only content 5 (banner RSO) changes; the executable and every other content
stay byte-identical to v106. See kwce/forecast_banner_date.py for the edit.

python scripts/build_forecast_banner_date.py [--reproduce]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.forecast_banner_date import patch_content

PARENT = 106
REVISION = 107
WAD = 'forecast-ko-personal-test.wad'


def build():
    parent = ROOT / f'workspace/channels/forecast/build-v{PARENT}'
    meta = json.loads((parent / 'build-manifest.json').read_text(encoding='utf-8'))
    raw = (parent / WAD).read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta['wad_sha256']:
        raise ValueError('Forecast v106 parent differs')
    lib = load_library()
    title = lib.title.Title()
    title.load_wad(raw)
    if title.tmd.title_id != '0001000248414645' or len(title.tmd.content_records) != 12:
        raise ValueError('Wrong Forecast parent')
    original = [title.get_content_by_index(i) for i in range(12)]
    c5, record = patch_content(original[5])
    title.set_content(c5, 5)
    wad = title.dump_wad()
    check = lib.title.Title()
    check.load_wad(wad)
    changed = sorted(i for i in range(12) if check.get_content_by_index(i) != original[i])
    if changed != [5] or check.get_content_by_index(1) != original[1]:
        raise ValueError(f'Forecast v107 changed unexpected contents: {changed}')
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
            raise SystemExit(f'No build-v{REVISION} to reproduce yet')
        expected = (out / WAD).read_bytes()
        n = 1
        while (ROOT / f'workspace/private/forecast-banner-date-reproduce-{n}').exists():
            n += 1
        out = ROOT / f'workspace/private/forecast-banner-date-reproduce-{n}'
    if out.exists():
        raise SystemExit(f'Existing Forecast build-v{REVISION} preserved')
    wad, meta, record, changed = build()
    if expected is not None and wad != expected:
        raise SystemExit(f'Forecast v{REVISION} byte-identical reproduction differs')
    h = hashlib.sha256(wad).hexdigest()
    meta = dict(meta)
    meta.update(revision=REVISION, parent_revision=PARENT, parent_wad_sha256=meta['wad_sha256'],
                changed_from_parent=changed, executable_changed=False, wad_sha256=h,
                banner_date_korean=dict(record, cause='banner RSO has no Korean date format; the Korean console '
                                                     'took the US English "As of ... a.m./p.m." line',
                                        adds_new_section=False, hardware_verified=False, dolphin_verified=False),
                wiilink_live_compatibility_verified=False, full_localization_complete=False)
    out.mkdir()
    (out / WAD).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: Forecast build-v{REVISION} (Korean banner date); contents {changed} only; '
          f'content1 identical; sha {h[:16]}' + (' (byte-identical reproduction)' if expected is not None else ''))


if __name__ == '__main__':
    main()

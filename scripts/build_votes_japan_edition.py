"""Everybody Votes Channel installer edition "japan": build-v28 (country 1 Japan, region 1 whole country)
made into the hardware WAD the installer offers next to the standard build (build-v27, USA 49, region 1).

  python scripts/build_votes_japan_edition.py [--reproduce]

Output workspace/channels/votes/japan-hardware-v1 (fakesigned, region 4, same as the export of the
standard Korean build). User decision 2026-11-17: no Korea on the WiiLink server, offer USA and Japan.
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.hardware import hardware_wad

BASE = ROOT / 'workspace/channels/votes'
KOREAN = BASE / 'build-v28/votes-ko-ui-test.wad'
ORIGINAL = BASE / 'originals/votes-usa-wiilink-archive.wad'
OUT = BASE / 'japan-hardware-v1'
NAME = 'votes-ko-japan-hardware.wad'


def build():
    korean = KOREAN.read_bytes()
    pinned = json.loads((KOREAN.parent / 'build-manifest.json').read_text(encoding='utf-8'))['wad_sha256']
    if hashlib.sha256(korean).hexdigest() != pinned: raise ValueError('build-v28 differs from its manifest')
    wad, checks = hardware_wad(korean, ORIGINAL.read_bytes())
    meta = dict(revision=1, channel='votes', variant='japan', edition='japan', edition_label='Japan (vote as Japan)',
                country='Japan', country_code=1, region_id=1, source_build='build-v28', source_wad_sha256=pinned,
                wad_sha256=hashlib.sha256(wad).hexdigest(), local_only=False, hardware_candidate=True,
                full_localization_complete=False, hardware_success_verified=False, hardware_checks=checks,
                note='Questions come in Japanese or English (WiiLink Japan languages); the standard build votes as USA.')
    return wad, meta


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--reproduce', action='store_true'); a = ap.parse_args()
    wad, meta = build()
    if a.reproduce:
        if (OUT / NAME).read_bytes() != wad: raise SystemExit('reproduction differs')
        print('PASS: votes japan-hardware-v1 reproduced byte-identically'); return
    if OUT.exists(): raise SystemExit('Existing build preserved')
    OUT.mkdir(parents=True); (OUT / NAME).write_bytes(wad)
    (OUT / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: votes japan-hardware-v1, wad {meta["wad_sha256"][:16]}')


if __name__ == '__main__': main()

"""Wii Room build-v68 (MiiInfo code 0 accepted) and Votes build-v22 (239001 -> NWC24 result readout).

Each derives from its parent WAD and changes content 1 only (Wii Room: LZ11 container re-encoded
keeping the original matches; raw size unchanged). python scripts/build_channel_service_fix.py --channel wiiroom|votes [--reproduce]
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce import channel_service_fixes as fixes
from kwce.wiiroom_formats import decompress_lz11, reencode_lz11_same_size

FIX = dict(wiiroom=(fixes.patch_room_miiinfo, 'miiinfo_code_zero'), votes=(fixes.patch_votes_readout, 'dltask_error_readout'),
           votes_v23=(fixes.patch_votes_quiet_signature, 'quiet_verify_signature'),
           votes_v24=(fixes.patch_votes_region_select, 'region_select_halk'),
           votes_v25=(fixes.patch_votes_region_launch, 'region_launch_halk'),
           votes_v26=(fixes.patch_votes_launch_region, 'launch_region_check'),
           votes_v27=(fixes.patch_votes_whole_country, 'usa_whole_country'),
           votes_v28=(fixes.patch_votes_japan, 'japan_whole_country'))


def build(channel):
    pin = json.loads((ROOT / 'configs/channel-service-fixes.json').read_text(encoding='utf-8'))[channel]
    parent = ROOT / f'workspace/channels/{pin.get("channel", channel)}/build-v{pin["parent"]}'
    meta = json.loads((parent / 'build-manifest.json').read_text(encoding='utf-8'))
    raw = (parent / pin['wad']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta['wad_sha256']: raise ValueError('Parent WAD differs')
    lib = load_library(); title = lib.title.Title(); title.load_wad(raw)
    count = len(title.tmd.content_records); original = [title.get_content_by_index(i) for i in range(count)]
    patch, key = FIX[channel]
    exe = decompress_lz11(original[1]) if pin['compressed'] else original[1]
    edited, record = patch(exe, pin['parent_executable_sha256'])
    packed = reencode_lz11_same_size(original[1], edited) if pin['compressed'] else edited
    if not pin['compressed'] and len(packed) != len(original[1]): raise ValueError('Content 1 size changed')
    title.set_content(packed, 1); wad = title.dump_wad()
    check = lib.title.Title(); check.load_wad(wad)
    if [i for i in range(count) if check.get_content_by_index(i) != original[i]] != [1]: raise ValueError('Unexpected content change')
    record.update(content_1_size=len(packed), parent_content_1_size=len(original[1]))
    meta = dict(meta); meta.update(revision=pin['revision'], parent_revision=pin['parent'], parent_wad_sha256=meta['wad_sha256'],
                                   wad_sha256=hashlib.sha256(wad).hexdigest(), changed_from_parent=[1], runtime_verified=False)
    meta[key] = record
    return pin, wad, meta


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--channel', choices=sorted(FIX), required=True)
    ap.add_argument('--reproduce', action='store_true'); a = ap.parse_args()
    pin, wad, meta = build(a.channel); out = ROOT / f'workspace/channels/{pin.get("channel", a.channel)}/build-v{pin["revision"]}'
    if a.reproduce:
        if (out / pin['wad']).read_bytes() != wad: raise SystemExit(f'{a.channel} v{pin["revision"]} reproduction differs')
        print(f'PASS: {a.channel} v{pin["revision"]} reproduced byte-identically'); return
    if out.exists(): raise SystemExit('Existing build preserved')
    out.mkdir(parents=True); (out / pin['wad']).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: {a.channel} v{pin["revision"]} from v{pin["parent"]}, content 1 only, wad {meta["wad_sha256"][:16]}')


if __name__ == '__main__': main()

"""Build an isolated hardware candidate fixing only Photo Prints TMD region."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.hardware import local_reference_counts

BASE = ROOT / 'workspace/channels/photoprints'

def build():
    lib = load_library()
    prior = BASE / 'hardware-v5'
    source = (prior / 'photoprints-ko-hardware-test.wad').read_bytes()
    meta = json.loads((prior / 'build-manifest.json').read_text(encoding='utf-8'))
    if hashlib.sha256(source).hexdigest() != meta['wad_sha256']:
        raise ValueError('Prior hardware candidate differs')
    old = lib.title.Title(); old.load_wad(source)
    if old.tmd.title_id.lower() != '000100014843444a' or old.tmd.region != 0:
        raise ValueError('Unexpected title or original region')
    contents = [old.get_content_by_index(i) for i in range(len(old.tmd.content_records))]
    counts = local_reference_counts(old)
    tmd_before = old.tmd.dump()
    ticket_before = old.ticket.dump()
    old.tmd.region = 4
    old.fakesign()
    result = old.dump_wad()
    check = lib.title.Title(); check.load_wad(result)
    if check.tmd.region != 4 or not check.get_is_fakesigned():
        raise ValueError('Region/signature check failed')
    if check.tmd.title_id.lower() != '000100014843444a' or check.tmd.ios_tid != meta['hardware_checks']['ios']:
        raise ValueError('Title or IOS changed')
    if [check.get_content_by_index(i) for i in range(len(contents))] != contents:
        raise ValueError('Channel content changed')
    if local_reference_counts(check) != counts:
        raise ValueError('Service endpoints changed')
    tmd_after = check.tmd.dump()
    if len(tmd_before) != len(tmd_after) or {i for i, (a, b) in enumerate(zip(tmd_before, tmd_after)) if a != b} != {0x19d, 0x1e3} or check.ticket.dump() != ticket_before:
        raise ValueError('Changes escaped the TMD region and fakesign padding')
    return result, dict(revision=6, hardware_candidate=True, local_only=False,
        hardware_success_verified=False, full_localization_complete=False,
        source='hardware-v5', source_wad_sha256=meta['wad_sha256'],
        wad_sha256=hashlib.sha256(result).hexdigest(), title_id=check.tmd.title_id,
        region_before=0, region_after=4, ios=check.tmd.ios_tid,
        unchanged_content_count=len(contents), local_reference_counts=counts,
        reason='Japanese TMD region may prevent Korean System Menu launch; exact real failure path remains unverified')

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--verify', action='store_true'); args = ap.parse_args()
    output = BASE / 'hardware-v6'
    data, meta = build()
    if args.verify:
        if (output / 'photoprints-ko-hardware-test.wad').read_bytes() != data:
            raise ValueError('Candidate is not byte reproducible')
        print('PASS: Photo Prints hardware-v6 reproducible; only TMD region/signing changed, 13 contents preserved')
        return
    if output.exists():
        raise SystemExit('Existing candidate preserved')
    output.mkdir(parents=True)
    (output / 'photoprints-ko-hardware-test.wad').write_bytes(data)
    (output / 'build-manifest.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    print('PASS: hardware-v6 region 0 -> 4; all 13 channel contents unchanged; real Wii untested')

if __name__ == '__main__': main()

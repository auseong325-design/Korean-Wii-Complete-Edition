"""Create a new experimental compressed module. Never deploys to hardware."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.dvd_lzma_stage import compile_decoder, pack, unpack
from kwce.dvd_native_relocate import validate_payload, validate_ash_mapping


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--player', type=int, required=True)
    parser.add_argument('--revision', type=int, required=True)
    args = parser.parse_args()
    out = ROOT / f'workspace/experiments/dvd-native-module-v{args.revision}'
    if out.exists():
        raise ValueError('Existing numbered module preserved')
    source = ROOT / f'workspace/channels/dvd-player/build-v{args.player}'
    raw = (source / 'boot.dol').read_bytes()
    manifest = json.loads((source / 'build-manifest.json').read_text())
    sha = hashlib.sha256(raw).hexdigest()
    if sha != manifest['boot_dol_sha256']:
        raise ValueError('Player differs from frozen build')
    validate_payload(raw)
    validate_ash_mapping(raw)
    code = compile_decoder()
    package = pack(raw, code)
    if unpack(package) != raw:
        raise ValueError('Package roundtrip failed')
    out.mkdir()
    # Keep the existing SD asset name; only source38 understands its format.
    (out / 'player.ash').write_bytes(package)
    (out / 'decoder.bin').write_bytes(code)
    (out / 'manifest.json').write_text(json.dumps(dict(
        schema=1, format='KWL1', source_build=args.player, source_sha256=sha,
        packed_sha256=hashlib.sha256(package).hexdigest(), bytes=len(package),
        raw_bytes=len(raw), decoder_bytes=len(code), source_revision_required=38,
        physical_hardware_verified=False), indent=2) + '\n')
    print(f'PASS experimental module v{args.revision}: {len(package)} bytes; exact roundtrip')


if __name__ == '__main__':
    main()

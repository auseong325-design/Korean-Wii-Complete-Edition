"""Build local-feed-v3: the RAW English Forecast supply data (PC conversion disabled).

This feed is the exact public country-136 payloads with NO localize_forecast overlay. Seeding
forecast-v2 from it and booting build-v104 proves the channel itself converts the supply strings
(conditions, UV, place/country names) at runtime: any Korean on screen must come from the channel,
because the PC side wrote English. New number only; byte-identical regeneration is verified and an
existing feed is never overwritten. No network, credentials or signatures.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.forecast_cache import public_source, inspect_public_download
from kwce.forecast_data import localize_forecast, forecast_mapping


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    lib = load_library()
    from libWiiPy.archive import decompress_lz77
    binding = json.loads((ROOT / 'workspace/channels/forecast/references/active-public-snapshot.json').read_text())
    out = ROOT / 'workspace/channels/forecast/local-feed-v3'
    mapping = forecast_mapping()
    records = {}
    files = {}
    for kind in ('forecast', 'short'):
        raw = public_source(kind, binding).read_bytes()
        report = inspect_public_download(raw, kind)
        payload = raw[320:]                       # LZ-compressed weather struct, English, unmodified
        files[kind] = payload
        rec = dict(file=f'{kind}.bin', sha256=sha(payload), size=len(payload),
                   decompressed_size=report['decompressed_size'], source_sha256=report['sha256'])
        if kind == 'forecast':
            # Document that this really is unconverted English and that localize would change it.
            localized, _ = localize_forecast(payload, mapping)
            data = decompress_lz77(payload)
            english_markers = [m for m in (b'S\0u\0n\0n\0y', b'M\0o\0d\0e\0r\0a\0t\0e') if m in data]
            rec.update(differs_from_localized=(localized != payload),
                       english_markers_present=len(english_markers))
        records[kind] = rec
    manifest = dict(schema=1, feed='local-feed-v3', source_binding=binding, files=records,
                    pc_conversion='disabled (raw English)',
                    purpose='Prove build-v104 converts WiiLink supply strings in-channel at runtime',
                    launch=('Remove-Item Env:PYTHONUTF8 -ErrorAction SilentlyContinue; '
                            '.venv\\Scripts\\python.exe scripts\\seed_forecast_cache.py --current --offline --raw-english; '
                            '.venv\\Scripts\\python.exe scripts\\launch_forecast.py --current --cache-preview'))
    if out.exists():
        old = json.loads((out / 'manifest.json').read_text())
        for kind in ('forecast', 'short'):
            if (out / f'{kind}.bin').read_bytes() != files[kind] or old['files'][kind]['sha256'] != records[kind]['sha256']:
                raise SystemExit('Existing local-feed-v3 differs; new number only')
        print('local-feed-v3 already present and byte-identical')
    else:
        out.mkdir()
        for kind in ('forecast', 'short'):
            (out / f'{kind}.bin').write_bytes(files[kind])
        (out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        print('wrote', out)
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'source_sha256'} for k, v in records.items()}, ensure_ascii=True))


if __name__ == '__main__':
    main()

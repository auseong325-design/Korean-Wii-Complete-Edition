"""Export the existing authored DVD banner for the native SD File wrapper."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library, ChannelArchive
from kwce.formats import U8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wad', type=int, default=31)
    ap.add_argument('--revision', type=int, required=True)
    args = ap.parse_args()
    out = ROOT / f'workspace/experiments/dvd-native-banner-v{args.revision}'
    if out.exists(): raise SystemExit('Existing numbered banner preserved')
    source = ROOT / f'workspace/channels/dvd-player/wad-v{args.wad}/dvd-player.wad'
    record = json.loads(source.with_name('wad-manifest.json').read_text(encoding='utf-8'))
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != record['wad_sha256']:
        raise ValueError('Authored DVD WAD differs from its manifest')
    lib = load_library()
    from libWiiPy.archive import decompress_lz77
    title = lib.title.Title(); title.load_wad(data)
    outer = U8(title.get_content_by_index(0)[0x640:])
    matches = [n for n in outer.files if n.endswith('/banner.bin') or n == 'banner.bin']
    if len(matches) != 1: raise ValueError('Expected exactly one banner')
    wrapped = outer.get(matches[0])
    if wrapped[:4] != b'IMD5': raise ValueError('Expected IMD5 banner')
    raw = decompress_lz77(wrapped[32:])
    archive = ChannelArchive(raw)
    if not any(n.endswith('.brlyt') for n in archive.files): raise ValueError('Banner layout missing')
    out.mkdir(); (out / 'menu.arc').write_bytes(raw)
    (out / 'manifest.json').write_text(json.dumps(dict(schema=1, source_wad=args.wad,
        source_sha256=hashlib.sha256(data).hexdigest(), bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest()), indent=2)+'\n')
    print(f'PASS native banner v{args.revision}: {len(raw)} bytes, original layout/resources preserved')


if __name__ == '__main__': main()

"""Synthetic Wii-format test disc images for the emulator (no game data).

--kind unreadable: Wii header and magic but an empty partition table, so the
System Menu cannot open a game partition and ends in the unreadable/unknown
disc state - the state a DVD-Video disc reaches on a console (Dolphin cannot
load real DVD-Video discs). Output: workspace/test-media/wii/kwce-wii-<kind>-vN.iso
"""
import argparse,hashlib,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def unreadable():
    image=bytearray(0x100000)
    image[0:6]=b'KDVT01'                       # synthetic ID (not a retail product code)
    struct.pack_into('>I',image,0x18,0x5D1C9EA3)  # Wii disc magic
    image[0x20:0x20+31]=b'KWCE UNREADABLE TEST DISC'.ljust(31,b'\0')
    image[0x60]=1;image[0x61]=1                 # no hashes, no encryption (unencrypted layout)
    # partition table at 0x40000: four groups, all empty
    struct.pack_into('>8I',image,0x40000,0,0,0,0,0,0,0,0)
    struct.pack_into('>I',image,0x4E000,4)      # region info: KOR
    return bytes(image)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--kind',choices=['unreadable'],required=True);ap.add_argument('--revision',type=int,required=True);args=ap.parse_args()
    out=ROOT/'workspace/test-media/wii';out.mkdir(parents=True,exist_ok=True)
    iso=out/f'kwce-wii-{args.kind}-v{args.revision}.iso'
    if iso.exists():raise SystemExit('Existing test disc preserved')
    data=unreadable();iso.write_bytes(data)
    meta=dict(file=iso.name,sha256=hashlib.sha256(data).hexdigest(),size=len(data),synthetic=True,kind=args.kind,content='Wii header and magic only; no partitions, no game data')
    iso.with_suffix('.json').write_text(json.dumps(meta,indent=1),encoding='utf-8');print(json.dumps(meta))

if __name__=='__main__':main()

"""Private News v26: distinguish existing NEWS000006 runtime branches.

This diagnostic reports 10 + the most recent signed validation result in the
existing NEWS error number. It changes no feed, locale, clock or content data.
An adjacent error dispatch is shortened; v26 is diagnostic-only, not production.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.ppc_patch import assemble, to_file


def main():
    base = ROOT / 'workspace/channels/news'
    parent = base / 'build-v25'
    out = base / 'build-v26'
    if out.exists(): raise SystemExit('Existing build-v26 preserved')
    meta = json.loads((parent / 'build-manifest.json').read_text(encoding='utf-8'))
    raw = (parent / meta['wads']['personal']['file']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta['wads']['personal']['sha256']:
        raise ValueError('Parent hash mismatch')
    lib = load_library();title = lib.title.Title();title.load_wad(raw)
    contents = [title.get_content_by_index(i) for i in range(12)]
    exe = bytearray(contents[1]); address = 0x800095b0; at = to_file(exe, address, 12)
    original = assemble('li r29,6\nb resume', address, {'resume': 0x80009608})
    if exe[at:at + 8] != original: raise ValueError('Dispatch anchor mismatch')
    if exe[at + 8:at + 12] != assemble('lwz r0,0x1b0(r31)', address + 8, {}):
        raise ValueError('Adjacent dispatch anchor mismatch')
    patch = assemble('lwz r29,0x1bc(r31)\naddi r29,r29,10\nb resume', address, {'resume': 0x80009608})
    if len(patch) != 12: raise ValueError('Unexpected patch length')
    exe[at:at + 12] = patch;title.set_content(bytes(exe), 1)
    wad = title.dump_wad();check = lib.title.Title();check.load_wad(wad)
    if [i for i in range(12) if check.get_content_by_index(i) != contents[i]] != [1]:
        raise ValueError('Unexpected channel content changed')
    out.mkdir();(out / 'news-ko-personal.wad').write_bytes(wad)
    manifest = {'revision': 26, 'parent_revision': 25, 'diagnostic_only': True,
                'production_candidate': False, 'hardware_verified': False,
                'diagnostic': 'NEWS000006 dispatch reports 10 + last validator result; adjacent error dispatch bypassed',
                'changed_words': 3, 'changed_contents': [1],
                'wads': {'personal': {'file': 'news-ko-personal.wad', 'sha256': hashlib.sha256(wad).hexdigest()}}}
    (out / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('PASS: v26 diagnostic build; only content 1 and three PPC words changed; hardware untested')

if __name__ == '__main__': main()

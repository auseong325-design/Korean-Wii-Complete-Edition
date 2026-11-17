"""Nintendo Channel v18 candidate: fix the KOR service-language check only.

One existing call is replaced with li r3,1 (English) for the channel's
language-change comparison. The Wii language getter, HOME, strings, server
URL and all other content stay byte-identical to the v17 KOR-only build.
This is a candidate, not proof of real-console connectivity.
"""
import argparse
import copy
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN
from kwce.channels import load_library
from kwce.ppc_patch import to_file

CALL = 0x80053BD4
GET_LANGUAGE = '0x8021fa20'
OUT = 'nintendo-ko-ui-test.wad'


def build():
    base = ROOT / 'workspace/channels/nintendo'
    source = base / 'build-v17'
    meta = json.loads((source / 'build-manifest.json').read_text(encoding='utf-8'))
    wad = (source / OUT).read_bytes()
    if hashlib.sha256(wad).hexdigest() != meta['wad_sha256']:
        raise ValueError('Parent WAD does not match its manifest')
    lib = load_library()
    title = lib.title.Title(); title.load_wad(wad)
    count = len(title.tmd.content_records)
    before = [title.get_content_by_index(i) for i in range(count)]
    exe = before[1]; at = to_file(exe, CALL, 4)
    ins = list(Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN).disasm(exe[at:at+4], CALL))
    if len(ins) != 1 or ins[0].mnemonic != 'bl' or ins[0].op_str != GET_LANGUAGE:
        raise ValueError('Unexpected language-check call')
    edited = bytearray(exe); struct.pack_into('>I', edited, at, 0x38600001)
    if {i for i, (a, b) in enumerate(zip(exe, edited)) if a != b} - set(range(at, at+4)):
        raise ValueError('Edit escaped language-check instruction')
    title.set_content(bytes(edited), 1)
    result = title.dump_wad()
    check = lib.title.Title(); check.load_wad(result)
    if [i for i in range(count) if check.get_content_by_index(i) != before[i]] != [1]:
        raise ValueError('Unexpected content change')
    result_meta = copy.deepcopy(meta)
    result_meta.update(revision=18, parent_revision=17, source_build='build-v17',
                       wad_sha256=hashlib.sha256(result).hexdigest(),
                       changed_from_parent=[1], changed_content_indices=[1],
                       installed=False, runtime_verified=False,
                       service_language_fix={'call_site':hex(CALL),
                           'fallback_language':'English', 'scope':'KOR-only build; service language-change comparison',
                           'wii_system_settings_changed':False, 'global_language_getter_changed':False,
                           'real_wii_success_verified':False})
    return result, result_meta


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--reproduce', action='store_true'); args = ap.parse_args()
    wad, meta = build(); dest = ROOT / 'workspace/channels/nintendo/build-v18'
    manifest = (json.dumps(meta, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if args.reproduce:
        if not dest.is_dir() or (dest/OUT).read_bytes() != wad or (dest/'build-manifest.json').read_bytes() != manifest:
            raise SystemExit('v18 reproduction differs')
        print('PASS: Nintendo build-v18 WAD and manifest byte-identical'); return
    if dest.exists(): raise SystemExit('Existing build preserved')
    dest.mkdir(); (dest/OUT).write_bytes(wad); (dest/'build-manifest.json').write_bytes(manifest)
    print('PASS: built Nintendo v18 candidate from v17; one executable instruction changed')


if __name__ == '__main__': main()

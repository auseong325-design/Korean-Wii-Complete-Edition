"""Korean Wii Speak Channel + WiiLink's Wiimmfi patch, ported (hardware candidate).

The official Korean channel (000100014843464b v512) is already Korean. WiiLink
only publishes Wiimmfi patches for JP/USA/PAL, so kwce.wiispeak_wiimmfi ports
the JP patch to the Korean executable (content 1). All other contents stay
byte-identical. The WAD is fakesigned for the user's own console (cIOS with
signature-check patch) and is not installed anywhere by this script.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library  # noqa: E402
from kwce import bspatch  # noqa: E402
from kwce.hardware import hardware_wad  # noqa: E402
from kwce.wiiroom_formats import decompress_lz11, reencode_lz11_same_size  # noqa: E402
from kwce.wiispeak_wiimmfi import port  # noqa: E402

BASE = ROOT / 'workspace/channels/wiispeak'
NAME = 'wiispeak-ko-wiimmfi.wad'


def build():
    lib = load_library()
    acquisition = json.loads((BASE / 'originals/acquisition.json').read_text(encoding='utf-8'))
    pinned = {row['alias']: row['sha256'] for row in acquisition['titles']}
    raw = {}
    for alias in ('wiispeak-korea-v512.wad', 'wiispeak-japan-v512.wad'):
        data = (BASE / 'originals' / alias).read_bytes()
        if hashlib.sha256(data).hexdigest() != pinned[alias]:
            raise ValueError('Preserved original differs from acquisition manifest: ' + alias)
        raw[alias] = data
    patch_path = BASE / 'references/wiilink-patcher/bsdiff__ws__WiiSpeak_1_Japan.bsdiff'
    patch = patch_path.read_bytes()
    pinned_patch = {Path(r['file']).name: r['sha256'] for r in acquisition['wiilink_patcher']}
    if hashlib.sha256(patch).hexdigest() != pinned_patch[patch_path.name]:
        raise ValueError('WiiLink reference patch differs from acquisition manifest')
    korean = lib.title.Title()
    korean.load_wad(raw['wiispeak-korea-v512.wad'])
    japan = lib.title.Title()
    japan.load_wad(raw['wiispeak-japan-v512.wad'])
    if korean.tmd.title_id != '000100014843464b' or korean.tmd.title_version != 512 or korean.tmd.boot_index != 8:
        raise ValueError('Korean Wii Speak identity differs')
    stock = korean.get_content_by_index(1)
    jp_stock = japan.get_content_by_index(1)
    edited, record = port(decompress_lz11(stock), decompress_lz11(jp_stock), decompress_lz11(bspatch.apply(jp_stock, patch)))
    korean.set_content(reencode_lz11_same_size(stock, edited), 1)
    original = [lib.title.Title() for _ in range(1)][0]
    original.load_wad(raw['wiispeak-korea-v512.wad'])
    wad, checks = hardware_wad(korean.dump_wad(), raw['wiispeak-korea-v512.wad'])
    check = lib.title.Title()
    check.load_wad(wad)
    changed = [i for i in range(check.tmd.num_contents) if check.get_content_by_index(i) != original.get_content_by_index(i)]
    if changed != [1] or decompress_lz11(check.get_content_by_index(1)) != edited:
        raise ValueError('Only content 1 may change')
    manifest = dict(revision=1, title_id='000100014843464b', title_version=512, base='official Korean v512 (already Korean UI)',
                    hardware_candidate=True, hardware_success_verified=False, local_only=False,
                    full_localization_complete=False, korean_ui='official Nintendo Korean resources, unchanged',
                    network='Wiimmfi (WiiLink patcher lists Wii Speak under network Wiimmfi)', changed_contents=changed,
                    original_sha256=pinned['wiispeak-korea-v512.wad'], reference_patch_sha256=pinned_patch[patch_path.name],
                    wad_sha256=hashlib.sha256(wad).hexdigest(), port=record, hardware_checks=checks,
                    requirements='fakesigned: install only with a cIOS that has the signature-check patch; needs the Wii Speak USB microphone')
    return wad, manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reproduce', action='store_true')
    parser.add_argument('--verify', action='store_true', help='rebuild in memory and compare; writes nothing')
    args = parser.parse_args()
    out = BASE / 'hardware-v1'
    wad, manifest = build()
    if args.verify:
        stored = json.loads((out / 'build-manifest.json').read_text(encoding='utf-8'))
        if hashlib.sha256((out / NAME).read_bytes()).hexdigest() != stored['wad_sha256'] or manifest['wad_sha256'] != stored['wad_sha256']:
            raise SystemExit('FAIL: Wii Speak hardware-v1 differs from its manifest or rebuild')
        print('PASS: Wii Speak hardware-v1 rebuild byte-identical; only content 1 (Wiimmfi port) changed; not installed')
        return
    if args.reproduce:
        if (out / NAME).read_bytes() != wad:
            raise ValueError('Wii Speak hardware reproduction differs')
        number = 1
        while (ROOT / f'workspace/private/wiispeak-reproduce-v1-{number}').exists():
            number += 1
        target = ROOT / f'workspace/private/wiispeak-reproduce-v1-{number}'
        target.mkdir(parents=True)
        (target / NAME).write_bytes(wad)
        print('PASS: Wii Speak hardware-v1 reproduced byte-identically', manifest['wad_sha256'])
        return
    if out.exists():
        raise SystemExit('Existing Wii Speak hardware build preserved')
    out.mkdir(parents=True)
    (out / NAME).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Built Wii Speak hardware-v1:', manifest['wad_sha256'], 'string edits', sum(manifest['port']['string_edits'].values()),
          'code words', len(manifest['port']['dwc_words']), '; not installed')


if __name__ == '__main__':
    main()

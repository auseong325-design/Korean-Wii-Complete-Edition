"""News build-v23: the v22 hardware lineage plus a single IPC change that fixes
error 107242 on real hardware.

Root cause (lead-verified by disassembly): the WC24 IPC deadline adapter bounds
every *small* ioctl (input <=32, output <=256 bytes) with a 30s cap so a startup
call cannot hang. The News download (NWC24iDownloadNowEx -> ioctl 14) reaches IOS
with small buffers but legitimately takes longer than 30s against a live server,
so the cap returns -42 and the channel shows 107242 (= 107200 + 42 INTERNAL_IPC).

Fix: exempt ioctl 14 from the cap so it runs on the native synchronous path --
exactly the retail behaviour. This adds NO new code section (the two-instruction
check is absorbed by the adapter's existing 32-byte alignment padding, so the blob
stays 1056 bytes and the adjacent country-fallback cave at 0x801e0560 is untouched)
and cannot corrupt memory or crash boot, because the native path is what the retail
SDK used. Only "does the download now finish" is hardware-verifiable; the emulator
serves a local feed that replies instantly, so 107242 never reproduces there.

Chain mirrors the pinned scripts: build-v16 -> socket + ipc(native_ioctls=[14])
(= the v20 step with the exemption) -> News-context country fallback (= the v22
step), written as build-v23. Other channel contents stay byte-identical to v22.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.channel_socket_startup import patch as patch_socket
from kwce.channel_ipc_deadline import patch as patch_ipc
from kwce.ppc_patch import assemble, to_file

NATIVE_IOCTLS = [14]


def build():
    parent = ROOT / 'workspace/channels/news/build-v16'
    meta = json.loads((parent / 'build-manifest.json').read_text(encoding='utf-8'))
    raw = (parent / 'news-ko-personal.wad').read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta['wads']['personal']['sha256']:
        raise ValueError('News v16 parent differs')
    lib = load_library()
    t = lib.title.Title()
    t.load_wad(raw)
    original = [t.get_content_by_index(i) for i in range(12)]

    # v20 step: socket startup bound + IPC deadline adapter, now with ioctl 14 exempt.
    exe, socket_record = patch_socket(original[1], 'news')
    exe, ipc = patch_ipc(exe, 'news', NATIVE_IOCTLS)
    if ipc['bytes'] != 1056 or ipc['native_ioctls'] != NATIVE_IOCTLS:
        raise ValueError('IPC adapter size/exemption unexpected')

    # v22 step: News-context country fallback (136 -> 49) in the audited cave AFTER
    # the adapter blob. The exemption did not grow the blob, so this cave is still
    # the same zero region v22 wrote into; its guard hashes still hold.
    exe = bytearray(exe)
    entry = 0x800081f8
    cave = 0x801e0560
    offset = to_file(exe, cave, 128)
    if hashlib.sha256(exe[offset:offset + 128]).hexdigest() != \
            'fddb0a0be9c67098de878c70bb9318b71c6613691433016ea2d894666158c745':
        raise ValueError('Country cave differs (exemption must not touch 0x801e0560)')
    ep = to_file(exe, entry)
    if exe[ep:ep + 4] != bytes.fromhex('7c9d2378'):
        raise ValueError('Country instruction differs')
    body = assemble('''cmpwi cr7,r4,136
    bne cr7,preserve
    li r29,49
    b resume
preserve:
    mr r29,r4
    b resume''', cave, {'resume': entry + 4})
    br = assemble('b candidate', entry, {'candidate': cave})
    if len(body) > 128 or len(br) != 4:
        raise ValueError('Country size')
    exe[offset:offset + len(body)] = body
    exe[ep:ep + 4] = br
    t.set_content(bytes(exe), 1)

    wad = t.dump_wad()
    check = lib.title.Title()
    check.load_wad(wad)
    changed = {i for i in range(12) if check.get_content_by_index(i) != original[i]}
    if changed != {1}:
        raise ValueError('News v23 changed unrelated content: %r' % sorted(changed))
    return wad, meta, socket_record, ipc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reproduce', action='store_true')
    args = ap.parse_args()
    out = ROOT / 'workspace/channels/news/build-v23'
    expected = None
    if args.reproduce:
        if not (out / 'news-ko-personal.wad').exists():
            raise SystemExit('No build-v23 to reproduce yet')
        expected = (out / 'news-ko-personal.wad').read_bytes()
        n = 1
        while (ROOT / f'workspace/private/news-ipc-exempt-reproduce-{n}').exists():
            n += 1
        out = ROOT / f'workspace/private/news-ipc-exempt-reproduce-{n}'
    if out.exists():
        raise SystemExit('Existing News build-v23 preserved')
    wad, meta, socket_record, ipc = build()
    if expected is not None and wad != expected:
        raise SystemExit('News v23 byte-identical reproduction differs')
    h = hashlib.sha256(wad).hexdigest()
    meta.update(revision=23, parent_revision=16, derived_from='build-v22 lineage',
                socket_startup=socket_record, ipc_deadline=ipc,
                country_fallback={'from': 136, 'to': 49, 'scope': 'News constructor only',
                                  'signature_verified': False, 'hardware_verified': False},
                wads={'personal': {'file': 'news-ko-personal.wad', 'sha256': h}},
                wad_sha256=h, changed_from_parent=[1], live_service_verified=False,
                error_107242_fix={'ioctl_exempted': NATIVE_IOCTLS,
                                  'cause': 'download ioctl bounded by the 30s small-call cap',
                                  'approach': 'route the download ioctl to the native retail path',
                                  'adds_new_section': False, 'blob_bytes': ipc['bytes'],
                                  'hardware_verified': False})
    out.mkdir()
    (out / 'news-ko-personal.wad').write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: News build-v23 (107242 fix, ioctl {NATIVE_IOCTLS} exempt); content1 only; '
          f'adapter {ipc["bytes"]}B no new section; sha {h[:16]}; hardware-pending')


if __name__ == '__main__':
    main()

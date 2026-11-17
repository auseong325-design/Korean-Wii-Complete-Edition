"""News build-v24: v22 lineage, the download ioctl bounded at 10 minutes.

Hardware report 2026-10-29 (RC1, build-v23): with ioctl 14 exempt from the IPC adapter the
in-channel download screen ('내려받는 중입니다') never ended (several minutes), i.e. the
download itself does not complete on the user's console; v23 only turned the 30 s error
into an endless wait. v24 keeps the adapter bound for the download but at 6000 polls
(10 minutes) instead of 300 (30 s): a slow but working download gets ten minutes, a stalled
one ends in error 107242 instead of an endless screen. All other small WC24 ioctls keep 30 s.

Chain: build-v16 -> socket + ipc(long_ioctls=[(14, 6000)]) -> News country fallback
(136 -> 49), same steps as build-v22/v23. Only content 1 changes. The adapter must still end
at or before the country cave (0x801e0560), which is checked.
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

LONG_IOCTLS = [(14, 6000)]
IPC_CAVE = 0x801e0120
COUNTRY_CAVE = 0x801e0560


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

    exe, socket_record = patch_socket(original[1], 'news')
    exe, ipc = patch_ipc(exe, 'news', (), LONG_IOCTLS)
    if IPC_CAVE + ipc['bytes'] > COUNTRY_CAVE:
        raise ValueError(f'IPC adapter ({ipc["bytes"]}B) would reach the country cave')

    exe = bytearray(exe)
    entry = 0x800081f8
    offset = to_file(exe, COUNTRY_CAVE, 128)
    if hashlib.sha256(exe[offset:offset + 128]).hexdigest() != \
            'fddb0a0be9c67098de878c70bb9318b71c6613691433016ea2d894666158c745':
        raise ValueError('Country cave differs')
    ep = to_file(exe, entry)
    if exe[ep:ep + 4] != bytes.fromhex('7c9d2378'):
        raise ValueError('Country instruction differs')
    body = assemble('''cmpwi cr7,r4,136
    bne cr7,preserve
    li r29,49
    b resume
preserve:
    mr r29,r4
    b resume''', COUNTRY_CAVE, {'resume': entry + 4})
    br = assemble('b candidate', entry, {'candidate': COUNTRY_CAVE})
    exe[offset:offset + len(body)] = body
    exe[ep:ep + 4] = br
    t.set_content(bytes(exe), 1)

    wad = t.dump_wad()
    check = lib.title.Title()
    check.load_wad(wad)
    changed = {i for i in range(12) if check.get_content_by_index(i) != original[i]}
    if changed != {1}:
        raise ValueError('News v24 changed unrelated content: %r' % sorted(changed))
    return wad, meta, socket_record, ipc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reproduce', action='store_true')
    args = ap.parse_args()
    out = ROOT / 'workspace/channels/news/build-v24'
    expected = None
    if args.reproduce:
        expected = (out / 'news-ko-personal.wad').read_bytes()
        n = 1
        while (ROOT / f'workspace/private/news-v24-reproduce-{n}').exists():
            n += 1
        out = ROOT / f'workspace/private/news-v24-reproduce-{n}'
    if out.exists():
        raise SystemExit('Existing News build-v24 preserved')
    wad, meta, socket_record, ipc = build()
    if expected is not None and wad != expected:
        raise SystemExit('News v24 byte-identical reproduction differs')
    h = hashlib.sha256(wad).hexdigest()
    meta.update(revision=24, parent_revision=16, derived_from='build-v22 lineage',
                socket_startup=socket_record, ipc_deadline=ipc,
                country_fallback={'from': 136, 'to': 49, 'scope': 'News constructor only',
                                  'signature_verified': False, 'hardware_verified': False},
                wads={'personal': {'file': 'news-ko-personal.wad', 'sha256': h}},
                wad_sha256=h, changed_from_parent=[1], live_service_verified=False,
                download_bound={'ioctl': 14, 'polls': 6000, 'seconds': 600,
                                'why': 'v23 unbounded download never finished on hardware (endless screen)',
                                'adds_new_section': False, 'blob_bytes': ipc['bytes'],
                                'hardware_verified': False})
    out.mkdir()
    (out / 'news-ko-personal.wad').write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: News build-v24 (download ioctl 14 bounded at 600 s); content1 only; '
          f'adapter {ipc["bytes"]}B ends {hex(IPC_CAVE + ipc["bytes"])}; sha {h[:16]}')


if __name__ == '__main__':
    main()

"""News build-v25: v24 lineage, every long-running WC24 (KD) request bounded at 10 minutes.

RC3 analysis (workspace/channels/news/rc3-download-analysis.md, 2026-10-30): the hardware
error 050330 seen with build-v22 is produced by OUR IPC adapter, not by the service: KD
ioctl 6 (NWC24iStartupSocket, the request that brings the network up) hit the adapter's
30 s bound, returned -42 and the channel mapped it to 050330. ioctl 14 (DownloadNowEx) had
the same problem (107242) and was moved to a 10 minute bound in build-v24. v25 gives the
same finite 10 minute bound (6000 polls) to ioctl 6 and to ioctl 30 (scheduler status), so a
slow Wi-Fi association or a slow first fill (24 hourly files, about 2.5 MB) is not cut at
30 s, while a stalled request still ends in an error instead of an endless screen.

Chain: build-v16 -> socket + ipc(long_ioctls 6/14/30 at 6000 polls) -> News country
fallback (136 -> 49), exactly the build-v24 steps otherwise. Only content 1 changes; the
adapter must still end at or before the country cave (0x801e0560), which is checked.
build-v24 (scripts/build_news_download_bound.py) is not modified and still reproduces.
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

REVISION = 25
LONG_IOCTLS = [(6, 6000), (14, 6000), (30, 6000)]
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
        raise ValueError('News v25 changed unrelated content: %r' % sorted(changed))
    return wad, meta, socket_record, ipc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reproduce', action='store_true')
    args = ap.parse_args()
    out = ROOT / f'workspace/channels/news/build-v{REVISION}'
    expected = None
    if args.reproduce:
        expected = (out / 'news-ko-personal.wad').read_bytes()
        n = 1
        while (ROOT / f'workspace/private/news-v{REVISION}-reproduce-{n}').exists():
            n += 1
        out = ROOT / f'workspace/private/news-v{REVISION}-reproduce-{n}'
    if out.exists():
        raise SystemExit(f'Existing News build-v{REVISION} preserved')
    wad, meta, socket_record, ipc = build()
    if expected is not None and wad != expected:
        raise SystemExit(f'News v{REVISION} byte-identical reproduction differs')
    h = hashlib.sha256(wad).hexdigest()
    meta.update(revision=REVISION, parent_revision=16, derived_from='build-v24 lineage',
                socket_startup=socket_record, ipc_deadline=ipc,
                country_fallback={'from': 136, 'to': 49, 'scope': 'News constructor only',
                                  'signature_verified': False, 'hardware_verified': False},
                wads={'personal': {'file': 'news-ko-personal.wad', 'sha256': h}},
                wad_sha256=h, changed_from_parent=[1], live_service_verified=False,
                download_bound={'ioctls': [c for c, _ in LONG_IOCTLS], 'polls': 6000, 'seconds': 600,
                                'why': '050330 = ioctl 6 cut by our 30 s bound; 107242 = ioctl 14 likewise '
                                       '(workspace/channels/news/rc3-download-analysis.md)',
                                'adds_new_section': False, 'blob_bytes': ipc['bytes'],
                                'hardware_verified': False})
    if expected is not None:
        print(f'PASS: News build-v{REVISION} reproduced byte-identically; sha {h[:16]}')
        return
    out.mkdir()
    (out / 'news-ko-personal.wad').write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: News build-v{REVISION} (KD ioctls 6/14/30 bounded at 600 s); content1 only; '
          f'adapter {ipc["bytes"]}B ends {hex(IPC_CAVE + ipc["bytes"])}; sha {h[:16]}')


if __name__ == '__main__':
    main()

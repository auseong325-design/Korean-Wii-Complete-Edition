"""Read-only identity gate for the channel-independent DVD test bed."""
import hashlib
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(install, library):
    package = install['native_package']
    if not re.fullmatch(r'kwce-rc-sd-v[1-9][0-9]*', package):
        raise ValueError('Unexpected native DVD package')
    bed = ROOT / 'workspace/sandbox' / install['profile']
    meta = json.loads((bed / 'test-bed-manifest.json').read_text(encoding='utf-8'))
    if not meta.get('channel_independent'):
        raise ValueError('Native test marker missing')
    nand = bed / 'user/Wii'
    if any((nand / path).exists() for path in
           ('title/00010001/4b445644', 'ticket/00010001/4b445644.tik')):
        raise ValueError('Native DVD must have no player title')
    hardware = ROOT / 'workspace/hardware' / package
    raw = (hardware / 'package-manifest.json').read_bytes()
    sha = lambda data: hashlib.sha256(data).hexdigest()
    if sha(raw) != (hardware / 'package-manifest.sha256').read_text().strip():
        raise ValueError('Native package manifest differs')
    pin = json.loads(raw)['config']['native_dvd']
    from .dvd_native_hardware import runtime_files
    resources = runtime_files(pin, library)
    for path, data in resources.items():
        if (hardware / path).read_bytes() != data or (bed / 'sd-sync' / path).read_bytes() != data:
            raise ValueError('Native SD resource differs')
    player = ROOT / 'workspace/channels/dvd-player' / install['artifact']
    manifest = json.loads((player / 'build-manifest.json').read_text(encoding='utf-8'))
    expected = manifest['boot_dol_sha256']
    if sha((player / 'boot.dol').read_bytes()) != expected or meta['native_hook']['player_sha256'] != expected:
        raise ValueError('Native player identity differs')
    if sha((bed / 'sd-sync/apps/kwce-dvd/boot.dol').read_bytes()) != expected:
        raise ValueError('Direct test player differs')
    if meta['native_hook']['sha256'] != pin['hook_sha256']:
        raise ValueError('Native hook identity differs')
    content = nand / 'title/00000001/00000002/content'
    tmd = (content / 'title.tmd').read_bytes()
    actual = {}
    for i in range(int.from_bytes(tmd[0x1de:0x1e0], 'big')):
        cid, index = struct.unpack_from('>IH', tmd, 0x1e4+36*i)
        if str(index) in meta['system_menu_contents']:
            actual[str(index)] = sha((content / f'{cid:08x}.app').read_bytes())
    if actual != meta['system_menu_contents'] or actual['6'] != pin['hook_sha256']:
        raise ValueError('Native menu installation differs')
    return len(resources)

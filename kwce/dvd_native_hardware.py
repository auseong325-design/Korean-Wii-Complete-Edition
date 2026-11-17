"""Pinned channel-independent DVD memory hack and SD resources."""
import hashlib
import json
from pathlib import Path
from .dvd_native_hook import CAVE,END,BANNER,BANNER_END,ORIGINAL,SITES
from .ppc_patch import to_file
from .gc_native import patch_gc_native
from .priiloader_hacks import _runs,_split,_unique_hash,_words,DVD_GROUP

ROOT=Path(__file__).resolve().parents[1]
RUNTIME='kwce/dvd'


def entry(menu,pin):
    folder=ROOT/'workspace/experiments'/pin['hook']
    hook_record=json.loads((folder/'manifest.json').read_text())
    if hook_record.get('sd_worker_service'):
        raise ValueError('Integrated service requires its separate qualification gate')
    if hook_record.get('local_only') or hook_record.get('source_revision')==33:
        raise ValueError('Local-only SD ownership review must not be packaged for hardware')
    if hook_record.get('source_revision') in (12,14,16,19,20,22,23):raise ValueError('Diagnostic drive simulation cannot be packaged')
    patched=(folder/'menu.dol').read_bytes()
    if hashlib.sha256(patched).hexdigest()!=pin['hook_sha256']:raise ValueError('Native DVD hook differs from reviewed pin')
    base=patch_gc_native(menu,japanese_cards=True,japanese_comments=True)[0]
    if len(patched)!=len(base):raise ValueError('Native DVD hook changes DOL size')
    sites=list(SITES)
    if hook_record.get("source_revision") in (28,29,30,31,32):sites.append(0x8135E820)
    if pin.get('icon'):sites.append(0x813A9FBC)
    ranges=[(to_file(menu,a,b-a),to_file(menu,a,b-a)+b-a) for a,b in
            [(ORIGINAL,ORIGINAL+0x740),(BANNER,BANNER_END),(CAVE,END),*[(a,a+4) for a in sites]]]
    runs=_runs(base,patched)
    if not runs or any(not any(lo<=a<b<=hi for lo,hi in ranges) for a,b in runs):
        raise ValueError('Native hook changes bytes outside reviewed RAM sites')
    pairs=[(_unique_hash(menu,a,(b-a)//4),_words(patched,a,b)) for a,b in _split(runs,64)]
    return dict(name=DVD_GROUP,minimum=518,maximum=518,pairs=pairs)


def runtime_files(pin,lib):
    module=ROOT/'workspace/experiments'/pin['module']
    record=json.loads((module/'manifest.json').read_text())
    data=(module/'player.ash').read_bytes()
    if hashlib.sha256(data).hexdigest()!=pin['module_sha256'] or record['packed_sha256']!=pin['module_sha256']:
        raise ValueError('Native DVD module differs')
    hook=json.loads((ROOT/'workspace/experiments'/pin['hook']/'manifest.json').read_text())
    if hook['module_sha256']!=pin['module_sha256'] or hook['player_sha256']!=record['source_sha256']:
        raise ValueError('Native module and loader pins disagree')
    banner=(ROOT/'workspace/experiments'/pin['banner']/'menu.arc').read_bytes()
    if hashlib.sha256(banner).hexdigest()!=pin['banner_sha256']:raise ValueError('Native banner differs')
    home=(ROOT/f'workspace/channels/dvd-player/home-ui-v{pin["home_ui"]}/home.arc').read_bytes()
    if hashlib.sha256(home).hexdigest()!=pin['home_sha256']:raise ValueError('Native HOME differs')
    wad=ROOT/f'workspace/channels/dvd-player/wad-v{pin["font_wad"]}/dvd-player.wad'
    if hashlib.sha256(wad.read_bytes()).hexdigest()!=pin['font_wad_sha256']:raise ValueError('Font source WAD differs')
    title=lib.title.Title();title.load_wad(wad.read_bytes())
    font=title.get_content_by_index(2)
    result={f'{RUNTIME}/boot.ash':data,f'{RUNTIME}/menu.arc':banner,
            f'{RUNTIME}/home.arc':home,f'{RUNTIME}/wbf1.brfna':font}
    if pin.get('icon'):
        icon=(ROOT/'workspace/experiments'/pin['icon']/'icon.arc').read_bytes()
        if hashlib.sha256(icon).hexdigest()!=pin['icon_sha256'] or hook.get('icon_sha256')!=pin['icon_sha256']:
            raise ValueError('Native DVD icon differs from loader pin')
        result[f'{RUNTIME}/icon.arc']=icon
    return result

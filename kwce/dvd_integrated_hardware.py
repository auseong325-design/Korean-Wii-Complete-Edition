"""RAM definitions for the integrated DVD service; never a NAND installer.

Definition construction is local verification, not deployment authorization.
Hardware export must additionally pass the bound qualification gate.
"""
import hashlib
import json
from pathlib import Path
from .dvd_integrated_hook import REGIONS, DEBUG_GUARDS, sites, ORIGINAL
from .gc_native import patch_gc_native
from .ppc_patch import to_file
from .priiloader_hacks import _runs, _split, _unique_hash, _words, DVD_GROUP
from .priiloader_legacy import checked_ini, parse, apply_streaming
ROOT=Path(__file__).resolve().parents[1]


def definition(revision=66):
    folder=ROOT/f'workspace/experiments/dvd-native-hook-v{revision}'
    record=json.loads((folder/'manifest.json').read_text())
    if record['source_revision']!=37 or not record.get('board_lifetime_cache'):
        raise ValueError('Unreviewed integrated source')
    patched=(folder/'menu.dol').read_bytes()
    if hashlib.sha256(patched).hexdigest()!=record['sha256']:
        raise ValueError('Frozen candidate changed')
    menu=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    base=patch_gc_native(menu,japanese_cards=True,japanese_comments=True)[0]
    if len(patched)!=len(base):raise ValueError('DOL size changed')
    regions=[*REGIONS,(ORIGINAL,ORIGINAL+56),
             *[(a,a+len(b))for a,b in DEBUG_GUARDS.items()],
             *[(a,a+4)for a in sites(menu)]]
    ranges=[(to_file(menu,a),to_file(menu,b-1)+1)for a,b in regions]
    merged=[]
    for lo,hi in sorted(ranges):
        if merged and lo<=merged[-1][1]:merged[-1]=(merged[-1][0],max(hi,merged[-1][1]))
        else:merged.append((lo,hi))
    ranges=merged
    runs=_runs(base,patched)
    if not runs or any(not any(lo<=a<b<=hi for lo,hi in ranges)for a,b in runs):
        raise ValueError('Integrated patch escaped reviewed regions')
    pairs=[(_unique_hash(menu,a,(b-a)//4),_words(patched,a,b))for a,b in _split(runs,64)]
    row=dict(name=DVD_GROUP,minimum=518,maximum=518,pairs=pairs)
    raw=checked_ini(menu,[row],packed=True)
    if apply_streaming(base,parse(raw))!=patched:
        raise ValueError('Legacy sequential patch differs')
    return raw

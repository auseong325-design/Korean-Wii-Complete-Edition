"""Bounded R53 startup trace, preserving the native66 service implementation."""
import hashlib
import json
from pathlib import Path
import re
from .dvd_integrated_sd import ROOT, TARGETS, DEFINITIONS, qualified
from .dvd_integrated_hardware import definition
from .gcmce_recovery import sha, direct
from .gc_card_encoding_sd import wii_mount
from .priiloader_legacy import parse, apply_streaming
from .priiloader_hacks import DVD_GROUP

README='KWCE-DVD-PLAYER-TRACE-v1-ko.txt'
MANIFEST='KWCE-DVD-PLAYER-TRACE-v1-manifest.json'
MODULE='kwce/dvd/boot.ash'
PATHS=TARGETS|{MODULE,README}


def upgrade(raw,before_revision=66,after_revision=67):
    if (before_revision,after_revision) not in ((66,67),(67,68),(68,69),(69,70),(70,71),(71,72),(72,74),(72,75),(72,76),(76,77)):
        raise ValueError('Unreviewed player transition')
    before=parse(raw)
    if [r for r in before if r['name']==DVD_GROUP]!=parse(definition(before_revision)):
        raise ValueError('Expected native66 definition')
    pattern=rb'(?m)^\['+re.escape(DVD_GROUP.encode())+rb'\]\r\n.*?(?=^\[|\Z)'
    changed,n=re.subn(pattern,lambda _:definition(after_revision),raw,flags=re.S)
    after=parse(changed)
    if n!=1 or [r for r in before if r['name']!=DVD_GROUP]!=[r for r in after if r['name']!=DVD_GROUP]:
        raise ValueError('Another hack changed')
    base=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    expected=(ROOT/f'workspace/experiments/dvd-native-hook-v{after_revision}/menu-with-card-encoding.dol').read_bytes()
    # Fragments also contain the three GC definitions, like the complete file.
    if apply_streaming(base,[r for r in after if r['name'].startswith('KWCE ')])!=expected:
        raise ValueError('Legacy combined result differs')
    return changed


def sd_files(package):
    package=Path(package);raw=(package/'package-manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=(package/'package-manifest.sha256').read_text().strip():
        raise ValueError('Trace manifest mismatch')
    m=json.loads(raw)
    version={'dvd-player-trace-v1':1,'dvd-player-trace-v2':2,'dvd-player-trace-v3':3,'dvd-player-trace-v4':4,'dvd-player-trace-v5':5,'dvd-player-trace-v6':6}.get(m.get('kind'),0)
    if not version: raise ValueError('Unreviewed player package')
    player_revision,hook_revision,module_revision={1:(53,67,12),2:(54,68,13),3:(55,69,14),4:(56,70,15),5:(57,71,16),6:(58,72,17)}[version]
    readme=README.replace('v1',f'v{version}')
    manifest=MANIFEST.replace('v1',f'v{version}')
    paths=TARGETS|{MODULE,readme}
    if (m.get('kind') not in ('dvd-player-trace-v1','dvd-player-trace-v2','dvd-player-trace-v3','dvd-player-trace-v4','dvd-player-trace-v5','dvd-player-trace-v6') or m.get('nand_write') is not False or
        m.get('physical_dvd_verified') is not False or m.get('gc_changed') is not False or
        m.get('player_revision')!=player_revision or m.get('hook_revision')!=hook_revision or
        set(m.get('files',{}))!=paths or set(m.get('expected_inputs',{}))!=DEFINITIONS):
        raise ValueError('Trace package scope mismatch')
    q=direct(package/'qualification.json',package)
    if sha(q)!=m['qualification_sha256']:raise ValueError('Trace qualification pin changed')
    proof=qualified(q,hook_revision)
    if version>=2 and proof['checks'].get('failed_read_without_error_query') is not True:
        raise ValueError('Failed-read return qualification missing')
    if version>=3 and proof['checks'].get('dvd_video_permission_lifecycle') is not True:
        raise ValueError('DVD permission qualification missing')
    if version>=4 and proof['checks'].get('exact_read_cache_contract') is not True:
        raise ValueError('Exact-read cache qualification missing')
    if version>=5 and proof['checks'].get('first_read_sequence_contract') is not True:
        raise ValueError('First-read qualification missing')
    if version>=6 and proof['checks'].get('dvd_disable_bit_clear_contract') is not True:
        raise ValueError('DVD disable polarity qualification missing')
    if not all(proof['checks'].get(k) is True for k in ('player_trace_boundaries','player_reproducibility','runtime_error_return')):
        raise ValueError('Trace player qualification incomplete')
    prior=json.loads((ROOT/'workspace/hardware/kwce-dvd-integrated-v1/package-manifest.json').read_text())
    expected_runtime=prior['runtime_inputs']
    if version>=2:
        previous=json.loads((ROOT/f'workspace/hardware/kwce-dvd-player-trace-v{version-1}/package-manifest.json').read_text())
        expected_runtime={**expected_runtime,MODULE:previous['files'][MODULE]}
    if m.get('runtime_inputs')!=expected_runtime:
        raise ValueError('Previous runtime pins differ')
    old={r:direct(package/'expected'/r,package).read_bytes()for r in DEFINITIONS}
    if any(hashlib.sha256(b).hexdigest()!=m['expected_inputs'][r]for r,b in old.items()):
        raise ValueError('Expected definitions changed')
    # Ensure a current frozen player/module pair, not an arbitrary boot file.
    from .formats import ash_decompress
    module=direct(package/MODULE,package).read_bytes()
    player=ROOT/f'workspace/channels/dvd-player/build-v{player_revision}'
    build=json.loads((player/'build-manifest.json').read_text())
    if (build.get('host')!='linux' or build.get('css_decryption') is not False or
        sha(player/'boot.dol')!=build['boot_dol_sha256'] or
        module!=(ROOT/f'workspace/experiments/dvd-native-module-v{module_revision}/player.ash').read_bytes() or
        ash_decompress(module)!=(player/'boot.dol').read_bytes()):
        raise ValueError('Trace player/module mismatch')
    files=[]
    for rel in sorted(paths-{'apps/Priiloader/hacks_hash.ini'})+['apps/Priiloader/hacks_hash.ini']:
        p=direct(package/rel,package)
        if sha(p)!=m['files'][rel]:raise ValueError('Trace payload mismatch')
        if rel in TARGETS and p.read_bytes()!=upgrade(old[rel],hook_revision-1,hook_revision):raise ValueError('Trace definition differs')
        files.append((p,rel))
    files.append((package/'package-manifest.json',manifest))
    return m,files


def verify_card(package,card):
    m,files=sd_files(package);card=Path(card);wii_mount(card)
    for rel,h in (m['expected_inputs']|m['runtime_inputs']).items():
        if sha(direct(card/rel,card))!=h:raise ValueError('SD changed since trace review')
    for _,rel in files:
        p=direct(card/rel,card)
        if p.with_name(p.name+'.kwce-new').exists():raise ValueError('Existing staged file retained')
        if rel not in TARGETS|{MODULE} and p.exists():raise ValueError('Numbered delivery already exists')

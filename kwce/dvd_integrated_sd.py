"""Verified native66 RAM service definitions; no IOS/menu NAND writes."""
import hashlib
import json
from pathlib import Path
import re
from .dvd_integrated_hardware import definition
from .dvd_prefetch_sd import definitions
from .gc_card_encoding_sd import DEFINITIONS, wii_mount
from .gcmce_recovery import direct, sha
from .priiloader_hacks import DVD_GROUP, GC_LAYOUT_GROUP
from .priiloader_legacy import checked_ini, parse, apply_streaming
ROOT=Path(__file__).resolve().parents[1]
TARGETS={'apps/Priiloader/hacks_hash.ini','kwce-rc/priiloader/gc-dvd.ini',
         'kwce-rc/priiloader/fragment-gc-dvd.ini'}
README='KWCE-DVD-INTEGRATED-ko.txt'
PATHS=TARGETS|{README}
REQUIRED={'ppc_regressions','legacy_streaming','cave_reference_audit','sdk_lifecycle',
          'exact_candidate_boot','thumbnail_to_settings','settings_return_reload',
          'disc_channel_banner','player_handoff','full_linux_gates','source_reproducibility'}


def qualified(path,revision=66):
    j=json.loads(Path(path).read_text())
    if revision not in (66,67,68,69,70,71,72,74,75,76,77):raise ValueError('Unreviewed integrated revision')
    folder=ROOT/f'workspace/experiments/dvd-native-hook-v{revision}'
    if (j.get('revision')!=revision or j.get('source_revision')!=37 or
        j.get('sha256')!=sha(folder/'menu.dol') or
        j.get('card_encoding_sha256')!=sha(folder/'menu-with-card-encoding.dol') or
        j.get('physical_dvd_verified') is not False or
        not REQUIRED<=set(j.get('checks',{})) or
        any(j['checks'][k] is not True for k in REQUIRED)):
        raise ValueError('Integrated candidate qualification incomplete or mismatched')
    for rel,h in j.get('evidence',{}).items():
        if sha(direct(ROOT/rel,ROOT))!=h:raise ValueError('Qualification evidence changed')
    if not j.get('evidence'):raise ValueError('Qualification evidence missing')
    return j


def upgrade(raw):
    old=parse(checked_ini(definitions(60,61)[0],[definitions(60,61)[2]],packed=True))[0]
    if [r for r in parse(raw)if r['name']==DVD_GROUP]!=[old]:
        raise ValueError('Expected frozen native61 definition')
    pattern=rb'(?m)^\['+re.escape(DVD_GROUP.encode())+rb'\]\r\n.*?(?=^\[|\Z)'
    result,n=re.subn(pattern,lambda _:definition(),raw,flags=re.S)
    if n!=1:raise ValueError('Ambiguous DVD section')
    before,after=parse(raw),parse(result)
    if [r for r in before if r['name']!=DVD_GROUP]!=[r for r in after if r['name']!=DVD_GROUP]:
        raise ValueError('Another section changed')
    menu=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    want=(ROOT/'workspace/experiments/dvd-native-hook-v66/menu-with-card-encoding.dol').read_bytes()
    if apply_streaming(menu,[r for r in after if r['name'].startswith(('KWCE GC:','KWCE DVD:'))])!=want:
        raise ValueError('Legacy combined GC/DVD result differs')
    return result


def sd_files(package):
    package=Path(package);raw=(package/'package-manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=(package/'package-manifest.sha256').read_text().strip():
        raise ValueError('Integrated manifest mismatch')
    m=json.loads(raw)
    if (m.get('kind')!='dvd-integrated-service-v1' or m.get('nand_write') is not False or
        m.get('player_changed') is not False or m.get('gc_changed') is not False or
        set(m.get('files',{}))!=PATHS or set(m.get('expected_inputs',{}))!=DEFINITIONS):
        raise ValueError('Integrated package scope mismatch')
    q=direct(package/'qualification.json',package)
    if sha(q)!=m['qualification_sha256']:raise ValueError('Qualification pin mismatch')
    qualified(q)
    old={rel:direct(package/'expected'/rel,package).read_bytes()for rel in DEFINITIONS}
    if any(hashlib.sha256(data).hexdigest()!=m['expected_inputs'][rel]for rel,data in old.items()):
        raise ValueError('Expected input mismatch')
    active=parse(old['apps/Priiloader/hacks_hash.ini'])
    gc=parse(old['kwce-rc/priiloader/gc-only.ini']);dvd=parse(old['kwce-rc/priiloader/gc-dvd.ini'])
    if active!=gc or [r for r in gc if r['name']!=GC_LAYOUT_GROUP]!=[r for r in dvd if r['name']!=DVD_GROUP]:
        raise ValueError('Unreviewed GC-only to DVD mode transition')
    result=[]
    # Update templates first and active definition last.
    for rel in sorted(PATHS-{'apps/Priiloader/hacks_hash.ini'})+['apps/Priiloader/hacks_hash.ini']:
        src=direct(package/rel,package)
        if sha(src)!=m['files'][rel]:raise ValueError('Integrated payload changed')
        if rel in TARGETS:
            base=old['kwce-rc/priiloader/gc-dvd.ini']if rel=='apps/Priiloader/hacks_hash.ini'else old[rel]
            if src.read_bytes()!=upgrade(base):raise ValueError('Definition differs from reviewed transition')
        result.append((src,rel))
    result.append((package/'package-manifest.json','KWCE-DVD-INTEGRATED-manifest.json'))
    return m,result


def verify_card(package,card):
    m,files=sd_files(package);card=Path(card);wii_mount(card)
    for rel,h in {**m['expected_inputs'],**m['runtime_inputs']}.items():
        if sha(direct(card/rel,card))!=h:raise ValueError('SD changed since integrated review')
    for _,rel in files:
        p=direct(card/rel,card)
        if p.with_name(p.name+'.kwce-new').exists():raise ValueError('Existing staged file retained')
        if rel not in TARGETS and p.exists():raise ValueError('Existing numbered delivery retained')

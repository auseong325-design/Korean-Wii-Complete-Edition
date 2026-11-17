"""Replace only native57 DVD definitions with native58 deferred-prefetch candidate."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from .dvd_native_hardware import entry
from .gc_card_encoding import patch_card_encodings
from .gc_card_encoding_sd import DEFINITIONS, wii_mount
from .gcmce_recovery import direct, sha
from .priiloader_hacks import DVD_GROUP
from .priiloader_legacy import apply_streaming, checked_ini, parse

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {'apps/Priiloader/hacks_hash.ini', 'kwce-rc/priiloader/gc-dvd.ini',
           'kwce-rc/priiloader/fragment-gc-dvd.ini'}
README = 'KWCE-DVD-DEFERRED-PREFETCH-ko.txt'
PATHS = TARGETS | {README}


@lru_cache(maxsize=4)
def definitions(before=57,after=58):
    if (before,after) not in ((57,58),(58,59),(59,60),(60,61)):
        raise ValueError('Unreviewed DVD definition transition')
    menu = (ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    entries = []
    for revision in (before,after):
        folder = ROOT/f'workspace/experiments/dvd-native-hook-v{revision}'
        meta = json.loads((folder/'manifest.json').read_text())
        expected_source={57:29,58:30,59:30,60:31,61:32}[revision]
        if (meta['source_revision'],meta['player_revision'],meta['module_revision']) != (expected_source,51,10):
            raise ValueError('Unexpected frozen DVD revision')
        if revision==59:
            if meta.get('thumbnail_hook') is not False:
                raise ValueError('Native59 must restore the stock thumbnail call')
            from .ppc_patch import to_file
            previous=(ROOT/'workspace/experiments/dvd-native-hook-v58/menu.dol').read_bytes()
            current=(folder/'menu.dol').read_bytes()
            at=to_file(menu,0x813A9FBC)
            if (current[:at]!=previous[:at] or current[at+4:]!=previous[at+4:]
                    or current[at:at+4]!=menu[at:at+4]):
                raise ValueError('Native59 changes more than one stock SDK call site')
        if revision==60:
            if meta.get('icon_cache_store') is not True or meta.get('thumbnail_hook') is False:
                raise ValueError('Native60 must publish icon cache and restore its thumbnail hook')
            old_source=ROOT/'workspace/experiments/dvd-native-hook-v58/source'
            for original in old_source.iterdir():
                expected=original.read_bytes()
                if original.name=='loader.c':
                    needle=b'    icon_data=data;return data;'
                    if expected.count(needle)!=1:raise ValueError('Ambiguous icon publication')
                    expected=expected.replace(needle,b'    FN(0x8150671C,void (*)(void *,u32))(data,ICON_SIZE);\r\n'+needle)
                if (folder/'source'/original.name).read_bytes()!=expected:
                    raise ValueError('Native60 changes more than post-validation icon cache publication')
        if revision==61:
            if (meta.get('thumbnail_read_control') is not True
                    or meta.get('icon_cache_store') is not True
                    or meta.get('thumbnail_hook') is False):
                raise ValueError('Native61 must preserve the verified read path and use its control hook')
            old_source=ROOT/'workspace/experiments/dvd-native-hook-v60/source'
            for original in old_source.iterdir():
                old=original.read_bytes();new=(folder/'source'/original.name).read_bytes()
                if original.name=='banner.c':
                    before_marker=b'/* Thumbnail code runs only'
                    after_marker=b'/* Read-path control:'
                    if old.count(before_marker)!=1 or new.count(after_marker)!=1:
                        raise ValueError('Ambiguous read control source')
                    prefix,tail=new.split(after_marker)
                    if (prefix!=old.split(before_marker)[0]
                            or hashlib.sha256(after_marker+tail).hexdigest()!=
                            '102d233f7841e25cdf6bec7d6468ac37348da4f052a46bc7ab1d2aebba016181'):
                        raise ValueError('Native61 changes more than the reviewed thumbnail control')
                elif new!=old:
                    raise ValueError('Native61 changes another source file')
        entries.append(entry(menu,dict(hook=folder.name,hook_sha256=meta['sha256'],icon=True)))
    return menu, entries[0], entries[1]


def upgrade_definition(raw,*,before=57,after=58):
    menu, old, new = definitions(before,after)
    rows = parse(raw)
    selected = [r for r in rows if r['name']==DVD_GROUP]
    expected = parse(checked_ini(menu,[old],packed=True))[0]
    if selected != [expected]:
        raise ValueError(f'Existing DVD section differs from frozen native{before}')
    pattern = rb'(?m)^\['+re.escape(DVD_GROUP.encode())+rb'\]\r\n.*?(?=^\[|\Z)'
    matches = list(re.finditer(pattern,raw,re.S))
    if len(matches)!=1: raise ValueError('Ambiguous DVD section')
    match=matches[0]
    result=raw[:match.start()]+checked_ini(menu,[new],packed=True)+raw[match.end():]
    updated=parse(result)
    if [r['name']for r in rows]!=[r['name']for r in updated]:
        raise ValueError('DVD update changed section names/order')
    if any(a!=b for a,b in zip(rows,updated) if a['name']!=DVD_GROUP):
        raise ValueError('DVD update changed another hack')
    frozen=(ROOT/f'workspace/experiments/dvd-native-hook-v{after}/menu.dol').read_bytes()
    expected_menu=patch_card_encodings(frozen)[0]
    kw=[r for r in updated if r['name'].startswith(('KWCE GC:','KWCE DVD:'))]
    if apply_streaming(menu,kw)!=expected_menu:
        raise ValueError(f'Legacy parser result differs from reviewed native{after} plus GC encoding')
    return result


def _sd_files(package,*,kind,paths,before,after,manifest_name):
    package=Path(package).resolve()
    raw=(package/'package-manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=(package/'package-manifest.sha256').read_text().strip():
        raise ValueError('DVD deferred-prefetch manifest mismatch')
    meta=json.loads(raw)
    if (meta.get('kind')!=kind or meta.get('nand_write') is not False
            or meta.get('player_changed') is not False or meta.get('gc_changed') is not False
            or set(meta.get('files',{}))!=paths or set(meta.get('expected_inputs',{}))!=DEFINITIONS):
        raise ValueError('DVD deferred-prefetch scope mismatch')
    result=[]
    for rel in sorted(paths):
        src=direct(package/rel,package)
        if sha(src)!=meta['files'][rel]:raise ValueError('DVD candidate payload hash mismatch')
        if rel in TARGETS:
            old=direct(package/'expected'/rel,package)
            if sha(old)!=meta['expected_inputs'][rel]:raise ValueError('DVD candidate input mismatch')
            if src.read_bytes()!=upgrade_definition(old.read_bytes(),before=before,after=after):
                raise ValueError('Candidate changes more than reviewed DVD section')
        result.append((src,rel))
    result.append((package/'package-manifest.json',manifest_name))
    return meta,result


def sd_files(package):
    return _sd_files(package,kind='dvd-deferred-prefetch-v1',paths=PATHS,before=57,after=58,
                     manifest_name='KWCE-DVD-DEFERRED-PREFETCH-manifest.json')


def verify_card(package,card,*,verifier=None):
    package,card=Path(package).resolve(),Path(card).resolve()
    meta,files=(verifier or sd_files)(package)
    wii_mount(card)
    for rel,expected in {**meta['expected_inputs'],**meta['runtime_inputs']}.items():
        if sha(direct(card/rel,card))!=expected:
            raise ValueError('SD definitions/runtime changed since candidate review')
    for _,rel in files:
        path=direct(card/rel,card)
        if path.with_name(path.name+'.kwce-new').exists():raise ValueError('Existing SD stage retained')
        if rel not in TARGETS and path.exists():raise ValueError('Existing DVD candidate information retained')

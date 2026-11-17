"""Priiloader in-memory System Menu hacks for the KWCE GC patch (43K v518 only).

The Phase 1 GC menu patch (kwce.gc_native) only changes instruction words of
the menu DOL, so it can be applied by Priiloader at boot instead of writing a
patched System Menu to NAND. Each changed run becomes one hash/patch pair:
the hash is the original words from the run start, extended until the
sequence is unique in the DOL; the patch is the new words for the run.
Disable a hack (or all) from the Priiloader menu (hold RESET at power-on).
"""
import hashlib,struct
from .gc_native import patch_gc_native
from .dvd_disc_hook import patch_dvd_hook
from .patches import MENU_SHA1

VERSION=518  # System Menu 4.3K

def _runs(old,new):
    runs=[];i=0;n=len(old)//4
    while i<n:
        if old[4*i:4*i+4]!=new[4*i:4*i+4]:
            j=i
            while j<n and old[4*j:4*j+4]!=new[4*j:4*j+4]:j+=1
            runs.append((4*i,4*j));i=j
        else:i+=1
    return runs

def _words(data,start,end):
    return list(struct.unpack_from(f'>{(end-start)//4}I',data,start))

def _unique_hash(data,start,minimum):
    for length in range(max(2,minimum),max(2,minimum)+64):
        pattern=data[start:start+4*length]
        positions=[];at=data.find(pattern)
        while at!=-1:
            if at%4==0:positions.append(at)
            at=data.find(pattern,at+4)
        if positions==[start]:return _words(data,start,start+4*length)
    raise ValueError('No unique hash found')

GROUPS=[('KWCE GC: Wii/GC save menu',False,False),('KWCE GC: Japanese memory card encoding',True,False),('KWCE GC: Japanese save comments (CP932)',True,True)]
# Disc channel -> DVD player channel (kwce.dvd_disc_hook). Its sites and code cave do not
# overlap the GC patch, so this hack also works alone (hashes are original menu words).
DVD_GROUP='KWCE DVD: disc channel DVD player'
# The console's older Priiloader read the 66-word CP932 lines; the DVD code cave (105 words)
# is split so no hash/patch line is longer than that proven size.
DVD_MAX_WORDS=64

def _split(runs,limit):
    out=[]
    for a,b in runs:
        while b-a>4*limit:out.append((a,a+4*limit));a+=4*limit
        out.append((a,b))
    return out

# GameCube-only disc channel: the original two-disc layout (kwce.gc_disc_layout). Data
# strings only, independent of the GC code patch and of the DVD hook; use it with the DVD
# entry turned OFF (with DVD on, the DVD panes of the original layout stay hidden).
GC_LAYOUT_GROUP='KWCE GC: GC-only disc layout (DVD off)'

def _legacy_safe(data,start,end):
    """True when every word in [start,end) keeps all 4 bytes through the old token parser."""
    return all(data[i]!=0 for i in range(start,end,4))

def _byte_unique_hash(menu,start,limit):
    """Shortest legacy-safe original word run at `start` (>=2 words) found ONCE at byte level.

    Old Priiloader searches the hash bytes at any alignment, so uniqueness is checked on
    bytes, not only on word positions. Bounded by `limit` words; raises instead of looping.
    """
    for length in range(2,limit+1):
        if not _legacy_safe(menu,start,start+4*length):return None
        pattern=menu[start:start+4*length]
        if menu.find(pattern)==start and menu.find(pattern,start+1)==-1:return _words(menu,start,start+4*length)
    return None

def gc_layout_entry(menu,*,ordered=False):
    """One Priiloader section for kwce.gc_disc_layout; every hash/patch word starts nonzero."""
    from .gc_disc_layout import patch_gc_only_layout,PAIR_RANGES,file_offset
    if hashlib.sha1(menu).hexdigest()!=MENU_SHA1:raise ValueError('Only the original 43K menu DOL')
    patched,_=patch_gc_only_layout(menu)
    pairs=[]
    ranges=sorted(PAIR_RANGES,key=lambda pair:file_offset(menu,pair[0],pair[1]-pair[0])) if ordered else PAIR_RANGES
    for a,b in ranges:
        fa=file_offset(menu,a,b-a);fb=fa+b-a
        if (b-a)%4 or (b-a)//4>DVD_MAX_WORDS:raise ValueError('GC layout pair size')
        if not _legacy_safe(patched,fa,fb):raise ValueError('GC layout patch word starts with zero at '+hex(a))
        h=_byte_unique_hash(menu,fa,16)
        if h is None:raise ValueError('No legacy-safe unique hash at '+hex(a))
        pairs.append((h,_words(patched,fa,fb)))
    entry=dict(name=GC_LAYOUT_GROUP,pairs=pairs)
    if apply(menu,[entry])!=patched:raise ValueError('GC layout hack simulation differs')
    return entry

def hacks(menu,dvd=False,dvd_banner=False):
    if hashlib.sha1(menu).hexdigest()!=MENU_SHA1:raise ValueError('Only the original 43K menu DOL')
    previous=menu;entries=[]
    steps=[(name,patch_gc_native(menu,japanese_cards=cards,japanese_comments=comments)[0])for name,cards,comments in GROUPS]
    if dvd_banner:
        if not dvd:raise ValueError('DVD banner needs DVD launch hook')
        if dvd_banner is True or dvd_banner==10:
            from .dvd_disc_banner_hook_v10 import patch_dvd_banner_hook
        elif dvd_banner==11:
            from .dvd_disc_banner_hook_v11 import patch_dvd_banner_hook
        elif dvd_banner==12:
            from .dvd_disc_banner_hook_v12 import patch_dvd_banner_hook
        elif dvd_banner==13:
            from .dvd_hide_tile_v1 import patch as patch_dvd_banner_hook
        elif dvd_banner==14:
            from .dvd_hide_tile_v2 import patch as patch_dvd_banner_hook
        else:raise ValueError('Unreviewed DVD banner hook revision')
        steps.append((DVD_GROUP,patch_dvd_banner_hook(steps[-1][1])[0]))
    elif dvd:steps.append((DVD_GROUP,patch_dvd_hook(steps[-1][1])[0]))
    for name,patched in steps:
        runs=_runs(previous,patched)
        if name==DVD_GROUP:runs=_split(runs,DVD_MAX_WORDS)
        pairs=[(_unique_hash(menu,a,(b-a)//4),_words(patched,a,b))for a,b in runs]
        entries.append(dict(name=name,pairs=pairs));previous=patched
    return entries

def ini(entries):
    out=[]
    for entry in entries:
        out+= [f"[{entry['name']}]",f'maxversion={VERSION}',f'minversion={VERSION}',f"amount={len(entry['pairs'])}"]
        for hash_words,patch_words in entry['pairs']:
            out.append('hash='+','.join(f'0x{w:08x}'for w in hash_words))
            out.append('patch='+','.join(f'0x{w:08x}'for w in patch_words))
    return '\n'.join(out)+'\n'

def apply(menu,entries):
    """Simulate Priiloader: each hash's first match gets its patch words."""
    data=bytearray(menu)
    for entry in entries:
        for hash_words,patch_words in entry['pairs']:
            pattern=struct.pack(f'>{len(hash_words)}I',*hash_words);at=bytes(data).find(pattern)
            while at!=-1 and at%4:at=bytes(data).find(pattern,at+1)
            if at==-1:raise ValueError(f"{entry['name']}: hash not found")
            struct.pack_into(f'>{len(patch_words)}I',data,at,*patch_words)
    return bytes(data)

LEGACY_KEYS=('maxversion','minversion','amount','hash','patch')

def legacy_sections(text):
    """Keep only sections the console's older Priiloader parser accepts.

    That parser stops at the first unknown layout ("expected 'version'"), so
    sections using newer keys (master/require/offset, minversion first,
    commented keys) are dropped instead of hiding every hack.
    """
    lines=text.replace('\r\n','\n').split('\n');sections=[];current=None
    for line in lines:
        if line.startswith('['):current=[line];sections.append(current)
        elif current is not None and line.strip():current.append(line)
    kept=[];dropped=[]
    for section in sections:
        keys=[l.split('=',1)[0]for l in section[1:]]
        ok=keys[:3]==['maxversion','minversion','amount']and set(keys)<=set(LEGACY_KEYS)and all('='in l for l in section[1:])
        if ok:
            pairs=keys[3:]
            ok=len(pairs)%2==0 and all(pairs[i]=='hash'and pairs[i+1]=='patch'for i in range(0,len(pairs),2))and int(section[3].split('=')[1])==len(pairs)//2
        (kept if ok else dropped).append(section)
    return '\n'.join(l for sec in kept for l in sec)+'\n',[sec[0]for sec in dropped]

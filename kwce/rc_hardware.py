"""Release-candidate unified installer packaging boundary.

One SD package carries every KWCE channel WAD, the unified installer app, and two
Priiloader hack profiles for the disc channel: GameCube-only (the original
two-disc layout, no DVD) and GameCube+DVD (the three-disc layout with the DVD
launch hook). The installer app writes channel titles through ES only; it links
no System Menu / NAND file writer, which forbidden_symbols() enforces on the
compiled ELF. Nothing here runs on, or sends anything to, a console.
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = 'apps/kwce-installer-rc'
DATA = 'kwce-rc'
README = 'KWCE-RC-README-ko.txt'
MANIFEST = 'KWCE-RC-package-manifest.json'
EDITIONS = f'{DATA}/editions.txt'
EDITION_KEY = re.compile(r'[a-z0-9-]{1,23}')
ACCOUNT_LINKER_FILES = {f'apps/wiilink-account-linker/{n}' for n in
                        ('boot.dol', 'meta.xml', 'icon.png', 'LICENSE', 'SOURCE.txt', 'source.zip')} | {
                        'KWCE-ACCOUNT-LINKER-README-ko.txt', 'KWCE-ACCOUNT-LINKER-manifest.json'}
CONFIG = ROOT / 'configs/rc-package.json'
# The app must install titles (ES_*) but never write System Menu files or NAND nodes.
FORBIDDEN = ('menu_available', 'menu_install', 'menu_restore', 'menu_state',
             'ISFS_Write', 'ISFS_Delete', 'ISFS_CreateFile', 'ISFS_Rename', 'ISFS_CreateDir')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def config():
    return json.loads(CONFIG.read_text(encoding='utf-8'))


def forbidden_symbols(nm_output):
    """Raise if the compiled installer links a System Menu / NAND writer symbol."""
    present = sorted({s for s in FORBIDDEN if re.search(r'\b' + re.escape(s) + r'\b', nm_output)})
    if present:
        raise ValueError('RC installer links a forbidden writer: ' + ', '.join(present))
    return True


def disc_ini_v2(menu, *, dvd, dvd_hook, strict_search_order=True, packed_tokens=True):
    """RC30+: rc_disc_v2 GC sections (+ frozen forwarder DVD section). Same record shape."""
    from .priiloader_hacks import gc_layout_entry, DVD_GROUP, GC_LAYOUT_GROUP
    from .priiloader_legacy import checked_ini, apply_streaming, apply, parse
    from . import rc_disc_v2
    entries = rc_disc_v2.gc_entries(menu)
    entries += [rc_disc_v2.dvd_entry(dvd_hook)] if dvd else [gc_layout_entry(menu, ordered=strict_search_order)]
    raw = checked_ini(menu, entries, packed=packed_tokens)
    rows = parse(raw)
    streamed = apply_streaming(menu, rows)
    if strict_search_order and streamed != apply(menu, rows):
        raise ValueError('Priiloader forward-search patch differs')
    kwce_only = [r for r in rows if r['name'] != GC_LAYOUT_GROUP]
    if apply_streaming(menu, kwce_only) != rc_disc_v2.final_image(menu, dvd_hook if dvd else None):
        raise ValueError('Disc profile result differs from the reviewed menu')
    names = [e['name'] for e in entries]
    record = dict(mode='gc-dvd' if dvd else 'gc-only', sections=names,
                  gc_only_layout=(GC_LAYOUT_GROUP in names), dvd_hook=(DVD_GROUP in names),
                  gc_card_menu=rc_disc_v2.GC_CARD_MENU, dvd_hook_revision=dvd_hook if dvd else None,
                  bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    return raw, record


def disc_ini(menu, *, dvd, hide_dvd_tile=False,native_dvd=None,strict_search_order=False,packed_tokens=False):
    """Return (ini bytes, record) for a disc-channel Priiloader profile.

    dvd=False -> GameCube-only: the original two-disc layout (kwce.gc_disc_layout)
                 plus the GC save-menu hacks; no DVD launch hook.
    dvd=True  -> GameCube+DVD: the three-disc layout with the DVD launch hook,
                 i.e. the existing kwce.priiloader_hacks DVD banner hook.
    Both are validated through the old Priiloader byte-token parser.
    """
    from .priiloader_hacks import hacks, gc_layout_entry, DVD_GROUP, GC_LAYOUT_GROUP
    from .priiloader_legacy import checked_ini
    if dvd:
        if native_dvd:
            from .dvd_native_hardware import entry
            entries=hacks(menu)+[entry(menu,native_dvd)]
        else:
            entries = hacks(menu, dvd=True, dvd_banner=14 if hide_dvd_tile == 2 else 13 if hide_dvd_tile else 12)
    else:
        entries = hacks(menu) + [gc_layout_entry(menu,ordered=strict_search_order)]
    raw = checked_ini(menu, entries,packed=packed_tokens)
    if strict_search_order:
        from .priiloader_legacy import apply_streaming,parse,apply
        if apply_streaming(menu,parse(raw))!=apply(menu,parse(raw)):
            raise ValueError('Priiloader forward-search patch differs')
    names = [e['name'] for e in entries]
    record = dict(mode='gc-dvd' if dvd else 'gc-only', sections=names,
                  gc_only_layout=(GC_LAYOUT_GROUP in names), dvd_hook=(DVD_GROUP in names),
                  bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    return raw, record


KWCE_DISC_PREFIXES = ('KWCE GC:', 'KWCE DVD:')
FRAGMENT = 'fragment-{}.ini'   # RC3+: KWCE-only disc sections; complete files are made per card


def merge_disc_profile(current, fragment):
    """Return a COMPLETE Priiloader file for one disc-channel mode.

    current  -- the card's own apps/Priiloader/hacks_hash.ini (may be empty)
    fragment -- KWCE-only disc sections from disc_ini() (gc-only or gc-dvd)
    Every non-KWCE section keeps its bytes and order; every existing 'KWCE GC:' /
    'KWCE DVD:' section is removed and the fragment is appended. The result must
    parse with the console's old Priiloader grammar (CRLF), so a mode switch can
    never hide the user's other hacks.
    """
    from .priiloader_hacks import legacy_sections
    from .priiloader_legacy import parse
    text = current.decode('latin1').replace('\r\n', '\n')
    if text.strip():
        _, dropped = legacy_sections(text)
        if dropped:
            raise ValueError('Existing Priiloader file has sections the console parser rejects; left unchanged')
    new = fragment.decode('ascii').replace('\r\n', '\n')
    names = re.findall(r'^\[([^\]\n]+)\]', new, re.M)
    if not names or any(not n.startswith(KWCE_DISC_PREFIXES) for n in names):
        raise ValueError('A disc fragment may contain only KWCE disc sections')
    text = re.sub(r'^\[KWCE (?:GC|DVD):[^\]\n]*\]\n.*?(?=^\[|\Z)', '', text, flags=re.M | re.S)
    prefix = text.rstrip('\n')
    merged = ((prefix + '\n' if prefix else '') + new.rstrip('\n') + '\n').replace('\n', '\r\n').encode('latin1')
    parse(merged)
    return merged


def restore_region(wad, target):
    """Return (wad, record): a restore WAD the Korean System Menu will launch.

    A WiiLink original keeps every content byte, title id, IOS and ticket; only the
    TMD region (+ the fakesign field) changes, and only when the region is not
    3 (any) or 4 (Korea): __OSCheckTmdCountryCode refuses other regions on a Korean
    console. target None keeps the RC1/RC2 behaviour (no change).
    """
    from .channels import load_library
    lib = load_library()
    title = lib.title.Title()
    title.load_wad(wad)
    region = title.tmd.region
    if target is None or region in (3, 4):
        return wad, dict(source_region=region, target_region=region, changed=False)
    if target not in (3, 4):
        raise ValueError('restore region must be 3 or 4')
    payloads = [title.get_content_by_index(i) for i in range(len(title.tmd.content_records))]
    before = title.tmd.dump()
    title.tmd.region = target
    title.fakesign()
    out = title.dump_wad()
    check = lib.title.Title()
    check.load_wad(out)
    if not check.get_is_fakesigned() or check.tmd.region != target:
        raise ValueError('restore WAD region/fakesign check failed')
    if any(check.get_content_by_index(i) != p for i, p in enumerate(payloads)):
        raise ValueError('restore WAD region change altered a content')
    after = check.tmd.dump()
    editable = set(range(4, 260)) | {0x19c, 0x19d, 0x1e2, 0x1e3}
    if len(before) != len(after) or any(a != b and i not in editable for i, (a, b) in enumerate(zip(before, after))):
        raise ValueError('Unexpected TMD modification')
    return out, dict(source_region=region, target_region=target, changed=True)


def allowed(path):
    if path in {'kwce/dvd/boot.ash','kwce/dvd/menu.arc','kwce/dvd/icon.arc','kwce/dvd/home.arc','kwce/dvd/wbf1.brfna',
                'kwce/dvd/player.dol'}:
        return True
    # RC30+: the pinned official Account Linker (kwce.account_linker_package), unmodified.
    if path in ACCOUNT_LINKER_FILES:
        return True
    if path in {f'{APP}/{n}' for n in ('boot.dol', 'meta.xml', 'icon.png')}:
        return True
    if path in {f'{DATA}/packages.txt', f'{DATA}/versions.txt', README, f'{DATA}/priiloader/gc-only.ini',
                f'{DATA}/priiloader/gc-dvd.ini',
                f'{DATA}/priiloader/fragment-gc-only.ini', f'{DATA}/priiloader/fragment-gc-dvd.ini'}:
        return True
    if re.fullmatch(r'kwce-rc/[a-z0-9-]+/(korean|original)\.wad', path):
        return True
    # RC9+: optional editions of a channel (sd:/kwce-rc/editions.txt), e.g. food/korean-dominos-us.wad
    if path == EDITIONS or re.fullmatch(r'kwce-rc/[a-z0-9-]+/korean-[a-z0-9-]+\.wad', path):
        return True
    if re.fullmatch(r'kwce-rc/extras/wiilink-mail-patcher/(boot\.dol|meta\.xml|icon\.png|LICENSE|SOURCE\.txt|source\.zip)', path):
        return True
    return False


def edition_list(entries):
    """sd:/kwce-rc/editions.txt from [(channel id, edition key, label)]. The installer reads it to offer
    each channel's editions (kwce-rc/<channel>/korean-<key>.wad) next to its standard Korean build."""
    lines = ['# channel|edition|label (generated by scripts/export_rc_hardware.py; do not edit)']
    for cid, key, label in entries:
        if not EDITION_KEY.fullmatch(key) or not re.fullmatch(r'[a-z0-9-]+', cid):
            raise ValueError('edition key / channel id must be [a-z0-9-]')
        if '|' in label or not label.isascii() or not 0 < len(label) < 40:
            raise ValueError('edition label must be ASCII, without |, at most 39 characters')
        lines.append(f'{cid}|{key}|{label}')
    if len(entries) > 16:
        raise ValueError('more editions than the installer holds (MAX_ED 16)')
    return ('\n'.join(lines) + '\n').encode('ascii')


def sd_files(package):
    """Verify the complete immutable SD payload against its signed manifest."""
    package = Path(package).resolve()
    raw = (package / 'package-manifest.json').read_bytes()
    if sha(raw) != (package / 'package-manifest.sha256').read_text(encoding='ascii').strip():
        raise ValueError('RC manifest digest differs')
    record = json.loads(raw)
    if record.get('kind') != 'kwce-rc-unified-v1' or record.get('menu_writer_linked') or record.get('nand_writes'):
        raise ValueError('RC package scope differs')
    seen, result = set(), []
    for item in record['sd_files']:
        name = item['path']
        p = package / name
        if name in seen or not allowed(name) or not p.resolve().is_relative_to(package) or p.is_symlink() or p.is_junction():
            raise ValueError('Unexpected RC package path: ' + name)
        if p.stat().st_size != item['bytes'] or sha(p.read_bytes()) != item['sha256']:
            raise ValueError('RC payload differs: ' + name)
        seen.add(name)
        result.append((p, name))
    if f'{APP}/boot.dol' not in seen or f'{DATA}/packages.txt' not in seen:
        raise ValueError('RC package missing the installer or channel list')
    result.append((package / 'package-manifest.json', MANIFEST))
    return record, result



# ---- RC4+: build identity and the version list (sd:/kwce-rc/versions.txt) ----------
# The installer (homebrew/kwce-installer-rc/source/versions.c) computes the same identity
# from the console's stored TMD; both sides must stay byte-for-byte in step.

VERSIONS = f'{DATA}/versions.txt'
VERSIONS_SCHEMA = 1
FNV_OFFSET, FNV_PRIME, MASK64 = 0xcbf29ce484222325, 0x100000001b3, (1 << 64) - 1
VERSION_LIMITS = dict(builds=2048, marks=8192)   # MAX_BUILDS / MAX_MARKS in versions.c


def fnv1a64(data, h=FNV_OFFSET):
    for b in data:
        h = ((h ^ b) * FNV_PRIME) & MASK64
    return h


def wad_tmd(head):
    """The TMD bytes of a WAD, from (at least) its first bytes; None if not a WAD or too short."""
    if len(head) < 32:
        return None
    hdr, _type, certs, crl, tik, tmd_len = (int.from_bytes(head[i:i + 4], 'big') for i in range(0, 24, 4))
    if hdr != 0x20 or not 0x1E4 <= tmd_len <= 0x10000:
        return None
    a64 = lambda x: (x + 63) & ~63
    off = a64(hdr) + a64(certs) + a64(crl) + a64(tik)
    tmd = head[off:off + tmd_len]
    return tmd if len(tmd) == tmd_len else None


def read_wad_tmd(path):
    with open(path, 'rb') as f:
        head = f.read(0x10000)
        tmd = wad_tmd(head)
        if tmd is None and len(head) == 0x10000:
            f.seek(0)
            tmd = wad_tmd(f.read(0x40000))
    return tmd


def tmd_records(tmd):
    count = int.from_bytes(tmd[0x1DE:0x1E0], 'big')
    if len(tmd) < 0x1E4 + 36 * count:
        raise ValueError('truncated TMD')
    return [bytes(tmd[0x1E4 + 36 * i:0x1E4 + 36 * (i + 1)]) for i in range(count)]


def tmd_identity(tmd):
    """Return (fingerprint, title id hex, title version, region) exactly as versions.c computes it."""
    records = tmd_records(tmd)
    h = fnv1a64(tmd[0x184:0x194])
    h = fnv1a64(tmd[0x19C:0x19E], h)
    h = fnv1a64(tmd[0x1D8:0x1E2], h)
    h = fnv1a64(b''.join(records), h)
    return (h or 1, tmd[0x18C:0x194].hex(), int.from_bytes(tmd[0x1DC:0x1DE], 'big'),
            int.from_bytes(tmd[0x19C:0x19E], 'big'))


# The final personal release follows RC31; keep in step with FINAL_1_0 in the installer.
FINAL_RELEASES = {'1.0': 32, '1.0.1': 33, '1.0.2': 34, '1.0.3': 35, '1.0.4': 36, '1.0.5': 37, '1.0.6': 38, '1.0.7': 39, '1.0.8': 40, '1.0.9': 41}


def release_of(version):
    m = re.search(r'-rc(\d+)$', version or '')
    return int(m.group(1)) if m else FINAL_RELEASES.get(version or '', 0)


def release_name(version):
    """Label shown to the user: 'RC12' for candidates, the version itself for a final release."""
    return version if version in FINAL_RELEASES else f'RC{release_of(version)}'


def version_sources(root, channels, package_name):
    """Every WAD the version list should know, as sorted project-relative paths.

    Older RC packages (kwce-rc-sd-vK with K below this one), every other hardware package
    under workspace/hardware (test deliveries before the RC), each channel's hardware-v*
    candidates and its originals/ folder. Only titles listed in the package are kept later.
    """
    root = Path(root)
    this = int(package_name.rsplit('-v', 1)[1])
    hw = root / 'workspace/hardware'
    paths = []
    for pkg in sorted(p for p in hw.iterdir() if p.is_dir()):
        m = re.fullmatch(r'kwce-rc-sd-v(\d+)', pkg.name)
        if pkg.name == package_name or (m and int(m.group(1)) >= this):
            continue
        if m and not (pkg / 'package-manifest.json').is_file():
            continue  # An interrupted build is not a released version source.
        paths += [p for p in pkg.rglob('*.wad') if p.is_file()]
    for ch in channels:
        base = root / 'workspace/channels' / ch['id']
        paths += [p for p in base.glob('hardware-v*/*.wad') if p.is_file()]
        paths += [p for p in base.glob('originals/*.wad') if p.is_file()]
    return sorted({p.relative_to(root).as_posix() for p in paths})


def _source_rank(root, rel):
    """(rank, label, forced kind) for one source path."""
    parts = rel.split('/')
    if parts[:2] == ['workspace', 'hardware']:
        pkg = parts[2]
        if re.fullmatch(r'kwce-rc-sd-v\d+', pkg):
            mani = json.loads((Path(root) / 'workspace/hardware' / pkg / 'package-manifest.json').read_text(encoding='utf-8'))
            n = release_of(mani.get('version'))
            ed = re.fullmatch(r'korean-([a-z0-9-]+)\.wad', parts[-1])
            if ed:   # RC9+ edition WAD: "RCn <key>" lets a later installer keep the same edition
                return n, f'RC{n} {ed.group(1)}'[:23], None
            return n, f'RC{n}', 'O' if parts[-1] == 'original.wad' else None
        return 0, pkg[:23], None
    if parts[:2] == ['workspace', 'channels'] and len(parts) >= 5:
        if parts[3] == 'originals':
            return 0, 'original', 'O'
        return 0, f'{parts[2]} {parts[3]}'[:23], None
    return 0, parts[-1][:23], None


def version_list(root, channels, release, version, sources):
    """Return (versions.txt bytes, record) for this package.

    channels -- the package's channel entries (id, tid); sources -- version_sources() paths.
    A WAD is an original ('O') when its content records equal those of a channel original
    (region and title version may differ); otherwise it is a KWCE build ('K'). rank is the RC
    release that first shipped the build, 0 for earlier test packages. 'mark' lines carry the
    first 8 bytes of content SHA-1s found only in KWCE builds of that channel, which lets the
    installer recognise a KWCE build this list does not name.
    """
    root = Path(root)
    by_tid = {c['tid'].lower(): c['id'] for c in channels}
    order = {c['id']: i for i, c in enumerate(channels)}
    seen = []
    for rel in sources:
        tmd = read_wad_tmd(root / rel)
        if tmd is None:
            continue
        fp, tid, ver, region = tmd_identity(tmd)
        if tid not in by_tid:
            continue
        rank, label, kind = _source_rank(root, rel)
        seen.append(dict(id=by_tid[tid], fp=fp, records=tuple(tmd_records(tmd)), rank=rank, label=label, kind=kind))
    original_sets = {(s['id'], s['records']) for s in seen if s['kind'] == 'O'}
    builds = {}
    for s in seen:
        kind = 'O' if s['kind'] == 'O' or (s['id'], s['records']) in original_sets else 'K'
        key = (s['id'], s['fp'])
        cur = builds.get(key)
        better = cur is None or (s['rank'] > 0 and (cur['rank'] == 0 or s['rank'] < cur['rank']))
        if better:
            builds[key] = dict(id=s['id'], fp=s['fp'], kind=kind, rank=s['rank'],
                               label='original' if kind == 'O' else s['label'])
    original_sha = {(s['id'], r[16:36]) for s in seen if (s['id'], s['records']) in original_sets for r in s['records']}
    marks = sorted({(s['id'], r[16:24].hex()) for s in seen if (s['id'], s['records']) not in original_sets
                    for r in s['records'] if (s['id'], r[16:36]) not in original_sha},
                   key=lambda m: (order[m[0]], m[1]))
    rows = sorted(builds.values(), key=lambda b: (order[b['id']], b['rank'], b['label'], b['fp']))
    if len(rows) > VERSION_LIMITS['builds'] or len(marks) > VERSION_LIMITS['marks']:
        raise ValueError('version list exceeds the installer limits')
    if any('|' in b['label'] or not b['label'].isascii() for b in rows):
        raise ValueError('version label must be ASCII without |')
    lines = [f'kwce-versions|{VERSIONS_SCHEMA}|{release}|{version}',
             '# generated by scripts/export_rc_hardware.py; build|channel|fingerprint|K=Korean O=original|release|label']
    lines += [f"build|{b['id']}|{b['fp']:016x}|{b['kind']}|{b['rank']}|{b['label']}" for b in rows]
    lines += [f'mark|{cid}|{prefix}' for cid, prefix in marks]
    raw = ('\n'.join(lines) + '\n').encode('ascii')
    record = dict(path=VERSIONS, release=release, builds=len(rows), marks=len(marks),
                  korean=sum(b['kind'] == 'K' for b in rows), originals=sum(b['kind'] == 'O' for b in rows),
                  sources=list(sources), sha256=sha(raw))
    return raw, record

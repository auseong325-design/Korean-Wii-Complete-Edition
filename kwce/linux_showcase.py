"""Showcase recording profiles: an online profile prepared for the distribution video.

User instruction 2026-11-17: record a showcase video in Dolphin, driven by the agent.
  * channel line-up: Korean system channels and official Korean channels only (KOR 'K' titles,
    e.g. data restoration HCRK, Mario Kart channel RMCK) plus the Homebrew Channel; everything else
    (Virtual Console, other homebrew channels, earlier Korean channel installs) removed from the copy
  * the disc channel in its normal (Korean) state; the KWCE installer is run from the Homebrew Channel
    on camera, from a virtual SD made of the 1.0.8 package only (never the project's sd/ tree;
    only the pristine Priiloader hacks file is read from it)
  * every Mii name -> symbols/digits, creator names cleared, console nickname -> "Wii"
    (the food channel's fictional address stays as it is)
  * recording at the console's own output: internal resolution 1x, XFB aspect-corrected frame dump
    (854x480 for 16:9), lossless FFV1 + DSP/DTK audio dumps

What differs from kwce.linux_online: the pinned showcase Dolphin (configs/dolphin-linux-showcase.lock.json,
frame dumps + fakesigned ES blobs) and a profile-local SD sync folder. Everything else (bubblewrap,
capabilities zero, home/project/SD hidden, Korean locale checks, one Dolphin at a time) is reused as is.
Nothing here prints identifiers; diagnostics go to workspace/private/showcase.
"""
import binascii
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time

from . import linux_online as online
from .linux_runtime import LOCK, ROOT, digest, direct, stopped

SHOW_LOCK = ROOT / 'configs/dolphin-linux-showcase.lock.json'
PRIVATE = ROOT / 'workspace/private/showcase'
SYMBOLS = '#@&+=$%!?*'
PIPE_GCPAD = ('[GCPad1]\nDevice = Pipe/0/kwce-pad\n'
              'Buttons/A = `Button A`\nButtons/B = `Button B`\nButtons/X = `Button X`\nButtons/Y = `Button Y`\n'
              'Buttons/Z = `Button Z`\nButtons/Start = `Button START`\nTriggers/L = `Button L`\nTriggers/R = `Button R`\n'
              'D-Pad/Up = `Button D_UP`\nD-Pad/Down = `Button D_DOWN`\nD-Pad/Left = `Button D_LEFT`\nD-Pad/Right = `Button D_RIGHT`\n'
              'Main Stick/Up = `Axis MAIN Y +`\nMain Stick/Down = `Axis MAIN Y -`\nMain Stick/Left = `Axis MAIN X -`\nMain Stick/Right = `Axis MAIN X +`\n'
              '[GCPad2]\nDevice = \n[GCPad3]\nDevice = \n[GCPad4]\nDevice = \n')


def executable():
    lock = json.loads(SHOW_LOCK.read_text())
    exe = direct(ROOT / lock['executable'], ROOT / 'tools/linux')
    if digest(exe) != lock['executable_sha256']:
        raise ValueError('Pinned showcase Dolphin hash mismatch')
    return exe, ROOT / lock['prefix']


def save(dest, meta):
    (dest / 'profile.json').write_text(json.dumps(meta, indent=2))


def prepare(alias='showcase'):
    executable()
    name = online.prepare(alias, wiilink=True)
    dest, meta = online.load(name)
    meta['showcase'] = dict(lock='configs/dolphin-linux-showcase.lock.json', steps=[])
    save(dest, meta)
    return name


def step(dest, meta, record):
    meta['showcase']['steps'].append(record); save(dest, meta)


def strip_titles(name):
    """Keep system, 00010002/00010008, official Korean ('K') titles and the Homebrew Channel."""
    stopped()
    dest, meta = online.load(name)
    title = dest / 'user/Wii/title'
    remove = []
    for hi in ('00010001', '00010004'):
        for t in sorted((title / hi).glob('*')) if (title / hi).is_dir() else []:
            if (t / 'content').is_dir() and not t.name.endswith('4b') and t.name != '4c554c5a':
                remove.append(hi + t.name)
    if remove:
        online.uninstall(name, remove)
    dest, meta = online.load(name)
    kept = sorted(hi + t.name for hi in ('00010001', '00010004') if (title / hi).is_dir()
                  for t in (title / hi).glob('*') if (t / 'content').is_dir())
    step(dest, meta, dict(action='strip_titles', removed=remove, kept_user_titles=kept))
    print(f'PASS showcase {name}: removed {len(remove)} title(s), kept {len(kept)} channel/game title(s)')


def _sysconf_set_nickname(path, text):
    d = bytearray(path.read_bytes())
    n = struct.unpack_from('>H', d, 4)[0]
    for i in range(n):
        off = struct.unpack_from('>H', d, 6 + 2 * i)[0]; h = d[off]; ln = (h & 0x1f) + 1
        if d[off + 1:off + 1 + ln] == b'IPL.NIK':
            if h >> 5 != 2 or d[off + 1 + ln] + 1 != 22:
                raise ValueError('Unexpected nickname entry')
            at = off + 2 + ln
            old = bytes(d[at:at + 20])
            d[at:at + 22] = text.encode('utf-16-be').ljust(20, b'\0') + struct.pack('>H', len(text))
            path.write_bytes(bytes(d))
            return old
    raise ValueError('Nickname entry missing')


def anonymize(name):
    """Mii names -> symbol+digits, creator names cleared, console nickname -> 'Wii'.
    Then scan the whole NAND copy for any remaining copy of the old strings (paths/counts only)."""
    stopped()
    dest, meta = online.load(name)
    wii = dest / 'user/Wii'
    db_path = wii / 'shared2/menu/FaceLib/RFL_DB.dat'
    db = bytearray(db_path.read_bytes())
    if db[:4] != b'RNOD' or binascii.crc_hqx(bytes(db[:127454]), 0) != int.from_bytes(db[127454:127456], 'big'):
        raise ValueError('Mii database missing or CRC invalid')
    olds, count = set(), 0
    for i in range(100):
        at = 4 + 74 * i; rec = db[at:at + 74]
        if not any(rec):
            continue
        for off in (0x02, 0x36):
            s = bytes(rec[off:off + 20]).decode('utf-16-be', 'ignore').split('\0')[0]
            if len(s) >= 2:
                olds.add(s)
        new = f'{SYMBOLS[count % len(SYMBOLS)]}{count + 1:02d}'
        db[at + 0x02:at + 0x16] = new.encode('utf-16-be').ljust(20, b'\0')
        db[at + 0x36:at + 0x4a] = bytes(20)
        count += 1
    db[127454:127456] = binascii.crc_hqx(bytes(db[:127454]), 0).to_bytes(2, 'big')
    # 0x40-byte records after the CRC (outside it) carry a name at +2; rename text-like ones only
    for k in range(5):
        at = 0x1F1E0 + k * 0x40
        s = bytes(db[at + 2:at + 0x16]).decode('utf-16-be', 'ignore').split('\0')[0]
        if s and all(0xAC00 <= ord(c) <= 0xD7A3 or 0x20 <= ord(c) < 0x7f or 0x3040 <= ord(c) <= 0x30ff for c in s):
            olds.add(s)
            db[at + 2:at + 0x16] = f'%{k + 31:02d}'.encode('utf-16-be').ljust(20, b'\0')
    db_path.write_bytes(bytes(db))
    sysconf = wii / 'shared2/sys/SYSCONF'
    old_nick = _sysconf_set_nickname(sysconf, 'Wii').decode('utf-16-be', 'ignore').split('\0')[0]
    if len(old_nick) >= 2:
        olds.add(old_nick)
    meta['locale_hashes']['shared2/sys/SYSCONF'] = digest(sysconf)
    hits = residual(wii, olds)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    meta['locale_hashes']['shared2/sys/SYSCONF'] = digest(sysconf)
    step(dest, meta, dict(action='anonymize', miis=count, creator_names='cleared', nickname='Wii',
                          residual_files=sorted(hits)))
    print(f'PASS showcase {name}: {count} Mii names replaced, creators cleared, nickname replaced; '
          f'{len(hits)} other file(s) still hold an old name')
    return hits


def clear_birthdays(name):
    """Mii birthdays may be real people's: clear month/day (bits 10-13 / 5-9 of the first word) of
    every Mii in RFL_DB.dat and fix the CRC. Counts only are printed."""
    stopped()
    dest, meta = online.load(name)
    path = dest / 'user/Wii/shared2/menu/FaceLib/RFL_DB.dat'
    db = bytearray(path.read_bytes())
    if db[:4] != b'RNOD' or binascii.crc_hqx(bytes(db[:127454]), 0) != int.from_bytes(db[127454:127456], 'big'):
        raise ValueError('Mii database missing or CRC invalid')
    cleared = 0
    for i in range(100):
        at = 4 + 74 * i
        if not any(db[at:at + 74]):
            continue
        word = int.from_bytes(db[at:at + 2], 'big')
        if word & 0x3fe0:
            struct.pack_into('>H', db, at, word & ~0x3fe0)
            cleared += 1
    db[127454:127456] = binascii.crc_hqx(bytes(db[:127454]), 0).to_bytes(2, 'big')
    path.write_bytes(bytes(db))
    step(dest, meta, dict(action='clear_mii_birthdays', cleared=cleared))
    print(f'PASS showcase {name}: birthdays cleared on {cleared} Mii(s)')


def residual(wii, olds):
    """Relative NAND paths that still contain any of the strings (UTF-16BE or UTF-8)."""
    needles = [s.encode('utf-16-be') for s in olds] + [s.encode('utf-8') for s in olds if len(s.encode('utf-8')) >= 4]
    hits = {}
    for p in wii.rglob('*'):
        if p.is_file() and p.stat().st_size < 64 * 1024 * 1024 and '/content/' not in p.as_posix():
            data = p.read_bytes()
            n = sum(data.count(x) for x in needles)
            if n:
                hits[p.relative_to(wii).as_posix()] = n
    return hits


def make_sd(name, package):
    """Profile-local SD sync folder: the package files + pristine Priiloader file + generated disc profiles."""
    stopped()
    dest, meta = online.load(name)
    if not re.fullmatch(r'kwce-rc-sd-v[0-9]+', package):
        raise ValueError('Expected a kwce-rc-sd-vN package')
    src = direct(ROOT / 'workspace/hardware' / package, ROOT / 'workspace/hardware')
    sd = dest / 'user/Load/WiiSDSync'
    if sd.exists() and any(sd.iterdir()):
        raise ValueError('SD folder exists; make a new profile for a different SD')
    files = {}
    for p in sorted(src.rglob('*')):
        if p.is_file():
            rel = p.relative_to(src).as_posix(); out = sd / rel
            out.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, out); files[rel] = digest(out)
    # The card's own Priiloader file as read by the last deploy of this package, with the KWCE disc
    # sections removed: the console's other hacks, disc channel in its normal state. (The project's
    # sd/ copy predates fixes the console parser needs, so it is not used.)
    # this package's own deploy stage, else the card's file as read by the most recent deploy
    stages = sorted((ROOT / 'workspace/private').glob(f'rc-priiloader-{package}-*'), key=lambda p: int(p.name.rsplit('-', 1)[1]))
    if not stages:
        stages = sorted((ROOT / 'workspace/private').glob('rc-priiloader-kwce-rc-sd-v*-*'),
                        key=lambda p: (int(p.name.split('-v')[1].split('-')[0]), int(p.name.rsplit('-', 1)[1])))
    if not stages:
        raise ValueError('No deploy stage with the card Priiloader file')
    card = (stages[-1] / 'card-hacks_hash.ini').read_bytes().decode('latin1').replace('\r\n', '\n')
    card = re.sub(r'^\[KWCE (?:GC|DVD):[^\]\n]*\]\n.*?(?=^\[|\Z)', '', card, flags=re.M | re.S)
    base = (card.rstrip('\n') + '\n').replace('\n', '\r\n').encode('latin1')
    if b'[KWCE' in base:
        raise ValueError('KWCE sections left in the base Priiloader file')
    out = sd / 'apps/Priiloader/hacks_hash.ini'; out.parent.mkdir(parents=True, exist_ok=True); out.write_bytes(base)
    files['apps/Priiloader/hacks_hash.ini'] = digest(out)
    from .rc_hardware import merge_disc_profile, FRAGMENT
    for mode in ('gc-only', 'gc-dvd'):
        merged = merge_disc_profile(base, (src / 'kwce-rc/priiloader' / FRAGMENT.format(mode)).read_bytes())
        out = sd / f'kwce-rc/priiloader/{mode}.ini'; out.write_bytes(merged); files[f'kwce-rc/priiloader/{mode}.ini'] = digest(out)
    step(dest, meta, dict(action='make_sd', package=package, files=len(files), card_priiloader_stage=stages[-1].name,
                          sd_manifest_sha256=hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()))
    print(f'PASS showcase {name}: SD sync folder with {len(files)} files from {package}')


MENU_RESOURCE = dict(path='title/00000001/00000002/content/0000009d.app',
                     original_sha1='aafc40a74c232533afda04a64cef679ebfcfc78c',
                     console_sha1='2e882145d3150d39bbc467046d62fe0ce2745694',
                     source='workspace/hardware/kwce-alpha-v7/kwce/menu/kwce-0000009d.app')


def console_menu_resource(name):
    """The console runs the KWCE GC menu resource installed by alpha-v7 (2026-10-24: GC card icons,
    'Nintendo / GameCube' two-line label, disc banner); the imported NAND (2026-10-21) predates it.
    Copy only, never the console."""
    stopped()
    dest, meta = online.load(name)
    target = dest / 'user/Wii' / MENU_RESOURCE['path']
    sha1 = lambda b: hashlib.sha1(b).hexdigest()
    have = sha1(target.read_bytes())
    if have == MENU_RESOURCE['console_sha1']:
        print(f'KEEP showcase {name}: console menu resource already present'); return
    if have != MENU_RESOURCE['original_sha1']:
        raise ValueError('Unexpected menu resource in the copy')
    data = direct(ROOT / MENU_RESOURCE['source'], ROOT / 'workspace/hardware').read_bytes()
    if sha1(data) != MENU_RESOURCE['console_sha1']:
        raise ValueError('KWCE menu resource differs from its record')
    target.write_bytes(data)
    step(dest, meta, dict(action='menu_resource', **MENU_RESOURCE))
    print(f'PASS showcase {name}: console KWCE menu resource installed (copy only)')


def stage_disc(name):
    """The owner's GameCube test disc (catalogued GALJ01) inserted at boot via DefaultISO."""
    stopped()
    dest, meta = online.load(name)
    disc = direct(ROOT / 'workspace/sandbox/gc-v9/disc/GALJ01.iso', ROOT / 'workspace/sandbox')
    catalog = json.loads((ROOT / 'workspace/private/disc-catalog.json').read_text())
    expected = next(row['sha256'] for row in catalog['files'] if row['name'] == 'GALJ01.iso')
    out = dest / 'user/Disc/GALJ01.iso'; out.parent.mkdir(exist_ok=True)
    if digest(disc) != expected:
        raise ValueError('Staged test disc differs from the private catalog')
    shutil.copyfile(disc, out)
    if digest(out) != expected:
        raise ValueError('Disc copy verification failed')
    set_disc(name, True)
    dest, meta = online.load(name)
    step(dest, meta, dict(action='stage_disc', disc='GALJ01 (owner dump, catalogued)', sha256_prefix=expected[:16]))
    print(f'PASS showcase {name}: GameCube disc staged and inserted at boot')


def set_disc(name, inserted):
    stopped()
    dest, meta = online.load(name); ini = dest / 'user/Config/Dolphin.ini'
    c = configparser.ConfigParser(strict=False); c.optionxform = str; c.read(ini)
    if inserted:
        if not (dest / 'user/Disc/GALJ01.iso').is_file():
            raise ValueError('Stage the disc first')
        c['Core']['DefaultISO'] = '/profile/user/Disc/GALJ01.iso'
    else:
        c['Core'].pop('DefaultISO', None)
    with ini.open('w') as f:
        c.write(f, space_around_delimiters=True)
    print(f'PASS showcase {name}: disc {"inserted" if inserted else "removed"} at next boot')


def configure(name, record=True):
    """Pipe input for Wiimote 1 and GC pad 1, SD on (profile folder sync), frame/audio dumps at 1x."""
    stopped()
    online.use_pipe_input(name)
    dest, meta = online.load(name); user = dest / 'user'
    # GC pad 1 reads its own FIFO: software that polls both controllers (Priiloader, the installer)
    # would otherwise see every press twice
    if not (user / 'Pipes/kwce-pad').exists():
        os.mkfifo(user / 'Pipes/kwce-pad')
    (user / 'Config/GCPadNew.ini').write_text(PIPE_GCPAD)
    c = configparser.ConfigParser(strict=False); c.optionxform = str; c.read(user / 'Config/Dolphin.ini')
    for sec in ('Core', 'Movie', 'DSP', 'Interface'):
        if not c.has_section(sec):
            c.add_section(sec)
    c['Core'].update(WiiSDCard='True', WiiSDCardAllowWrites='True', WiiSDCardEnableFolderSync='True', SIDevice0='6',
                     GFXBackend='Vulkan')   # GPU (the OpenGL path fell back to llvmpipe in the sandbox: ~80% speed)
    c['Movie'].update(DumpFrames=str(record), DumpFramesSilent='True')
    c['DSP'].update(DumpAudio=str(record), DumpAudioSilent='True')
    c['Interface'].update(OnScreenDisplayMessages='False')
    with (user / 'Config/Dolphin.ini').open('w') as f:
        c.write(f, space_around_delimiters=True)
    g = configparser.ConfigParser(strict=False); g.optionxform = str; g.read(user / 'Config/GFX.ini')
    for sec in ('Hardware', 'Settings', 'Enhancements', 'Hacks'):
        if not g.has_section(sec):
            g.add_section(sec)
    g['Hardware'].update(VSync='False')
    g['Settings'].update(InternalResolution='1', DumpFormat='matroska', DumpCodec='ffv1', DumpEncoder='',
                         FrameDumpsResolutionType='1', AspectRatio='0', MSAA='1', SSAA='False',
                         wideScreenHack='False', Crop='False')
    # every VI field is presented and dumped, like the console's own output (static console-text
    # screens such as the installer are otherwise never dumped)
    g['Hacks'].update(SkipDuplicateXFBs='False')
    g['Enhancements'].update(MaxAnisotropy='0', ForceTextureFiltering='0', OutputResampling='0')
    with (user / 'Config/GFX.ini').open('w') as f:
        g.write(f, space_around_delimiters=True)
    step(dest, meta, dict(action='configure', record=record, input='pipes (Wiimote 1: kwce-gc, GC pad 1: kwce-pad)',
                          sd='profile folder sync', video='1x, XFB aspect-corrected, matroska/ffv1, duplicate XFBs kept, no OSD', audio='dsp+dtk wav'))
    print(f'PASS showcase {name}: pipe input, SD folder sync, recording {"on" if record else "off"}')


def validate(name):
    dest, meta = online.load(name)
    if 'showcase' not in meta:
        raise ValueError('Not a showcase profile')
    user = dest / 'user'
    for p in user.rglob('*'):
        if p.is_symlink():
            raise ValueError('Indirect runtime content refused')
    wii = user / 'Wii'
    for rel, value in meta['locale_hashes'].items():
        if rel.endswith('setting.txt') and digest(wii / rel) != value:
            raise ValueError('Console region file changed')
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    from launch_dolphin import korean_locale
    if not korean_locale(wii):
        raise ValueError('Korean language/country changed')
    c = configparser.ConfigParser(strict=False); c.read(user / 'Config/Dolphin.ini')
    if c.getboolean('Core', 'WiiSDCard', fallback=False) and not c.getboolean('Core', 'WiiSDCardEnableFolderSync', fallback=False):
        raise ValueError('Only the profile SD sync folder is allowed')
    for section in c.sections():
        for key, value in c[section].items():
            if value and ('path' in key or key in ('nandroot', 'defaultiso')) and not (key == 'isopaths' and value == '0'):
                if not value.startswith('/profile/user/') or '..' in Path(value).parts:
                    raise ValueError('Outside profile path refused')
    exe, prefix = executable()
    return dest, meta, exe, prefix


def command(dest, prefix, args):
    base_prefix = str(ROOT / json.loads(LOCK.read_text())['prefix'])
    cmd = online.online_sandbox(dest, '/opt/dolphin/bin/dolphin-emu', args)
    return [str(prefix) if part == base_prefix else part for part in cmd]


def launch(name, title=None, dol=None):
    """Boot a NAND title, or a DOL from the profile SD folder (the Homebrew Channel itself does not
    run in Dolphin: black screen, no frames)."""
    stopped()
    dest, meta, exe, prefix = validate(name)
    if dol is not None:
        if not re.fullmatch(r'apps/[A-Za-z0-9_.-]+/boot\.dol', dol):
            raise ValueError('Expected apps/<name>/boot.dol')
        direct(dest / 'user/Load/WiiSDSync' / dol, dest / 'user/Load/WiiSDSync').stat()
        target = ['--exec', '/profile/user/Load/WiiSDSync/' + dol]
    else:
        if not re.fullmatch(r'[0-9a-f]{16}', title or ''):
            raise ValueError('Expected a 16-digit title id')
        if not (dest / 'user/Wii/title' / title[:8] / title[8:] / 'content').is_dir():
            raise ValueError('Title is not installed in this profile')
        target = ['--nand_title', title]
    online.isolation_probe(dest)
    cmd = command(dest, prefix, ['--batch', '--user', '/profile/user', *target])
    PRIVATE.mkdir(parents=True, exist_ok=True)
    with (PRIVATE / f'{name}-startup.log').open('wb') as output:
        child = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)
    for _ in range(100):
        if child.poll() is not None:
            raise ValueError('Dolphin exited during startup; diagnostics kept private')
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                args = proc.joinpath('cmdline').read_bytes().split(b'\0')
                if not os.path.samefile(proc / 'exe', exe) or not os.path.samefile(proc / 'root/profile', dest) or b'/profile/user' not in args:
                    continue
                row = {'pid': int(proc.name), 'start': proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19],
                       'executable': str(exe), 'network': 'host'}
                (dest / 'process.json').write_text(json.dumps(row))
                print(f'PASS launched showcase {name}: render window, real network, recording per profile config')
                return
            except (OSError, ValueError):
                pass
        time.sleep(.1)
    child.terminate()
    raise ValueError('Unable to verify showcase Dolphin identity')

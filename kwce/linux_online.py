"""Online Linux Dolphin profiles: a copy of the owner's imported console NAND, real network.

AGENTS.md section 5 (2026-11-16): the owner allows Dolphin to reach the real WiiLink service with
the console's own NAND so that hardware round trips are needed less often. This module is separate
from kwce.linux_runtime on purpose: offline profiles keep their checks untouched, and an online
profile can never be mistaken for one.

What stays enforced here
  * the source NAND (workspace/dolphin/baseline-user) is only read; work happens on a numbered copy
  * profiles live in workspace/online/<alias>-vN, never in workspace/linux
  * bubblewrap still hides the home directory, the project and the SD copy and drops every
    capability; only the network namespace is shared with the host
  * one Dolphin at a time; the pinned Dolphin build only
  * nothing here prints identifiers; diagnostics go to workspace/private
"""
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

from .linux_runtime import LOCK, ROOT, digest, direct, gc_keyboard_config, sandbox, stopped

BASE = ROOT / 'workspace/online'
PRIVATE = ROOT / 'workspace/private/linux-online'
SOURCE = ROOT / 'workspace/dolphin/baseline-user'          # Dolphin import of the owner's NAND dump
OMIT = {'Logs', 'Cache', 'StateSaves', 'Dump', 'ScreenShots', 'Shaders', 'Config'}
MENU = '0000000100000002'
NETWORK_FILES = ('resolv.conf', 'hosts', 'nsswitch.conf', 'ssl', 'ca-certificates', 'host.conf', 'gai.conf')


def runtime(name):
    if not re.fullmatch(r'[a-z][a-z0-9-]*-v[1-9][0-9]*', name):
        raise ValueError('Expected a numbered online profile alias')
    return direct(BASE / name, BASE)


def nand_manifest(wii):
    """Path -> sha256 for the parts that identify the installed software (not saves or WC24 state)."""
    rows = {}
    for top in ('title', 'ticket', 'shared1', 'sys'):
        for path in sorted((wii / top).rglob('*')):
            rel = path.relative_to(wii).as_posix()
            if path.is_file() and '/data/' not in rel:
                rows[rel] = digest(path)
    return rows


def source_identity():
    wii = SOURCE / 'Wii'
    if not (wii / 'title').is_dir() or not (wii / 'keys.bin').is_file():
        raise ValueError('Imported console NAND missing')
    return hashlib.sha256(json.dumps(nand_manifest(wii), sort_keys=True).encode()).hexdigest()


def write_config(user, wiilink):
    cfg = user / 'Config'; cfg.mkdir(parents=True, exist_ok=True)
    (cfg / 'Dolphin.ini').write_text(
        '[Analytics]\nEnabled = False\nPermissionAsked = True\n'
        '[AutoUpdate]\nUpdateTrack =\n[Core]\nSerialPort1 = 255\nSerialPort2 = 255\n'
        'WiiSDCard = False\nWiiSDCardAllowWrites = False\nWiiSDCardEnableFolderSync = False\n'
        f'EnableWiiLink = {"True" if wiilink else "False"}\n'
        'OverrideRegionSettings = True\n'   # hardware keeps Korean for PAL-ID titles (e.g. Kirby TV HCMP)
        '[Interface]\nLanguageCode = ko\nConfirmStop = False\nRenderToMain = False\n'
        '[Display]\nRenderToMain = False\nRenderWindowWidth = 960\nRenderWindowHeight = 720\n'
        '[DSP]\nBackend = Null\n[General]\nISOPaths = 0\n', encoding='utf-8')
    (cfg / 'GFX.ini').write_text('[Hardware]\nVSync = False\n[Settings]\nInternalResolution = 1\n')
    (cfg / 'Logger.ini').write_text('[Options]\nWriteToFile = False\nWriteToConsole = False\n')
    (cfg / 'WiimoteNew.ini').write_text(
        '[Wiimote1]\nSource = 1\nDevice = XInput2/0/Virtual core pointer\n'
        'Buttons/A = `Click 1` | `a`\nButtons/B = `Click 3` | `b`\n'
        'Buttons/1 = `1`\nButtons/2 = `2`\nButtons/- = `minus`\nButtons/+ = `plus`\n'
        'Buttons/Home = `h`\nD-Pad/Up = `Up`\nD-Pad/Down = `Down`\n'
        'D-Pad/Left = `Left`\nD-Pad/Right = `Right`\nIR/Up = `Cursor Y-`\n'
        'IR/Down = `Cursor Y+`\nIR/Left = `Cursor X-`\nIR/Right = `Cursor X+`\n'
        '[Wiimote2]\nSource = 0\n[Wiimote3]\nSource = 0\n[Wiimote4]\nSource = 0\n')
    (cfg / 'GCPadNew.ini').write_text(gc_keyboard_config())


def prepare(alias, wiilink=False):
    """Copy the imported console NAND into a new numbered profile. The source is never written."""
    stopped()
    if not re.fullmatch(r'[a-z][a-z0-9-]*', alias):
        raise ValueError('Expected a lower-case alias')
    before = source_identity()
    for path in SOURCE.rglob('*'):
        if path.is_symlink():
            raise ValueError('Indirect source content refused')
    BASE.mkdir(parents=True, exist_ok=True)
    revision = 1
    while (BASE / f'{alias}-v{revision}').exists():
        revision += 1
    dest = runtime(f'{alias}-v{revision}'); dest.mkdir()
    shutil.copytree(SOURCE, dest / 'user', ignore=lambda folder, names: [n for n in names if n in OMIT or n.lower().endswith(('.dtm', '.sav'))])
    write_config(dest / 'user', wiilink)
    if source_identity() != before:
        raise ValueError('Console NAND source changed while copying')
    wii = dest / 'user/Wii'
    if hashlib.sha256(json.dumps(nand_manifest(wii), sort_keys=True).encode()).hexdigest() != before:
        raise ValueError('Copied NAND differs from its source')
    meta = dict(schema=1, kind='online', network='host', source='workspace/dolphin/baseline-user', source_identity=before,
                wiilink_kd=bool(wiilink), installed=[],
                locale_hashes={rel: digest(wii / rel) for rel in ('shared2/sys/SYSCONF', 'title/00000001/00000002/data/setting.txt')})
    (dest / 'profile.json').write_text(json.dumps(meta, indent=2))
    print(f'PASS prepared online {dest.name}: copy of the imported console NAND, WiiLink WC24 {"on" if wiilink else "off"}')
    return dest.name


def install(name, package):
    """Install every channel's Korean WAD of a hardware package into the profile NAND (saves kept)."""
    stopped()
    dest, meta = load(name)
    if not re.fullmatch(r'kwce-rc-sd-v[0-9]+', package):
        raise ValueError('Expected a kwce-rc-sd-vN package')
    root = direct(ROOT / 'workspace/hardware' / package / 'kwce-rc', ROOT / 'workspace/hardware')
    from .channels import load_library
    lib = load_library(); nand = lib.nand.EmuNAND(dest / 'user/Wii'); done = []
    for wad in sorted(root.glob('*/korean.wad')):
        if wad.parent.name == 'dvd-player':      # remove-only legacy channel
            continue
        raw = wad.read_bytes(); title = lib.title.Title(); title.load_wad(raw)
        nand.install_title(title, skip_hash=True)
        done.append(dict(channel=wad.parent.name, title_id=title.tmd.title_id, wad_sha256=hashlib.sha256(raw).hexdigest()))
    meta['installed'] = [dict(package=package, channels=done)] + meta.get('installed', [])
    (dest / 'profile.json').write_text(json.dumps(meta, indent=2))
    print(f'PASS installed {len(done)} Korean channels from {package} into online {name}')
    return done


def install_wads(name, paths):
    """Install individual project WADs (workspace/channels/...) into the profile copy for testing."""
    stopped()
    dest, meta = load(name)
    from .channels import load_library
    lib = load_library(); nand = lib.nand.EmuNAND(dest / 'user/Wii'); done = []
    for p in paths:
        wad = direct(ROOT / p, ROOT / 'workspace/channels')
        raw = wad.read_bytes(); title = lib.title.Title(); title.load_wad(raw)
        nand.install_title(title, skip_hash=True)
        done.append(dict(wad=str(wad.relative_to(ROOT)), title_id=title.tmd.title_id, wad_sha256=hashlib.sha256(raw).hexdigest()))
    meta['installed'] = [dict(package='individual', channels=done)] + meta.get('installed', [])
    (dest / 'profile.json').write_text(json.dumps(meta, indent=2))
    print(f'PASS installed {len(done)} project WAD(s) into online {name}')


def uninstall(name, title_ids):
    """Remove titles from the profile copy only (their save data, if any, is kept)."""
    stopped()
    dest, meta = load(name)
    from .channels import load_library
    nand = load_library().nand.EmuNAND(dest / 'user/Wii')
    for tid in title_ids:
        if not re.fullmatch(r'0001000[014][0-9a-f]{8}', tid):
            raise ValueError('Only channel/game titles can be removed from a profile')
        nand.uninstall_title(tid)
    meta['removed_from_copy'] = sorted(set(meta.get('removed_from_copy', [])) | set(title_ids))
    (dest / 'profile.json').write_text(json.dumps(meta, indent=2))
    print(f'PASS removed {len(title_ids)} title(s) from online {name} (copy only)')


WC24_KEYS = ('IPL.INC', 'NET.WCFG', 'IPL.IDL')


def enable_wc24(name):
    """Turn the console's WiiConnect24 system setting on in the copy (the dump was taken with it off).

    Only the three non-identity records are taken from the Forecast test NAND, as the offline
    profiles do; language, country and every identity record stay the console's own.
    """
    stopped()
    dest, meta = load(name)
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    from prepare_votes_local_settings import records
    target = dest / 'user/Wii/shared2/sys/SYSCONF'
    old = target.read_bytes(); reference = (ROOT / 'workspace/sandbox/forecast-v1/user/Wii/shared2/sys/SYSCONF').read_bytes()
    a, b = records(old), records(reference); updated = bytearray(old)
    for key in WC24_KEYS:
        start, end, kind = a[key]; left, right, other = b[key]
        if kind != other or end - start != right - left:
            raise ValueError('Setting type mismatch')
        updated[start:end] = reference[left:right]
    if len(updated) != len(old):
        raise ValueError('SYSCONF size changed')
    target.write_bytes(bytes(updated))
    meta['wc24_setting_enabled'] = list(WC24_KEYS)
    (dest / 'profile.json').write_text(json.dumps(meta, indent=2))
    validate(name)
    print(f'PASS WiiConnect24 system setting on in online {name} ({sum(x != y for x, y in zip(old, updated))} bytes)')


def set_wiilink(name, on):
    """Dolphin's own 'Enable WiiConnect24 via WiiLink' (KD downloads/mail go to WiiLink). Owner approved 2026-11-16."""
    stopped()
    dest, meta = load(name)
    ini = dest / 'user/Config/Dolphin.ini'; text = ini.read_text(encoding='utf-8')
    new = re.sub(r'EnableWiiLink = (True|False)', f'EnableWiiLink = {"True" if on else "False"}', text)
    if new == text and f'EnableWiiLink = {"True" if on else "False"}' not in text:
        raise ValueError('EnableWiiLink line missing')
    ini.write_text(new, encoding='utf-8'); meta['wiilink_kd'] = bool(on)
    (dest / 'profile.json').write_text(json.dumps(meta, indent=2))
    print(f'PASS online {name}: WiiConnect24 via WiiLink {"on" if on else "off"}')


PIPE_WIIMOTE = ('[Wiimote1]\nSource = 1\nDevice = Pipe/0/kwce-gc\n'
                'Buttons/A = `Button A`\nButtons/B = `Button B`\nButtons/1 = `Button X`\nButtons/2 = `Button Y`\n'
                'Buttons/- = `Button L`\nButtons/+ = `Button R`\nButtons/Home = `Button START`\n'
                'D-Pad/Up = `Button D_UP`\nD-Pad/Down = `Button D_DOWN`\nD-Pad/Left = `Button D_LEFT`\nD-Pad/Right = `Button D_RIGHT`\n'
                'IR/Up = `Axis MAIN Y +`\nIR/Down = `Axis MAIN Y -`\nIR/Left = `Axis MAIN X -`\nIR/Right = `Axis MAIN X +`\n'
                '[Wiimote2]\nSource = 0\n[Wiimote3]\nSource = 0\n[Wiimote4]\nSource = 0\n')


def use_pipe_input(name):
    """Exact pointer input: Wiimote 1 reads the profile FIFO (linux_dolphin_ui.py pointer/pad).

    pad A/B = A/B, X/Y = 1/2, L/R = -/+, START = HOME, D_* = D-pad.
    """
    stopped()
    dest, meta = load(name); user = dest / 'user'
    (user / 'Pipes').mkdir(exist_ok=True)
    if not (user / 'Pipes/kwce-gc').exists():
        os.mkfifo(user / 'Pipes/kwce-gc')
    (user / 'Config/WiimoteNew.ini').write_text(PIPE_WIIMOTE)
    meta['input'] = 'pipe'
    (dest / 'profile.json').write_text(json.dumps(meta, indent=2))
    print(f'PASS online {name}: Wiimote 1 on the profile pipe')


NINTENDO_OUIS = ('0009bf 0017ab 00191d 0019fd 001ae9 001b7a 001bea 001cbe 001dbc 001e35 001ea9 001f32 001fc5 002147 '
                 '0021bd 00224c 0022aa 0022d7 002331 0023cc 00241e 002444 0024f3 0025a0 002659 002709 34af2c 40f407 '
                 '58bda3 8c56c5 9ce635 a45c27 cc9e00 ccfb65 e00c7f e84ece 0403d6 04c8c3 182a7b 2c10c1 40d28a 582f40 '
                 '78a2a0 7cbb8a 98b6e9 b8ae6e d86bf7 e0e751').split()


def set_console_mac(name):
    """Give Dolphin the console's wireless MAC so Miis made on the console count as local.

    A Mii's system ID is checksum8(MAC[0:3]) + MAC[3:6]. The ID shared by most Miis in the copy's
    RFL_DB.dat is the console's; exactly one Nintendo OUI must match its checksum. The value is
    written only to the profile's Dolphin.ini and never printed.
    """
    stopped()
    dest, meta = load(name); user = dest / 'user'
    from collections import Counter
    db = (user / 'Wii/shared2/menu/FaceLib/RFL_DB.dat').read_bytes()
    if db[:4] != b'RNOD':
        raise ValueError('Mii database missing')
    ids = Counter(db[4 + 74 * i + 0x1c:4 + 74 * i + 0x20] for i in range(100) if any(db[4 + 74 * i:4 + 74 * i + 74]))
    sid, count = ids.most_common(1)[0]
    if count * 2 <= sum(ids.values()):
        raise ValueError('No majority Mii system ID')
    ouis = [o for o in NINTENDO_OUIS if sum(bytes.fromhex(o)) & 0xff == sid[0]]
    if len(ouis) != 1:
        raise ValueError('Console MAC is ambiguous')
    mac = ':'.join(f'{b:02x}' for b in bytes.fromhex(ouis[0]) + sid[1:])
    ini = user / 'Config/Dolphin.ini'; text = ini.read_text(encoding='utf-8')
    if re.search(r'^WirelessMac = .*$', text, re.M):
        text = re.sub(r'^WirelessMac = .*$', 'WirelessMac = ' + mac, text, flags=re.M)
    else:
        text = text.replace('[General]\n', '[General]\nWirelessMac = ' + mac + '\n', 1)
    ini.write_text(text, encoding='utf-8')
    meta['wireless_mac'] = 'derived from the console Mii system ID'
    (dest / 'profile.json').write_text(json.dumps(meta, indent=2))
    print(f'PASS online {name}: console wireless MAC set from {count}/{sum(ids.values())} Miis (value not shown)')


def keep_console_locale(name):
    """Allow mismatched region settings and restore the console's IPL.LNG/IPL.SADR in the copy.

    Without OverrideRegionSettings Dolphin rewrites SYSCONF language to English when a PAL-ID title
    boots (GetLanguageAdjustedForRegion); a real console keeps Korean.
    """
    stopped()
    dest, meta = load(name); user = dest / 'user'
    ini = user / 'Config/Dolphin.ini'; text = ini.read_text(encoding='utf-8')
    if 'OverrideRegionSettings' not in text:
        text = text.replace('[Core]\n', '[Core]\nOverrideRegionSettings = True\n', 1)
    ini.write_text(re.sub(r'OverrideRegionSettings = \w+', 'OverrideRegionSettings = True', text), encoding='utf-8')
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    from prepare_votes_local_settings import records
    target = user / 'Wii/shared2/sys/SYSCONF'; old = target.read_bytes(); ref = (SOURCE / 'Wii/shared2/sys/SYSCONF').read_bytes()
    a, b = records(old), records(ref); out = bytearray(old); changed = []
    for key in ('IPL.LNG', 'IPL.SADR'):
        s0, e0, k0 = a[key]; s1, e1, k1 = b[key]
        if k0 != k1 or e0 - s0 != e1 - s1:
            raise ValueError('Setting type mismatch')
        if old[s0:e0] != ref[s1:e1]:
            out[s0:e0] = ref[s1:e1]; changed.append(key)
    target.write_bytes(bytes(out))
    meta['override_region_settings'] = True
    (dest / 'profile.json').write_text(json.dumps(meta, indent=2))
    validate(name)
    print(f'PASS online {name}: region override on, restored {changed or "nothing"}')


def fictional_address(name):
    """Write the FICTIONAL Korean sample address (kwce.food_personal_data korean-spd) as pd.dat in the copy.

    pd.dat is encrypted with the console device ID (OTP NG ID in the copy's BootMii keys.bin, offset
    0x124). Neither the ID nor the result is printed. Never reads or keeps a real address.
    """
    stopped()
    dest, meta = load(name); wii = dest / 'user/Wii'
    from . import personal_data_format as fmt, food_personal_data as fpd
    keys = (wii / 'keys.bin').read_bytes()
    if len(keys) < 0x200:
        raise ValueError('keys.bin layout differs')
    device_id = int.from_bytes(keys[0x124:0x128], 'big')
    if not (wii / 'title/00010008/4843434a/content').is_dir():
        raise ValueError('Set Personal Data title not installed in the copy')
    plain = fpd.variant('korean-spd'); target = wii / fpd.PD_PATH.lstrip('/')
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup = PRIVATE / f'{name}-pd-before.bin'; PRIVATE.mkdir(parents=True, exist_ok=True)
        if not backup.exists(): backup.write_bytes(target.read_bytes())
    target.write_bytes(fmt.encrypt(plain, device_id))
    if fmt.decrypt(target.read_bytes(), device_id) != plain:
        raise ValueError('pd.dat roundtrip failed')
    meta['fictional_address'] = 'korean-spd sample (fictional)'
    (dest / 'profile.json').write_text(json.dumps(meta, indent=2))
    print(f'PASS online {name}: fictional Korean address written (console key, not shown)')


def load(name):
    dest = runtime(name)
    meta = json.loads(direct(dest / 'profile.json', dest).read_text())
    if meta.get('kind') != 'online':
        raise ValueError('Not an online profile')
    return dest, meta


def validate(name):
    dest, meta = load(name); user = dest / 'user'
    for p in user.rglob('*'):
        if p.is_symlink():
            raise ValueError('Indirect online runtime content refused')
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
    for key in ('WiiSDCard', 'WiiSDCardAllowWrites', 'WiiSDCardEnableFolderSync'):
        if c.getboolean('Core', key, fallback=False):
            raise ValueError('SD passthrough refused')
    for section in c.sections():
        for key, value in c[section].items():
            if value and ('path' in key or key in ('nandroot', 'defaultiso')) and not (key == 'isopaths' and value == '0'):
                if not value.startswith('/profile/user/') or '..' in Path(value).parts:
                    raise ValueError('Outside profile path refused')
    lock = json.loads(LOCK.read_text())
    exe = direct(ROOT / lock['executable'], ROOT / 'tools/linux')
    if digest(exe) != lock['executable_sha256']:
        raise ValueError('Pinned Linux Dolphin hash mismatch')
    return dest, meta, exe


def online_sandbox(dest, executable, args, gui=True):
    """The offline sandbox with exactly one difference: the host network namespace is shared."""
    base = sandbox(dest, '@EXECUTABLE@', [], gui=gui)
    at = base.index('--unshare-all'); cut = base.index('@EXECUTABLE@')
    extra = []
    for rel in NETWORK_FILES:
        path = Path('/etc', rel)
        if path.exists():
            extra += ['--ro-bind', str(path.resolve() if path.is_symlink() and rel == 'resolv.conf' else path), '/etc/' + rel]
    return base[:at + 1] + ['--share-net'] + base[at + 1:cut] + extra + [executable, *args]


def isolation_probe(dest):
    probe = ('import socket; from pathlib import Path; '
             'assert not Path("' + str(ROOT) + '/sd").exists(); '
             'assert not Path("' + str(ROOT) + '/workspace").exists(); '
             'assert sorted(Path("/home").iterdir()) == [Path("/home/sandbox")]; '
             'assert int(next(x for x in Path("/proc/self/status").read_text().splitlines() '
             'if x.startswith("CapEff:")).split()[1],16)==0; '
             'socket.setdefaulttimeout(8); socket.getaddrinfo("prod.wiilink24.com", 80); '
             'print("PASS online sandbox: network reachable, capabilities zero, home/project/SD hidden")')
    subprocess.run(online_sandbox(dest, '/usr/bin/python3', ['-c', probe], gui=False), check=True, timeout=20)


def running(name=None):
    result = []
    for record in BASE.glob('*/process.json'):
        if name is not None and record.parent.name != name:
            continue
        try:
            row = json.loads(record.read_text()); proc = Path('/proc') / str(row['pid'])
            start = proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19]
            command = proc.joinpath('cmdline').read_bytes().split(b'\0')
            if (start == row['start'] and os.path.samefile(proc / 'exe', row['executable'])
                    and os.path.samefile(proc / 'root/profile', record.parent) and b'/profile/user' in command):
                result.append(row)
        except (OSError, ValueError, KeyError):
            continue
    return result


def launch(name, title):
    if not re.fullmatch(r'[0-9a-f]{16}', title):
        raise ValueError('Expected a 16-digit title id')
    stopped()
    dest, meta, exe = validate(name)
    if not (dest / 'user/Wii/title' / title[:8] / title[8:] / 'content').is_dir():
        raise ValueError('Title is not installed in this profile')
    isolation_probe(dest)
    cmd = online_sandbox(dest, '/opt/dolphin/bin/dolphin-emu', ['--batch', '--user', '/profile/user', '--nand_title', title])
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
                command = proc.joinpath('cmdline').read_bytes().split(b'\0')
                if not os.path.samefile(proc / 'exe', exe) or not os.path.samefile(proc / 'root/profile', dest) or b'/profile/user' not in command:
                    continue
                row = {'pid': int(proc.name), 'start': proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19],
                       'executable': str(exe), 'network': 'host'}
                (dest / 'process.json').write_text(json.dumps(row))
                print(f'PASS launched online {name}: render window, real network')
                return
            except (OSError, ValueError):
                pass
        time.sleep(.1)
    child.terminate()
    raise ValueError('Unable to verify online Dolphin identity')


def stop(name):
    rows = running(name)
    for row in rows:
        os.kill(row['pid'], signal.SIGTERM)
    for _ in range(150):
        if not running(name):
            break
        time.sleep(.1)
    if running(name):
        raise ValueError('Dolphin has not stopped; no profile changes made')
    print(f'PASS stop: {len(rows)} online Dolphin process(es)')

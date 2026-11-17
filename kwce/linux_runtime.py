"""Offline Linux runtime. Never mount the project, SD, real NAND or host home.

Windows launchers remain separate. All writable files belong to a newly numbered
Linux profile; only the compositor socket is shared with the desktop session.
"""
from __future__ import annotations

import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'workspace/linux'
PRIVATE = ROOT / 'workspace/private/linux-setup'
LOCK = ROOT / 'configs/dolphin-linux.lock.json'


def default_profile():
    return json.loads((ROOT / 'configs/emulator-launchers-linux.json').read_text())['system_menu_profile']


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def content_manifest(user):
    """Immutable installed contents only; saves/config/cache remain writable."""
    wii = user / 'Wii'
    folders = [wii / 'shared1', *wii.glob('title/*/*/content')]
    return {p.relative_to(user).as_posix(): digest(p)
            for folder in folders if folder.is_dir()
            for p in sorted(folder.rglob('*')) if p.is_file()}


def direct(path, parent):
    if not path.resolve().is_relative_to(parent.resolve()):
        raise ValueError('Path escaped approved tree')
    for part in (path, *path.parents):
        if part == ROOT.parent:
            break
        if part.is_symlink() or part.is_junction():
            raise ValueError('Indirect project path refused')
    return path


def sources():
    catalog = json.loads((ROOT / 'configs/channels.catalog.json').read_text())
    result = {'menu': ('workspace/sandbox/gc-v7/user', '0000000100000002')}
    for channel in catalog['channels']:
        active = [i for i in channel['installs'] if i['role'] == 'active']
        if len(active) != 1:
            raise ValueError('Expected one active installation')
        result[channel['id']] = (f"workspace/sandbox/{active[0]['profile']}/user", channel['title_id'])
    return result


def runtime(name):
    if not re.fullmatch(r'[a-z][a-z0-9-]*-v[1-9][0-9]*', name):
        raise ValueError('Expected a numbered Linux profile alias')
    return direct(BASE / name, BASE)


def running(name=None):
    """Match executable, explicit user path, PID start time and network namespace."""
    result = []
    for record in BASE.glob('*/process.json'):
        if name is not None and record.parent.name != name:
            continue
        try:
            row = json.loads(record.read_text())
            proc = Path('/proc') / str(row['pid'])
            start = proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19]
            command = proc.joinpath('cmdline').read_bytes().split(b'\0')
            if (start == row['start'] and os.path.samefile(proc / 'exe', row['executable'])
                    and os.path.samefile(proc / 'root/profile', record.parent)
                    and b'/profile/user' in command
                    and os.readlink(proc / 'ns/net') == row['net_namespace']
                    and row['net_namespace'] != os.readlink('/proc/self/ns/net')):
                result.append(row)
        except (OSError, ValueError, KeyError):
            continue
    return result


def stopped():
    # Do not copy any profile while a native Dolphin is active, including a
    # personally launched process. Read process names only, never its UI/log.
    for proc in Path('/proc').iterdir():
        if proc.name.isdigit():
            try:
                if proc.joinpath('comm').read_text().strip().startswith('dolphin-emu'):
                    raise ValueError('Close Dolphin before preparing or checking profiles')
            except OSError:
                pass


def sanitize(user):
    wc = user / 'Wii/shared2/wc24'
    if wc.exists():
        shutil.rmtree(wc)
    wc.mkdir(parents=True)
    cfg = bytearray(1024)
    struct.pack_into('>II', cfg, 0, 0x57634366, 8)
    cfg[24:40] = b'@offline.invalid'
    for i in range(5):
        url = f'http://127.0.0.1:9/linux-disabled/{i}'.encode()
        cfg[156 + 128*i:156 + 128*i + len(url)] = url
    struct.pack_into('>I', cfg, 1020, sum(struct.unpack('>255I', cfg[:1020])) & 0xffffffff)
    for name in ('nwc24msg.cfg', 'nwc24msg.cbk'):
        (wc / name).write_bytes(cfg)
    dl = bytearray(0xf800)
    struct.pack_into('>II', dl, 0, 0x5763446c, 1)
    struct.pack_into('>H', dl, 16, 32)
    struct.pack_into('>H', dl, 20, 120)
    (wc / 'nwc24dl.bin').write_bytes(dl)
    net = user / 'Wii/shared2/sys/net/02/config.dat'
    if net.exists():
        net.write_bytes(bytes(net.stat().st_size))
    # No Windows device/path bindings, USB passthrough, SD sync or real Wiimotes.
    (user / 'Config/Dolphin.ini').write_text(
        '[Analytics]\nEnabled = False\nPermissionAsked = True\n'
        '[AutoUpdate]\nUpdateTrack =\n[Core]\nSerialPort1 = 255\nSerialPort2 = 255\n'
        'WiiSDCard = False\nWiiSDCardAllowWrites = False\nWiiSDCardEnableFolderSync = False\n'
        'MemcardAPath = /profile/user/GC/MemoryCardA.JAP.raw\n'
        'MemcardBPath = /profile/user/GC/MemoryCardB.JAP.raw\n'
        '[Interface]\nLanguageCode = ko\nConfirmStop = False\nRenderToMain = False\n'
        '[Display]\nRenderToMain = False\nRenderWindowWidth = 960\nRenderWindowHeight = 720\n'
        '[DSP]\nBackend = Null\n[General]\nISOPaths = 0\n', encoding='utf-8')
    (user / 'Config/GFX.ini').write_text('[Hardware]\nVSync = False\n[Settings]\nInternalResolution = 1\n')
    (user / 'Config/Logger.ini').write_text('[Options]\nWriteToFile = False\nWriteToConsole = False\n')
    (user / 'Config/WiimoteNew.ini').write_text(
        '[Wiimote1]\nSource = 1\nDevice = XInput2/0/Virtual core pointer\n'
        'Buttons/A = `Click 1` | `a`\nButtons/B = `Click 3` | `b`\n'
        'Buttons/1 = `1`\nButtons/2 = `2`\nButtons/- = `minus`\nButtons/+ = `plus`\n'
        'Buttons/Home = `h`\nD-Pad/Up = `Up`\nD-Pad/Down = `Down`\n'
        'D-Pad/Left = `Left`\nD-Pad/Right = `Right`\nIR/Up = `Cursor Y-`\n'
        'IR/Down = `Cursor Y+`\nIR/Left = `Cursor X-`\nIR/Right = `Cursor X+`\n'
        '[Wiimote2]\nSource = 0\n[Wiimote3]\nSource = 0\n[Wiimote4]\nSource = 0\n')
    (user / 'Config/GCPadNew.ini').write_text(gc_keyboard_config())


def gc_keyboard_config():
    return ('[GCPad1]\nDevice = XInput2/0/Virtual core pointer\n'
            'Buttons/A = `x`\nButtons/B = `z`\nButtons/X = `c`\nButtons/Y = `s`\n'
            'Buttons/Z = `d`\nButtons/Start = `Return`\n'
            'Main Stick/Up = `Up`\nMain Stick/Down = `Down`\n'
            'Main Stick/Left = `Left`\nMain Stick/Right = `Right`\n'
            'C-Stick/Up = `i`\nC-Stick/Down = `k`\nC-Stick/Left = `j`\nC-Stick/Right = `l`\n'
            'Triggers/L = `q`\nTriggers/R = `w`\n'
            'D-Pad/Up = `t`\nD-Pad/Down = `g`\nD-Pad/Left = `f`\nD-Pad/Right = `h`\n'
            '[GCPad2]\n[GCPad3]\n[GCPad4]\n')


def prepare(source, with_gc_disc=False, target_name=None):
    stopped()
    src_rel, title = sources()[source]
    src = direct(ROOT / src_rel, ROOT / 'workspace/sandbox')
    if not src.is_dir():
        raise ValueError('Approved source profile missing')
    for path in src.rglob('*'):
        if path.is_symlink() or path.is_junction():
            raise ValueError('Indirect source content refused')
    BASE.mkdir(parents=True, exist_ok=True)
    revision = 1
    while (BASE / f'{source}-v{revision}').exists():
        revision += 1
    if target_name is not None and not target_name.startswith(source + '-v'):
        raise ValueError('New profile alias must match its approved source')
    dest = runtime(target_name or f'{source}-v{revision}')
    dest.mkdir()
    # Only a sanitized experimental NAND is copied. Record originals locally.
    omitted = {'keys.bin', 'wc24', 'Logs', 'Cache', 'StateSaves', 'Dump', 'ScreenShots',
               'cdb.vff', 'cdb_bak.vff'}
    def ignore(folder, names):
        return [n for n in names if n in omitted or n.lower().endswith(('.pem', '.dtm', '.sav'))]
    shutil.copytree(src, dest / 'user', ignore=ignore)
    sanitize(dest / 'user')
    disc_hash = None
    if with_gc_disc:
        if source != 'menu':
            raise ValueError('Staged GC disc is only supported by the menu profile')
        disc = direct(src.parent / 'disc/GALJ01.iso', ROOT / 'workspace/sandbox')
        catalog = json.loads((ROOT / 'workspace/private/disc-catalog.json').read_text())
        expected = next(row['sha256'] for row in catalog['files'] if row['name'] == 'GALJ01.iso')
        if digest(disc) != expected:
            raise ValueError('Staged test disc differs from the private catalog')
        (dest / 'disc').mkdir()
        shutil.copyfile(disc, dest / 'disc/test.iso')
        disc_hash = digest(dest / 'disc/test.iso')
        if disc_hash != expected:
            raise ValueError('Linux disc copy verification failed')
        ini = dest / 'user/Config/Dolphin.ini'
        ini.write_text(ini.read_text().replace('[Core]\n', '[Core]\nDefaultISO = /profile/disc/test.iso\n', 1))
    for rel in ('shared2/sys/SYSCONF', 'title/00000001/00000002/data/setting.txt'):
        if digest(src / 'Wii' / rel) != digest(dest / 'user/Wii' / rel):
            raise ValueError('Korean locale preservation failed')
    contents = content_manifest(src)
    if content_manifest(dest / 'user') != contents:
        raise ValueError('Copied installed title/shared contents differ from approved source')
    (dest / 'profile.json').write_text(json.dumps({'schema': 1, 'source': source,
        'source_user': src_rel, 'title': title, 'network': 'isolated-offline', 'disc_sha256': disc_hash,
        'content_manifest': contents,
        'locale_hashes': {rel: digest(dest / 'user/Wii' / rel) for rel in
            ('shared2/sys/SYSCONF', 'title/00000001/00000002/data/setting.txt')}}, indent=2))
    print(f'PASS prepared {dest.name}: separate offline Linux copy')
    return dest.name


def validate(name, scrub_tasks=False):
    dest = runtime(name)
    direct(dest / 'profile.json', dest)
    direct(dest / 'process.json', dest)
    meta = json.loads((dest / 'profile.json').read_text())
    if meta['source'] not in sources() or meta['title'] != sources()[meta['source']][1]:
        raise ValueError('Profile is outside approved title catalog')
    user = dest / 'user'
    for p in user.rglob('*'):
        if p.is_symlink() or p.is_junction():
            raise ValueError('Indirect Linux runtime content refused')
        if p.name == 'keys.bin' or p.suffix.lower() in ('.pem', '.dtm'):
            raise ValueError('Keys, client certificates or movies refused')
    if content_manifest(user) != meta.get('content_manifest'):
        raise ValueError('Installed title/shared contents differ from the Linux copy manifest')
    sys.path.insert(0, str(ROOT / 'scripts'))
    from launch_dolphin import korean_locale
    if not korean_locale(user / 'Wii'):
        raise ValueError('Korean language/country changed')
    setting = 'title/00000001/00000002/data/setting.txt'
    if digest(user / 'Wii' / setting) != meta['locale_hashes'][setting]:
        raise ValueError('Korean region changed')
    cfg = (user / 'Wii/shared2/wc24/nwc24msg.cfg').read_bytes()
    if (len(cfg) != 1024 or cfg[:8] != bytes.fromhex('5763436600000008')
            or int.from_bytes(cfg[20:24], 'big') not in (0, 1) or cfg[88:156] != bytes(68)
            or sum(struct.unpack('>255I', cfg[:1020])) & 0xffffffff != int.from_bytes(cfg[1020:], 'big')):
        raise ValueError('Synthetic unregistered WC24 config changed')
    original = (ROOT / 'workspace/dolphin/baseline-user/Wii/shared2/wc24/nwc24msg.cfg').read_bytes()
    if cfg[8:16] == original[8:16]:
        raise ValueError('Authentic console identity refused')
    from urllib.parse import urlparse
    for i in range(5):
        u = urlparse(cfg[156+128*i:284+128*i].split(b'\0')[0].decode('ascii'))
        if u.scheme != 'http' or u.hostname != '127.0.0.1' or u.port != 9:
            raise ValueError('Non-local WC24 destination refused')
    dl = (user / 'Wii/shared2/wc24/nwc24dl.bin').read_bytes()
    if len(dl) != 0xf800 or dl[:8] != bytes.fromhex('5763446c00000001'):
        raise ValueError('Offline WC24 tasks changed; prepare a fresh revision')
    c = configparser.ConfigParser(strict=False)
    c.read(user / 'Config/Dolphin.ini')
    virtual_sd = meta.get('virtual_sd')
    if virtual_sd:
        if (virtual_sd.get('relative_path') != 'Wii/sd.raw'
                or virtual_sd.get('read_only') is not True
                or not c.getboolean('Core', 'WiiSDCard', fallback=False)
                or c.get('General', 'WiiSDCardPath', fallback='') != '/profile/user/Wii/sd.raw'):
            raise ValueError('Virtual SD must be a pinned read-only profile image')
        sd_image = direct(user / 'Wii/sd.raw', user)
        if (not sd_image.is_file() or sd_image.stat().st_size != 64*1024*1024
                or digest(sd_image) != virtual_sd.get('sha256')):
            raise ValueError('Virtual SD image differs from its reviewed fixture')
    for key in (('WiiSDCardAllowWrites', 'WiiSDCardEnableFolderSync') if virtual_sd else
                ('WiiSDCard', 'WiiSDCardAllowWrites', 'WiiSDCardEnableFolderSync')):
        if c.getboolean('Core', key, fallback=False):
            raise ValueError('SD passthrough refused')
    for key in ('SerialPort1', 'SerialPort2'):
        if c.getint('Core', key, fallback=255) != 255:
            raise ValueError('Network devices refused')
    for section in c.sections():
        for key, value in c[section].items():
            if value and ('path' in key or key in ('nandroot', 'defaultiso')):
                if key == 'isopaths' and value == '0':
                    continue
                if key == 'defaultiso' and value == '/profile/disc/test.iso' and meta.get('disc_sha256'):
                    continue
                if not value.startswith('/profile/user/') or '..' in Path(value).parts:
                    raise ValueError('Outside profile path refused')
    if meta.get('disc_sha256'):
        disc = direct(dest / 'disc/test.iso', dest)
        if digest(disc) != meta['disc_sha256']:
            raise ValueError('Linux staged disc changed')
    lock = json.loads(LOCK.read_text())
    exe = direct(ROOT / lock['executable'], ROOT / 'tools/linux')
    if digest(exe) != lock['executable_sha256']:
        raise ValueError('Pinned Linux Dolphin hash mismatch')
    if any(dl[2048:]):
        if not scrub_tasks:
            raise ValueError('Offline tasks need scrubbing; launch resets them before starting')
        stopped()
        (user / 'Wii/shared2/wc24/nwc24dl.bin').write_bytes(dl[:2048] + bytes(len(dl)-2048))
    return dest, meta, exe


def sandbox(dest, executable, args, gui=True):
    bwrap = shutil.which('bwrap')
    if not bwrap:
        raise ValueError('bubblewrap required; unisolated fallback refused')
    prefix = ROOT / json.loads(LOCK.read_text())['prefix']
    cmd = [bwrap, '--unshare-all', '--new-session', '--cap-drop', 'ALL',
           '--clearenv', '--ro-bind', '/usr', '/usr', '--symlink', 'usr/lib', '/lib',
           '--symlink', 'usr/lib', '/lib64', '--symlink', 'usr/bin', '/bin',
           '--proc', '/proc', '--ro-bind', '/sys', '/sys', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/run',
           '--dir', '/home', '--dir', '/home/sandbox', '--dir', '/etc',
           '--ro-bind', str(prefix), '/opt/dolphin',
           # gettext uses the compiled install prefix. Expose only that tools
           # directory at its build path as well, never the containing project.
           '--ro-bind', str(prefix), str(prefix), '--bind', str(dest), '/profile',
           '--setenv', 'HOME', '/home/sandbox', '--setenv', 'PATH', '/usr/bin',
           '--setenv', 'LANG', 'C.UTF-8', '--setenv', 'XDG_CONFIG_HOME', '/profile/xdg-config',
           '--setenv', 'XDG_CACHE_HOME', '/profile/xdg-cache', '--chdir', '/profile']
    for rel in ('fonts', 'ld.so.cache', 'localtime'):
        if Path('/etc', rel).exists():
            cmd += ['--ro-bind', '/etc/' + rel, '/etc/' + rel]
    if (dest / 'disc').is_dir():
        cmd += ['--ro-bind', str(dest / 'disc'), '/profile/disc']
    if gui:
        display = os.environ.get('DISPLAY', '')
        if not re.fullmatch(r':[0-9]+(?:\.[0-9]+)?', display):
            raise ValueError('A local X11/XWayland display is required')
        sock = '/tmp/.X11-unix/X' + display[1:].split('.')[0]
        cmd += ['--ro-bind', sock, sock, '--setenv', 'DISPLAY', display,
                '--setenv', 'QT_QPA_PLATFORM', 'xcb', '--setenv', 'QT_X11_NO_MITSHM', '1']
        auth = os.environ.get('XAUTHORITY')
        if auth and Path(auth).is_file():
            cmd += ['--ro-bind', auth, '/tmp/xauthority', '--setenv', 'XAUTHORITY', '/tmp/xauthority']
        # Render nodes only: no physical Wii/USB/input/storage passthrough.
        for node in sorted(Path('/dev/dri').glob('renderD*')):
            cmd += ['--dev-bind', str(node), str(node)]
        # Proprietary NVIDIA GL/Vulkan additionally needs these graphics nodes.
        # Do not grant raw input, USB, block devices or NVIDIA management caps.
        for name in ('nvidia0', 'nvidiactl', 'nvidia-modeset', 'nvidia-uvm'):
            node = Path('/dev') / name
            if node.exists():
                cmd += ['--dev-bind', str(node), str(node)]
        if Path('/dev/nvidiactl').exists():
            cmd += ['--setenv', '__GLX_VENDOR_LIBRARY_NAME', 'nvidia']
    return cmd + [executable, *args]


def isolation_probe(dest):
    probe = ('import os,socket; from pathlib import Path; '
             'assert not Path("/profile/../../sd").exists(); '
             'assert not Path("' + str(ROOT) + '/sd").exists(); '
             'assert sorted(Path("/home").iterdir()) == [Path("/home/sandbox")]; '
             'assert int(next(x for x in Path("/proc/self/status").read_text().splitlines() '
             'if x.startswith("CapEff:")).split()[1],16)==0; '
             'assert all(name == "lo" for _,name in socket.if_nameindex()); '
             's=socket.socket(); s.settimeout(1); '
             'assert s.connect_ex(("192.0.2.1",443)) != 0; print("PASS Linux isolation: external network denied, capabilities zero, SD/home hidden")')
    subprocess.run(sandbox(dest, '/usr/bin/python3', ['-c', probe], gui=False), check=True,
                   timeout=10)


def stop(name):
    rows = running(name)
    for row in rows:
        os.kill(row['pid'], signal.SIGTERM)
    import time
    for _ in range(100):
        if not running(name):
            break
        time.sleep(.1)
    if running(name):
        raise ValueError('Dolphin has not stopped; no profile changes made')
    if rows:
        validate(name, scrub_tasks=True)
    print(f'PASS stop: {len(rows)} validated Linux Dolphin process(es)')

"""Wii Speak Channel Dolphin boot test bed: constants and pure checks.

The bed boots the OFFICIAL Korean channel (000100014843464b v512) first and the
hardware-v1 candidate (content 1 = ported Wiimmfi patch) as the comparison
build, in a clone of the sanitized votes-test-v1 profile. Dolphin gets no
microphone: USB/Bluetooth passthrough and every emulated USB device (Wii Speak,
Logitech mic, Skylander portal, Infinity base) stay off, and the capability-0
AppContainer grants neither microphone nor network. There is no local server
because the channel needs no feed. Used by scripts/prepare_wiispeak_test.py,
scripts/install_wiispeak_test.py and scripts/launch_wiispeak.py.
"""
import configparser
import io
import json
import re
from pathlib import Path

TITLE = '000100014843464b'
PROFILE = 'wiispeak-test-v1-user'
SANDBOX = 'workspace/sandbox/wiispeak-test-v1'
HELPER = 'tools/wiispeak-sandbox/v1/bin'
TEMPLATE = 'workspace/sandbox/votes-test-v1'
CHANNEL = 'workspace/channels/wiispeak'
LOCK = 'configs/wiispeak-runtime.lock.json'
ACTIVE = CHANNEL + '/active-build.json'
RUNNER = 'WiiSpeakRunner'
BASELINE = 'original-v512'
BUILDS = {BASELINE: 'originals/wiispeak-korea-v512.wad', 'hardware-v1': 'hardware-v1/wiispeak-ko-wiimmfi.wad'}
# Must stay byte-identical to the template: Wii Menu, IOS56 (the channel's IOS), BC, MIOS.
SYSTEM_TITLES = ('00000002', '00000038', '00000100', '00000101')

# Dolphin.ini values forced by the bed (System::Main keys of the pinned Dolphin build).
SETTINGS = (
    ('Core', 'DefaultISO', ''), ('Core', 'EnableWiiLink', 'False'), ('Core', 'OverrideRegionSettings', 'True'),
    ('Core', 'WiiSDCard', 'False'), ('Core', 'WiiSDCardEnableFolderSync', 'False'), ('Core', 'WiiSDCardAllowWrites', 'False'),
    ('Interface', 'UsePanicHandlers', 'True'),
    ('USBPassthrough', 'Devices', ''), ('BluetoothPassthrough', 'Enabled', 'False'),
    ('EmulatedUSBDevices', 'EmulateWiiSpeak', 'False'), ('EmulatedUSBDevices', 'EmulateLogitechMic', 'False'),
    ('EmulatedUSBDevices', 'EmulateSkylanderPortal', 'False'), ('EmulatedUSBDevices', 'EmulateInfinityBase', 'False'),
)

_APPROVED = 'bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","news-v1"),StringComparison.OrdinalIgnoreCase);'
_BLOCK_START = '   if(args.Length!=3||args[2]!="0001000248414745"'
_BLOCK_END = '   File.WriteAllText(Path.Combine(root,"child-exit.json")'
_BLOCK = '''   if(args.Length!=3||args[2]!="000100014843464b"||(args[1]!="menu"&&args[1]!="channel"))throw new Exception("Expected approved Wii Speak title and mode");
   string exe=Path.Combine(root,"Dolphin-x64","Dolphin.exe");string user=Path.Combine(root,"user");
   string boot=args[1]=="menu"?" --nand_title 0000000100000002":" --nand_title "+args[2];
   // No local server: Wii Speak needs no feed, and every outside connection stays denied.
   int childCode=Run(sid,exe,"--user "+Quote(user)+boot,Path.GetDirectoryName(exe));
'''


def derive_runner(text):
    """FeedRunner.cs -> WiiSpeakRunner.cs: same capability-0 container, no feed server."""
    if (text.count(_APPROVED) != 1 or text.count(_BLOCK_START) != 1 or text.count(_BLOCK_END) != 1
            or text.count('class FeedRunner') != 1):
        raise ValueError('Wii Speak helper source guard differs')
    start, end = text.index(_BLOCK_START), text.index(_BLOCK_END)
    if not start < end:
        raise ValueError('Wii Speak helper source order differs')
    out = (text[:start] + _BLOCK + text[end:]).replace(
        _APPROVED, _APPROVED.replace('"news-v1"', '"wiispeak-test-v1"')).replace('class FeedRunner', 'class ' + RUNNER)
    if ('FeedServer.exe' in out or 'Spawn(sid' in out or '"wiispeak-test-v1"' not in out or TITLE not in out
            or 'Child has capabilities' not in out):
        raise ValueError('Wii Speak helper derivation failed')
    return '// Derived by kwce.wiispeak_testbed for the Wii Speak boot bed: no local feed server is spawned.\n' + out


def pinned_builds(channel):
    """Approved WAD hashes: the acquisition-pinned official original and hardware-v1 built from it."""
    channel = Path(channel)
    acquisition = json.loads((channel / 'originals/acquisition.json').read_text(encoding='utf-8'))
    rows = [r for r in acquisition['titles'] if r.get('alias') == Path(BUILDS[BASELINE]).name]
    if (len(rows) != 1 or rows[0].get('title_id') != TITLE or rows[0].get('version') != 512
            or rows[0].get('tmd_signature_valid') is not True or rows[0].get('content_sha1_verified') is not True):
        raise ValueError('Official Korean Wii Speak original is not pinned')
    meta = json.loads((channel / 'hardware-v1/build-manifest.json').read_text(encoding='utf-8'))
    if (meta.get('title_id') != TITLE or meta.get('title_version') != 512 or meta.get('hardware_candidate') is not True
            or meta.get('changed_contents') != [1] or meta.get('original_sha256') != rows[0]['sha256']):
        raise ValueError('Wii Speak hardware-v1 manifest differs from the pinned original')
    pinned = {BASELINE: rows[0]['sha256'], 'hardware-v1': meta['wad_sha256']}
    if any(not re.fullmatch('[0-9a-f]{64}', v) for v in pinned.values()) or len(set(pinned.values())) != 2:
        raise ValueError('Wii Speak build hashes invalid')
    return pinned


def sanitized_dolphin_ini(text, source, base):
    """Template Dolphin.ini -> bed Dolphin.ini: paths moved to the bed, SETTINGS forced (case-insensitive keys)."""
    cfg = configparser.ConfigParser(strict=False, interpolation=None)
    cfg.optionxform = str
    cfg.read_string(text)
    pairs = [(str(source), str(base)), (Path(source).as_posix(), Path(base).as_posix())]
    for section in cfg.sections():
        for key, value in cfg[section].items():
            for old, new in pairs:
                value = value.replace(old, new)
            cfg[section][key] = value
    for section, key, value in SETTINGS:
        name = next((s for s in cfg.sections() if s.lower() == section.lower()), None)
        if name is None:
            cfg.add_section(section)
            name = section
        existing = [k for k in cfg[name] if k.lower() == key.lower()]
        for extra in existing[1:]:
            cfg.remove_option(name, extra)
        cfg[name][existing[0] if existing else key] = value
    out = io.StringIO()
    cfg.write(out)
    return out.getvalue()


def _flag(values, key, default):
    raw = values.get(key, default).strip().lower()
    if raw not in configparser.ConfigParser.BOOLEAN_STATES:
        raise ValueError('Unreadable Dolphin setting: ' + key)
    return configparser.ConfigParser.BOOLEAN_STATES[raw]


def check_dolphin_ini(path, user):
    """Refuse a disc, WiiLink, SD, hidden panics, any passthrough/emulated USB device or an outside path."""
    cfg = configparser.ConfigParser(strict=False, interpolation=None)
    cfg.read(path, encoding='utf-8-sig')
    s = {}
    for name in cfg.sections():  # Dolphin matches sections and keys case-insensitively
        s.setdefault(name.lower(), {}).update(cfg[name])
    core = s.get('core', {})
    if core.get('defaultiso', '').strip():
        raise ValueError('Wii Speak bed must not boot a disc')
    if _flag(core, 'enablewiilink', 'False'):
        raise ValueError('WiiLink must stay off in the Wii Speak bed')
    for key in ('wiisdcard', 'wiisdcardenablefoldersync', 'wiisdcardallowwrites'):
        if _flag(core, key, 'False'):
            raise ValueError('Wii Speak bed SD access refused')
    if not _flag(s.get('interface', {}), 'usepanichandlers', 'True'):
        raise ValueError('Panic dialogs must stay visible for the boot test')
    if s.get('usbpassthrough', {}).get('devices', '').strip():
        raise ValueError('Host USB passthrough refused')
    if _flag(s.get('bluetoothpassthrough', {}), 'enabled', 'False'):
        raise ValueError('Bluetooth passthrough refused')
    for key in ('emulatewiispeak', 'emulatelogitechmic', 'emulateskylanderportal', 'emulateinfinitybase'):
        if _flag(s.get('emulatedusbdevices', {}), key, 'False'):
            raise ValueError('Emulated USB device (microphone) refused')
    for values in s.values():
        for key, value in values.items():
            if (re.fullmatch(r'.*path(override)?\d*', key) or key in ('nandroot', 'dump', 'load')) and value.strip():
                if not Path(value.strip()).resolve().is_relative_to(Path(user).resolve()):
                    raise ValueError('Wii Speak bed outside profile path')

"""Forwarder deliveries: the menu keeps a ~0.3 MiB loader resident; the reviewed
player is a separate SD file that the loader reads and verifies after handoff.

RAM definitions and SD data only. No NAND, IOS or WAD content.
v1: native76 + R61 (first forwarder delivery, replaces the resident player).
v2: native77 + R64 (still-menu display, presentation cadence, battery bars).
v3: native79 + R66 (console HOME frame, Wii cursor outside HOME). Shipped inside
    RC31 only; there is no separate v3 delivery package (frozen_inputs pins it).
"""
import hashlib
import json
from pathlib import Path

from .dvd_integrated_sd import ROOT, TARGETS, DEFINITIONS, qualified
from .dvd_player_trace_sd import upgrade
from .gcmce_recovery import sha, direct
from .gc_card_encoding_sd import wii_mount

MODULE = 'kwce/dvd/boot.ash'
PLAYER_PATH = 'kwce/dvd/player.dol'
VERSIONS = {
    1: dict(hook=76, previous_hook=72, player=61, module=21, previous='kwce-dvd-player-trace-v6'),
    2: dict(hook=77, previous_hook=76, player=64, module=22, previous='kwce-dvd-forwarder-v1'),
    3: dict(hook=79, previous_hook=77, player=66, module=24, previous='kwce-dvd-forwarder-v2'),
}
CURRENT = 2
# Evidence the generic integrated gate does not cover.
EXTRA_V1 = {'general_channels_open_with_resident_bundle', 'menu_return_then_general_channel',
            'forwarder_missing_player_returns', 'forwarder_corrupt_player_returns',
            'forwarder_reproducibility', 'player_reproducibility',
            'dvd_disable_bit_clear_contract', 'runtime_error_return'}
EXTRA_V2 = EXTRA_V1 | {'still_menu_first_display', 'still_menu_page_switch',
                       'menu_return_single_press', 'presentation_rate_menu_and_playback',
                       'synthetic_menu_regression'}
# Names kept for the current delivery (tests and the export script use them).
HOOK, PREVIOUS_HOOK, PLAYER, MODULE_REVISION = (VERSIONS[CURRENT][k] for k in ('hook', 'previous_hook', 'player', 'module'))
PREVIOUS_PACKAGE = VERSIONS[CURRENT]['previous']
EXTRA = EXTRA_V2


def names(version):
    return (f'dvd-forwarder-v{version}', f'KWCE-DVD-FORWARDER-v{version}-ko.txt',
            f'KWCE-DVD-FORWARDER-v{version}-manifest.json')


def extra(version):
    return EXTRA_V1 if version == 1 else EXTRA_V2


def paths(version):
    return TARGETS | {MODULE, PLAYER_PATH, names(version)[1]}


def previous_runtime(version=CURRENT):
    """Hashes the card must hold before this delivery (definitions excluded)."""
    base = json.loads((ROOT/'workspace/hardware/kwce-dvd-integrated-v1/package-manifest.json').read_text())
    last = json.loads((ROOT/'workspace/hardware/kwce-dvd-player-trace-v6/package-manifest.json').read_text())
    runtime = {**base['runtime_inputs'], MODULE: last['files'][MODULE]}
    for v in range(1, version):
        done = json.loads((ROOT/f'workspace/hardware/kwce-dvd-forwarder-v{v}/package-manifest.json').read_text())
        runtime = {**runtime, MODULE: done['files'][MODULE], PLAYER_PATH: done['files'][PLAYER_PATH]}
    return runtime


def frozen_inputs(version=CURRENT):
    """Return (module bytes, player bytes) only for the exact frozen pair."""
    from .formats import ash_decompress
    row = VERSIONS[version]
    folder = ROOT/f'workspace/experiments/dvd-native-module-v{row["module"]}'
    record = json.loads((folder/'manifest.json').read_text())
    build = ROOT/f'workspace/channels/dvd-player/build-v{row["player"]}'
    manifest = json.loads((build/'build-manifest.json').read_text())
    module = (folder/'player.ash').read_bytes(); player = (build/'boot.dol').read_bytes()
    hook = json.loads((ROOT/f'workspace/experiments/dvd-native-hook-v{row["hook"]}/manifest.json').read_text())
    if (record.get('kind') != 'forwarder' or record.get('debug_no_pin') or record['source_build'] != row['player'] or
            manifest.get('host') != 'linux' or manifest.get('css_decryption') is not False or
            hashlib.sha256(player).hexdigest() != manifest['boot_dol_sha256'] or
            record['player_sha256'] != manifest['boot_dol_sha256'] or
            ash_decompress(module) != (folder/'forwarder.dol').read_bytes() or
            hashlib.sha256(module).hexdigest() != hook['module_sha256'] or
            hook.get('sd_player_sha256') != manifest['boot_dol_sha256'] or
            hook.get('sd_player_path') != PLAYER_PATH or not hook.get('forwarder') or
            hook.get('source_revision') != 37):
        raise ValueError('Forwarder/player/menu pins differ')
    return module, player


def sd_files(package):
    package = Path(package); raw = (package/'package-manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != (package/'package-manifest.sha256').read_text().strip():
        raise ValueError('Forwarder manifest mismatch')
    m = json.loads(raw)
    version = next((v for v in VERSIONS if names(v)[0] == m.get('kind')), 0)
    if not version: raise ValueError('Unreviewed forwarder package')
    row = VERSIONS[version]; _, readme, manifest = names(version)
    if (m.get('nand_write') is not False or m.get('gc_changed') is not False or
            m.get('hook_revision') != row['hook'] or m.get('player_revision') != row['player'] or
            set(m.get('files', {})) != paths(version) or set(m.get('expected_inputs', {})) != DEFINITIONS or
            m.get('runtime_inputs') != previous_runtime(version)):
        raise ValueError('Forwarder package scope mismatch')
    q = direct(package/'qualification.json', package)
    if sha(q) != m['qualification_sha256']: raise ValueError('Forwarder qualification pin changed')
    proof = qualified(q, row['hook'])
    if any(proof['checks'].get(k) is not True for k in extra(version)):
        raise ValueError('Forwarder qualification incomplete')
    old = {r: direct(package/'expected'/r, package).read_bytes() for r in DEFINITIONS}
    if any(hashlib.sha256(b).hexdigest() != m['expected_inputs'][r] for r, b in old.items()):
        raise ValueError('Expected definitions changed')
    module, player = frozen_inputs(version)
    if (direct(package/MODULE, package).read_bytes() != module or
            direct(package/PLAYER_PATH, package).read_bytes() != player):
        raise ValueError('Packaged loader/player differ from the frozen pair')
    files = []
    # Player first, loader next, templates, active definition last: an
    # interrupted copy leaves definitions that reject a mismatched loader by
    # hash, or a loader that rejects a mismatched player by hash (the DVD entry
    # is unavailable or returns to the menu), never a half-matched pair running.
    order = [PLAYER_PATH, MODULE, readme] + sorted(TARGETS - {'apps/Priiloader/hacks_hash.ini'}) + ['apps/Priiloader/hacks_hash.ini']
    for rel in order:
        p = direct(package/rel, package)
        if sha(p) != m['files'][rel]: raise ValueError('Forwarder payload mismatch')
        if rel in TARGETS and p.read_bytes() != upgrade(old[rel], row['previous_hook'], row['hook']):
            raise ValueError('Forwarder definition differs')
        files.append((p, rel))
    files.append((package/'package-manifest.json', manifest))
    return m, files


def verify_card(package, card):
    m, files = sd_files(package); card = Path(card); wii_mount(card)
    version = next(v for v in VERSIONS if names(v)[0] == m['kind'])
    replaced = TARGETS | {MODULE} | ({PLAYER_PATH} if version >= 2 else set())
    for rel, h in (m['expected_inputs'] | m['runtime_inputs']).items():
        if sha(direct(card/rel, card)) != h: raise ValueError('SD changed since forwarder review')
    for _, rel in files:
        p = direct(card/rel, card)
        if p.with_name(p.name+'.kwce-new').exists(): raise ValueError('Existing staged file retained')
        if rel not in replaced and p.exists(): raise ValueError('Numbered delivery already exists')

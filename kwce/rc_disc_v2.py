"""Disc-channel profiles for RC30+: current GC card menu + forwarder DVD (Priiloader RAM hacks only).

GC sections keep the three names/order the installer and earlier tools know:
  1 'Wii/GC save menu'                -- unchanged
  2 'Japanese memory card encoding'   -- SJIS card patch + per-card VerifyID thunk
                                         (gc_card_encoding) + ANSI format default (gc_card_format)
  3 'Japanese save comments (CP932)'  -- CP932 adapter + per-save region dispatcher (gc_comment_region)
Sections 1-3 equal what the SD already runs (RC29 + kwce-gc-card-encoding-v1) plus the two
2026-11-14 card-menu fixes.

The DVD section is the frozen integrated definition of hook 77 (forwarder delivery v2). Its
bytes are independent of the GC sections: no run of hook 77 overlaps a GC run (checked
here), and its hashes are original-menu words.

Runtime SD files: kwce/dvd/{menu,icon,home,wbf1} as installed by RC29 (native pin) and
kwce/dvd/{boot.ash,player.dol} from the frozen forwarder pair. Each must equal the bytes the
forwarder-v2 delivery left on the SD.
"""
import json
from pathlib import Path

from .gc_card_encoding import patch_card_encodings
from .gc_card_format import patch_format_ansi
from .gc_comment_region import patch_comment_region
from .gc_native import patch_gc_native
from .priiloader_hacks import GROUPS, _runs, _unique_hash, _words
from .priiloader_legacy import parse

ROOT = Path(__file__).resolve().parents[1]
GC_CARD_MENU = 2


def gc_images(menu):
    """Full menu image after each GC section, in section order."""
    cards = patch_gc_native(menu, japanese_cards=True)[0]
    comments = patch_gc_native(menu, japanese_cards=True, japanese_comments=True)[0]
    return [
        (GROUPS[0][0], patch_gc_native(menu)[0]),
        (GROUPS[1][0], patch_format_ansi(patch_card_encodings(cards)[0])[0]),
        (GROUPS[2][0], patch_comment_region(patch_format_ansi(patch_card_encodings(comments)[0])[0])[0]),
    ]


def gc_entries(menu):
    previous, entries = menu, []
    for name, image in gc_images(menu):
        pairs = [(_unique_hash(menu, a, (b - a) // 4), _words(image, a, b)) for a, b in _runs(previous, image)]
        entries.append(dict(name=name, pairs=pairs))
        previous = image
    return entries


def _hook(revision):
    folder = ROOT / f'workspace/experiments/dvd-native-hook-v{revision}'
    return folder, json.loads((folder / 'manifest.json').read_text())


def dvd_entry(revision):
    """The frozen DVD section as word pairs (re-encoding must give the same section bytes)."""
    import struct
    from .dvd_integrated_hardware import definition
    from .priiloader_legacy import checked_ini
    raw = definition(revision)
    row = dict(parse(raw)[0])
    words = lambda b: list(struct.unpack(f'>{len(b) // 4}I', b))
    row['pairs'] = [(words(h), words(p)) for h, p in row['pairs']]
    menu = (ROOT / 'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    if checked_ini(menu, [row], packed=True) != raw:
        raise ValueError('Frozen DVD section does not re-encode identically')
    return row


def final_image(menu, dvd_revision=None):
    """Expected menu after all KWCE sections of a profile (gc-only layout excluded)."""
    image = bytearray(gc_images(menu)[-1][1])
    if dvd_revision is not None:
        folder, _ = _hook(dvd_revision)
        base = patch_gc_native(menu, japanese_cards=True, japanese_comments=True)[0]
        hook = (folder / 'menu.dol').read_bytes()
        dvd = _runs(base, hook)
        gc = _runs(menu, bytes(image))
        if any(a < d and c < b for a, b in gc for c, d in dvd):
            raise ValueError('DVD hook overlaps a GC section')
        for a, b in dvd:
            image[a:b] = hook[a:b]
        # Without the two card-menu fixes this must be the frozen hook menu the DVD was qualified on.
        frozen = bytearray(patch_card_encodings(base)[0])
        for a, b in dvd:
            frozen[a:b] = hook[a:b]
        if bytes(frozen) != (folder / 'menu-with-card-encoding.dol').read_bytes():
            raise ValueError('Frozen hook menu differs')
    return bytes(image)


def runtime_files(native_pin, forwarder_version, lib):
    """SD files under kwce/dvd for the forwarder DVD, checked against the delivered SD state."""
    from .dvd_forwarder_sd import VERSIONS, frozen_inputs, MODULE, PLAYER_PATH
    from .dvd_native_hardware import runtime_files as native_files
    from .rc_hardware import sha
    files = native_files(native_pin, lib)
    module, player = frozen_inputs(forwarder_version)
    files[MODULE] = module
    files[PLAYER_PATH] = player
    folder = ROOT / f'workspace/hardware/kwce-dvd-forwarder-v{forwarder_version}'
    if folder.exists():
        delivered = json.loads((folder / 'package-manifest.json').read_text())
        expected = {**delivered['runtime_inputs'], MODULE: delivered['files'][MODULE],
                    PLAYER_PATH: delivered['files'][PLAYER_PATH]}
        if {k: sha(v) for k, v in files.items()} != expected:
            raise ValueError('DVD runtime files differ from the forwarder delivery')
    else:
        # RC31+: a forwarder pair shipped only inside the RC (no separate delivery). The
        # loader/player pair is the one the hook pins (frozen_inputs). home.arc follows the
        # RC's HOME pin; every other SD resource must equal the last forwarder delivery.
        last = max(v for v in VERSIONS if v < forwarder_version and
                   (ROOT / f'workspace/hardware/kwce-dvd-forwarder-v{v}').exists())
        delivered = json.loads((ROOT / f'workspace/hardware/kwce-dvd-forwarder-v{last}'
                                / 'package-manifest.json').read_text())['runtime_inputs']
        home = 'kwce/dvd/home.arc'
        if (set(files) != set(delivered) or
                any(sha(files[k]) != h for k, h in delivered.items() if k not in (MODULE, PLAYER_PATH, home))):
            raise ValueError('Unchanged DVD runtime files differ from the last forwarder delivery')
    return files, VERSIONS[forwarder_version]['hook']

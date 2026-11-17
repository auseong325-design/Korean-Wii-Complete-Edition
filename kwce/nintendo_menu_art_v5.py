"""Korean Nintendo Channel menu artwork, preserving native animations.

Only the Japanese fallback title panes/textures and icon language group are
changed. Dynamic news panes, texts, animations, and all other languages remain
byte-identical. The main wordmark has three syllables above five syllables.
"""
import hashlib
import struct

from .channels import ChannelArchive, compress_lz10, layout_sections, load_library, rebuild_layout
from .votes_visual import _materials, _textures
from .wiiroom_visual import _coverage
from . import tpl


# pane, matching reflected pane, glyph texture, text, horizontal position
ROWS = [
    ('P_J_mi_00', 'P_J_mi_01', 'tr_na_00.tpl', '모', -58),
    ('P_J_n_00', 'P_J_n_04', 'tr_nn_01.tpl', '두', 0),
    ('P_J_na_00', 'P_J_na_01', 'tr_no_00.tpl', '의', 58),
    ('P_J_ni_00', 'P_J_ni_01', 'tr_ni_00.tpl', '닌', -124),
    ('P_J_n_01', 'P_J_n_05', 'tr_nn_00.tpl', '텐', -62),
    ('P_J_te_00', 'P_J_te_01', 'tr_te_00.tpl', '도', 0),
    ('P_J_n_02', 'P_J_n_06', 'tr_do_00.tpl', '채', 62),
    ('P_J_do_00', 'P_J_do_01', 'tr_chi_00.tpl', '널', 124),
]


def mask_image(size, text, padding=2):
    from PIL import Image
    w, h = size
    mask, _ = _coverage(size, text, 0, (padding, padding, w-padding, h-padding))
    return Image.merge('RGBA', (mask, mask, mask, mask))


def banner_archive(before):
    path = 'arc/blyt/banner.brlyt'
    sections = layout_sections(before.get(path))
    matidx = next(i for i, s in enumerate(sections) if s[:4] == b'mat1')
    mat = bytearray(sections[matidx])
    materials = _materials(mat)
    textures = _textures(next(s for s in sections if s[:4] == b'txl1'))
    chosen = {n: (texture, x) for front, back, texture, _, x in ROWS for n in (front, back)}
    seen = set()
    for i, section in enumerate(sections):
        if section[:4] != b'pic1':
            continue
        name = section[12:28].split(b'\0')[0].decode('ascii')
        if not name.startswith('P_J_'):
            continue
        pane = bytearray(section)
        if name in chosen:
            texture, x = chosen[name]
            struct.pack_into('>f', pane, 0x24, float(x))
            struct.pack_into('>H', mat, materials[name] + 0x40, textures.index(texture))
            seen.add(name)
        else:
            pane[8] &= 0xfe
        sections[i] = bytes(pane)
    if seen != set(chosen):
        raise ValueError('Unexpected Japanese title panes')
    sections[matidx] = bytes(mat)
    archive = ChannelArchive(before.replace(path, rebuild_layout(before.get(path), sections)))
    for _, _, texture, glyph, _ in ROWS:
        name = 'arc/timg/' + texture
        old = archive.get(name)
        image = tpl.decode(old, 0)
        if image.size != (56, 56):
            raise ValueError('Unexpected title glyph dimensions')
        archive = ChannelArchive(archive.replace(name, tpl.encode(old, 0, mask_image(image.size, glyph, 5))))
    return archive


def icon_archive(before):
    path = 'arc/blyt/icon.brlyt'
    sections = layout_sections(before.get(path))
    hits = 0
    for i, section in enumerate(sections):
        if section[:4] == b'grp1' and section[8:24].split(b'\0')[0] == b'JPN':
            section = bytearray(section)
            section[8:24] = b'KOR' + bytes(13)
            sections[i] = bytes(section)
            hits += 1
    if hits != 1:
        raise ValueError('Expected one Japanese icon language group')
    archive = ChannelArchive(before.replace(path, rebuild_layout(before.get(path), sections)))
    name = 'arc/timg/oh_proLogo_J_00.tpl'
    original = archive.get(name)
    image = tpl.decode(original, 0)
    if image.size != (120, 32):
        raise ValueError('Unexpected icon title dimensions')
    return ChannelArchive(archive.replace(name, tpl.encode(original, 0, mask_image(image.size, '모두의 닌텐도 채널', 2))))


def korean_menu_art(content):
    load_library()
    from libWiiPy.archive import decompress_lz77
    outer = ChannelArchive(content[0x640:])
    prefix = bytearray(content[:0x640])
    result = []
    for kind, fn in [('banner', banner_archive), ('icon', icon_archive)]:
        name = f'meta/{kind}.bin'
        wrapped = outer.get(name)
        if wrapped[:4] != b'IMD5' or hashlib.md5(wrapped[32:]).digest() != wrapped[16:32]:
            raise ValueError('Invalid menu artwork wrapper')
        before = ChannelArchive(decompress_lz77(wrapped[32:]))
        archive = fn(before)
        if set(archive.files) != set(before.files):
            raise ValueError('Menu resource topology changed')
        if any(archive.get(p) != before.get(p) for p in archive.files if p.endswith('.brlan')):
            raise ValueError('Menu animation changed')
        if kind == 'icon':
            allowed = {'arc/blyt/icon.brlyt', 'arc/timg/oh_proLogo_J_00.tpl'}
        else:
            allowed = {'arc/blyt/banner.brlyt'} | {'arc/timg/' + row[2] for row in ROWS}
        if any(archive.get(p) != before.get(p) for p in archive.files if p not in allowed):
            raise ValueError('Unrelated menu content changed')
        raw = archive.compact()
        payload = b'LZ77' + compress_lz10(raw)
        if decompress_lz77(payload) != raw:
            raise ValueError('Menu artwork compression failed')
        new = b'IMD5' + len(payload).to_bytes(4, 'big') + bytes(8) + hashlib.md5(payload).digest() + payload
        outer = ChannelArchive(outer.replace(name, new))
        struct.pack_into('>I', prefix, 0x40 + (0x50 if kind == 'banner' else 0x4c), len(raw))
        result.append({'kind': kind, 'animation_preserved': True, 'size': len(raw)})
    prefix[0x630:0x640] = bytes(16)
    prefix[0x630:0x640] = hashlib.md5(prefix[0x40:0x640]).digest()
    return bytes(prefix) + outer.compact(), result

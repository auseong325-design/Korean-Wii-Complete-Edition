"""Korean Nintendo Channel wordmark using the US layout and animation tracks."""
import hashlib
import struct

from .channels import ChannelArchive, compress_lz10, layout_sections, load_library, rebuild_layout
from .votes_visual import _materials, _textures
from .wiiroom_visual import _coverage
from . import tpl

ROWS = [
    ('P_E_N_00', 'P_E_N_01', 'tr_na_00.tpl', '닌', -74),
    ('P_E_n_00', 'P_E_n_04', 'tr_nn_01.tpl', '텐', -39),
    ('P_E_e_00', 'P_E_e_02', 'tr_no_00.tpl', '도', -4),
    ('P_E_C_00', 'P_E_C_01', 'tr_ni_00.tpl', '채', 43),
    ('P_E_h_00', 'P_E_h_01', 'tr_nn_00.tpl', '널', 78),
]


def mask(size, text, bounds):
    from PIL import Image
    layer, _ = _coverage(size, text, 0, bounds)
    return Image.merge('RGBA', (layer, layer, layer, layer))


def swap_names(data, names, width):
    """Swap fixed-width NW4R identifiers, including group membership."""
    data = bytes(data)
    for index, (first, second) in enumerate(names):
        a, b = (n.encode('ascii').ljust(width, b'\0') for n in (first, second))
        marker = ('__KWCE_SWAP_%02d' % index).encode('ascii').ljust(width, b'\0')
        if len(a) != width or len(b) != width or marker in data:
            raise ValueError('Unsafe NW4R name swap')
        if data.count(a) != data.count(b):
            raise ValueError('Unequal title name references')
        data = data.replace(a, marker).replace(b, a).replace(marker, b)
    return data


def banner_archive(before):
    path = 'arc/blyt/banner.brlyt'
    sections = layout_sections(before.get(path))
    matidx = next(i for i, s in enumerate(sections) if s[:4] == b'mat1')
    materials = _materials(sections[matidx])
    textures = _textures(next(s for s in sections if s[:4] == b'txl1'))
    mat = bytearray(sections[matidx])
    chosen = {name: (texture, x) for front, back, texture, _, x in ROWS for name in (front, back)}
    found = set()
    for index, section in enumerate(sections):
        if section[:4] != b'pic1':
            continue
        name = section[12:28].split(b'\0')[0].decode('ascii')
        if not name.startswith('P_E_'):
            continue
        pane = bytearray(section)
        if name in chosen:
            texture, x = chosen[name]
            struct.pack_into('>f', pane, 0x24, float(x))
            struct.pack_into('>H', mat, materials[name] + 0x40, textures.index(texture))
            found.add(name)
        else:
            pane[8] &= 0xfe
        sections[index] = bytes(pane)
    if found != set(chosen):
        raise ValueError('US title panes missing')
    sections[matidx] = bytes(mat)
    layout = rebuild_layout(before.get(path), sections)
    # Korean falls back to the J parent. Redirect that name to the US parent,
    # and swap the reflected parent; child panes and animation curves remain US.
    parents = [('N_logoJ_00', 'N_logoE_00'), ('N_logoJS_00', 'N_logoES_00')]
    layout = swap_names(layout, parents, 16)
    archive = ChannelArchive(before.replace(path, layout))
    for _, _, texture, glyph, _ in ROWS:
        name = 'arc/timg/' + texture
        original = archive.get(name)
        image = tpl.decode(original, 0)
        if image.size != (56, 56):
            raise ValueError('Unexpected glyph resource')
        archive = ChannelArchive(archive.replace(name, tpl.encode(original, 0, mask(image.size, glyph, (6, 6, 50, 50)))))
    for name in [p for p in archive.files if p.endswith('.brlan')]:
        data = archive.get(name)
        patched = swap_names(data, [('N_logoJS_00', 'N_logoES_00')], 20)
        archive = ChannelArchive(archive.replace(name, patched))
    return archive


def icon_archive(before):
    from PIL import Image
    path = 'arc/blyt/icon.brlyt'
    sections = layout_sections(before.get(path))
    hits = set()
    for index, section in enumerate(sections):
        if section[:4] == b'grp1' and section[8:24].split(b'\0')[0] in (b'ENG', b'JPN'):
            section = bytearray(section)
            original_group = bytes(section[8:24].split(b'\0')[0])
            section[8:24] = (b'JPN' if original_group == b'ENG' else b'ENG') + bytes(13)
            sections[index] = bytes(section)
            hits.add(original_group)
    if hits != {b'ENG', b'JPN'}:
        raise ValueError('Expected US and fallback icon groups')
    layout = rebuild_layout(before.get(path), sections)
    panes = [('P_logoJ_00', 'P_logoE_00'), ('P_logoJ_01', 'P_logoE_01')]
    layout = swap_names(layout, panes, 16)
    archive = ChannelArchive(before.replace(path, layout))
    for anim in [p for p in archive.files if p.endswith('.brlan')]:
        archive = ChannelArchive(archive.replace(anim, swap_names(archive.get(anim), panes, 20)))
    name = 'arc/timg/oh_proLogo_E_00.tpl'
    original = archive.get(name)
    if tpl.decode(original, 0).size != (120, 32):
        raise ValueError('US icon title dimensions differ')
    # The US bitmap contains its own reflection at y=18..28.
    title = mask((120, 32), '닌텐도 채널', (3, 3, 117, 14))
    reflection = title.crop((0, 3, 120, 14)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    title.paste(reflection, (0, 18))
    return ChannelArchive(archive.replace(name, tpl.encode(original, 0, title)))


def korean_menu_art(content):
    load_library()
    from libWiiPy.archive import decompress_lz77
    outer = ChannelArchive(content[0x640:])
    prefix = bytearray(content[:0x640])
    records = []
    for kind, func in [('banner', banner_archive), ('icon', icon_archive)]:
        name = f'meta/{kind}.bin'
        wrapped = outer.get(name)
        if wrapped[:4] != b'IMD5' or hashlib.md5(wrapped[32:]).digest() != wrapped[16:32]:
            raise ValueError('Menu artwork integrity')
        before = ChannelArchive(decompress_lz77(wrapped[32:]))
        archive = func(before)
        allowed = (({'arc/blyt/icon.brlyt', 'arc/timg/oh_proLogo_E_00.tpl'} | {p for p in before.files if p.endswith('.brlan')}) if kind == 'icon' else
                   {'arc/blyt/banner.brlyt'} | {'arc/timg/' + r[2] for r in ROWS} |
                   {p for p in before.files if p.endswith('.brlan')})
        if set(archive.files) != set(before.files) or any(archive.get(p) != before.get(p) for p in before.files if p not in allowed):
            raise ValueError('Changes escaped US wordmark')
        raw = archive.compact()
        payload = b'LZ77' + compress_lz10(raw)
        if decompress_lz77(payload) != raw:
            raise ValueError('Menu artwork compression')
        wrapped = b'IMD5' + len(payload).to_bytes(4,'big') + bytes(8) + hashlib.md5(payload).digest() + payload
        outer = ChannelArchive(outer.replace(name, wrapped))
        struct.pack_into('>I', prefix, 0x40 + (0x50 if kind == 'banner' else 0x4c), len(raw))
        records.append({'kind': kind, 'us_layout_and_curves': True, 'size': len(raw)})
    prefix[0x630:0x640] = bytes(16)
    prefix[0x630:0x640] = hashlib.md5(prefix[0x40:0x640]).digest()
    return bytes(prefix) + outer.compact(), records

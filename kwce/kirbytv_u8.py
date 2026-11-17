"""Order-preserving U8 edits for Kirby TV contents.

Existing nodes keep their order and names; new files are appended to the end
of their (possibly new) directory, so lookups that walk the original tree see
the original entries first. Every original file payload is kept verbatim and
verified after rebuilding.
"""
import struct
from .channels import ChannelArchive

MAGIC = bytes.fromhex('55aa382d')


def _tree(data):
    root, header, start = struct.unpack_from('>III', data, 4)
    count = struct.unpack_from('>I', data, root + 8)[0]
    strings = root + count * 12
    nodes = []
    for index in range(count):
        word, value, size = struct.unpack_from('>III', data, root + 12 * index)
        at = strings + (word & 0xffffff)
        name = data[at:data.index(b'\0', at)].decode('ascii')
        nodes.append((word >> 24, name, value, size))

    def build(index, end):
        children = []
        i = index + 1
        while i < end:
            kind, name, value, size = nodes[i]
            if kind == 1:
                children.append([name, build(i, size)])
                i = size
            else:
                children.append([name, data[value:value + size]])
                i += 1
        return children
    return build(0, nodes[0][3])


def _serialize(children, reserved=bytes(16), pad_tail=False):
    nodes = [[1, 0, 0, 0]]
    names = bytearray(b'\0')
    files = []

    def walk(items, parent):
        for name, item in items:
            index = len(nodes)
            offset = len(names)
            names.extend(name.encode('ascii') + b'\0')
            if isinstance(item, list):
                nodes.append([1, offset, parent, 0])
                walk(item, index)
                nodes[index][3] = len(nodes)
            else:
                nodes.append([0, offset, 0, len(item)])
                files.append((index, item))
    walk(children, 0)
    nodes[0][3] = len(nodes)
    header = len(nodes) * 12 + len(names)
    start = (0x20 + header + 0x1f) & ~0x1f
    out = bytearray(start)
    for index, item in files:
        out.extend(bytes(-len(out) % 32))
        nodes[index][2] = len(out)
        out.extend(item)
    struct.pack_into('>IIII', out, 0, 0x55AA382D, 0x20, header, start)
    out[0x10:0x20] = reserved
    at = 0x20
    for kind, offset, value, size in nodes:
        struct.pack_into('>III', out, at, kind << 24 | offset, value, size)
        at += 12
    out[at:at + len(names)] = names
    if pad_tail:
        out.extend(bytes(-len(out) % 32))
    return bytes(out)


def edit(data, add=None, replace=None):
    """Return a U8 with `replace` {path: bytes} and appended `add` {path: bytes}.

    Paths are archive paths as ChannelArchive reports them (the virtual '.'
    directory is not part of the path).
    """
    add = dict(add or {})
    replace = dict(replace or {})
    original = ChannelArchive(data)
    for path in replace:
        if path not in original.files:
            raise ValueError('Replace target missing: ' + path)
    for path in add:
        if path in original.files:
            raise ValueError('Added path already exists: ' + path)
    tree = _tree(data)
    top = tree
    dot = len(tree) == 1 and tree[0][0] == '.' and isinstance(tree[0][1], list)
    if dot:
        top = tree[0][1]

    def visit(items, prefix):
        for entry in items:
            name, item = entry
            path = '/'.join(x for x in (prefix, name) if x)
            if isinstance(item, list):
                visit(item, path)
            elif path in replace:
                entry[1] = bytes(replace[path])
    visit(top, '')
    for path, payload in add.items():
        parts = path.split('/')
        items = top
        for part in parts[:-1]:
            found = next((e for e in items if e[0] == part and isinstance(e[1], list)), None)
            if found is None:
                found = [part, []]
                items.append(found)
            items = found[1]
        items.append([parts[-1], bytes(payload)])
    last_end = max(at + size for at, size in original.files.values())
    result = _serialize(tree, reserved=data[0x10:0x20], pad_tail=len(data) > last_end)
    checked = ChannelArchive(result)
    for path in original.files:
        expected = replace.get(path, original.get(path))
        if checked.get(path) != expected:
            raise ValueError('U8 rebuild changed ' + path)
    for path, payload in add.items():
        if checked.get(path) != payload:
            raise ValueError('U8 rebuild lost ' + path)
    if set(checked.files) != set(original.files) | set(add):
        raise ValueError('U8 file set differs')
    return result

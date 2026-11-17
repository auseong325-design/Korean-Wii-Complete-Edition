"""Strict SD boundary for the read-only key probe (public patch design v2, stage 2)."""
import hashlib
import json
from pathlib import Path

PATHS = {'apps/kwce-key-probe/boot.dol', 'apps/kwce-key-probe/meta.xml', 'KWCE-KEY-PROBE-ko.txt'}


def sd_files(package):
    package = Path(package).resolve()
    raw = (package/'package-manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != (package/'package-manifest.sha256').read_text().strip():
        raise ValueError('Key probe manifest mismatch')
    meta = json.loads(raw)
    if (meta.get('kind') != 'key-probe-v1' or meta.get('nand_write') is not False
            or meta.get('network') is not False or meta.get('key_output') is not False
            or meta.get('ios_reload') is not False):
        raise ValueError('Key probe scope mismatch')
    rows = meta['sd_files']
    if len(rows) != len(PATHS) or {r['path'] for r in rows} != PATHS:
        raise ValueError('Unexpected key probe payload')
    result = []
    for row in rows:
        path = package/row['path']
        if path.is_symlink() or not path.resolve().is_relative_to(package):
            raise ValueError('Key probe payload escapes package')
        data = path.read_bytes()
        if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Key probe payload mismatch')
        result.append((path, row['path']))
    result.append((package/'package-manifest.json', 'KWCE-KEY-PROBE-manifest.json'))
    return meta, result

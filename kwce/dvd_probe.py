"""Strict SD boundary for the standalone physical DVD read probe."""
import hashlib
import json
from pathlib import Path

PATHS = {'apps/kwce-dvd-probe/boot.dol', 'apps/kwce-dvd-probe/meta.xml',
         'KWCE-DVD-PROBE-ko.txt'}


def sd_files(package):
    package = Path(package).resolve()
    raw = (package/'package-manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != (package/'package-manifest.sha256').read_text().strip():
        raise ValueError('DVD probe manifest mismatch')
    meta = json.loads(raw)
    if (meta.get('kind') != 'dvd-read-probe-v1' or meta.get('nand_write') is not False
            or meta.get('network') is not False or meta.get('content_logging') is not False
            or meta.get('ios_reload') is not False):
        raise ValueError('DVD probe scope mismatch')
    rows = meta['sd_files']
    if len(rows) != len(PATHS) or {r['path'] for r in rows} != PATHS:
        raise ValueError('Unexpected DVD probe payload')
    result = []
    for row in rows:
        path = package/row['path']
        if path.is_symlink() or not path.resolve().is_relative_to(package):
            raise ValueError('DVD probe payload escapes package')
        data = path.read_bytes()
        if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('DVD probe payload mismatch')
        result.append((path, row['path']))
    result.append((package/'package-manifest.json', 'KWCE-DVD-PROBE-manifest.json'))
    return meta, result

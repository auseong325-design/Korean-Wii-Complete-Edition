"""Strict SD payload boundary for the read-only News diagnostic."""
import hashlib
import json
from pathlib import Path

ALLOWED = {'apps/kwce-news-network/boot.dol', 'apps/kwce-news-network/meta.xml',
           'KWCE-NEWS-NETWORK-README-ko.txt'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sd_files(package):
    package = Path(package).resolve()
    raw = (package / 'package-manifest.json').read_bytes()
    if digest(raw) != (package / 'package-manifest.sha256').read_text().strip():
        raise ValueError('Diagnostic manifest mismatch')
    meta = json.loads(raw)
    if (meta.get('kind') != 'news-network-diagnostic-v1' or
            meta.get('nand_write') or meta.get('console_identifiers') or meta.get('wad_included')):
        raise ValueError('Diagnostic scope mismatch')
    rows = meta['sd_files']
    if len(rows) != len(ALLOWED) or {row['path'] for row in rows} != ALLOWED:
        raise ValueError('Unexpected diagnostic payload')
    files = []
    for row in rows:
        path = package / row['path']
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(package):
            raise ValueError('Diagnostic payload escapes package')
        raw = path.read_bytes()
        if len(raw) != row['bytes'] or digest(raw) != row['sha256']:
            raise ValueError('Diagnostic payload mismatch')
        files.append((path, row['path']))
    files.append((package / 'package-manifest.json', 'KWCE-NEWS-NETWORK-manifest.json'))
    return meta, files

"""Strict payload boundary for an isolated, channel-only News trace package."""
import hashlib
import json
from pathlib import Path

ALLOWED = {'apps/kwce-news-trace/boot.dol', 'apps/kwce-news-trace/meta.xml',
           'apps/kwce-news-trace/icon.png', 'kwce-news-trace/packages.txt',
           'kwce-news-trace/trace/korean.wad', 'kwce-news-trace/return/korean.wad',
           'KWCE-NEWS-TRACE-README-ko.txt'}


def sha(data): return hashlib.sha256(data).hexdigest()


def sd_files(package):
    package = Path(package).resolve();raw = (package / 'package-manifest.json').read_bytes()
    if sha(raw) != (package / 'package-manifest.sha256').read_text().strip():
        raise ValueError('Trace manifest mismatch')
    meta = json.loads(raw)
    if (meta.get('kind') != 'news-branch-trace-v1' or meta.get('title_id') != '0001000248414745'
            or meta.get('production') or meta.get('menu_writer_linked') or meta.get('hardware_tested')):
        raise ValueError('Trace package scope mismatch')
    rows = meta['sd_files']
    if len(rows) != len(ALLOWED) or {row['path'] for row in rows} != ALLOWED:
        raise ValueError('Trace payload paths mismatch')
    files = []
    for row in rows:
        path = package / row['path']
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(package):
            raise ValueError('Trace payload escapes package')
        data = path.read_bytes()
        if len(data) != row['bytes'] or sha(data) != row['sha256']:
            raise ValueError('Trace payload mismatch')
        files.append((path, row['path']))
    files.append((package / 'package-manifest.json', 'KWCE-NEWS-TRACE-manifest.json'))
    return meta, files

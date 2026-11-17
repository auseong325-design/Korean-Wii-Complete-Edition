"""Immutable, official Account Linker packages: strict non-console SD payload.

Package numbers map to upstream pins; earlier packages stay verifiable.
  sd-v1: Account Linker 2.1.0 (configs/account-linker-v1.lock.json)
  sd-v2: Account Linker 2.2.0 (configs/account-linker-v2.lock.json; new OAuth client ID)
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {'apps/wiilink-account-linker/boot.dol', 'apps/wiilink-account-linker/icon.png',
           'apps/wiilink-account-linker/meta.xml', 'apps/wiilink-account-linker/LICENSE',
           'apps/wiilink-account-linker/SOURCE.txt', 'apps/wiilink-account-linker/source.zip',
           'KWCE-ACCOUNT-LINKER-README-ko.txt'}
# package number -> (manifest kind, upstream version, lock file)
VERSIONS = {
    1: ('official-account-linker-v1', '2.1.0', 'configs/account-linker-v1.lock.json'),
    2: ('official-account-linker-v2', '2.2.0', 'configs/account-linker-v2.lock.json'),
}
CURRENT = 2


def sha(data): return hashlib.sha256(data).hexdigest()


def lock(number):
    kind, version, path = VERSIONS[number]
    data = json.loads((ROOT / path).read_text(encoding='utf-8'))
    if data['version'] != version:
        raise ValueError('Account Linker lock version differs')
    return data


def sd_files(package):
    package = Path(package).resolve()
    raw = (package / 'package-manifest.json').read_bytes()
    if sha(raw) != (package / 'package-manifest.sha256').read_text(encoding='ascii').strip():
        raise ValueError('Account Linker manifest hash differs')
    record = json.loads(raw)
    number = next((n for n, (kind, version, _) in VERSIONS.items()
                   if record.get('kind') == kind and record.get('version') == version), None)
    if number is None or record.get('modified_upstream_binary') or record.get('hardware_verified'):
        raise ValueError('Account Linker scope differs')
    pin = lock(number)
    if record.get('release_archive_sha256') != pin['archive_sha256'] or record.get('source_commit') != pin['source_commit']:
        raise ValueError('Account Linker upstream pin differs')
    rows = record['sd_files']
    if len(rows) != len(ALLOWED) or {r['path'] for r in rows} != ALLOWED:
        raise ValueError('Account Linker payload paths differ')
    result = []
    for row in rows:
        p = package / row['path']
        if p.is_symlink() or p.is_junction() or not p.resolve().is_relative_to(package):
            raise ValueError('Account Linker payload escapes package')
        data = p.read_bytes()
        if len(data) != row['bytes'] or sha(data) != row['sha256']:
            raise ValueError('Account Linker payload changed')
        prefix = 'apps/wiilink-account-linker/'
        if row['path'].startswith(prefix) and row['path'][len(prefix):] in pin['payload_sha256']:
            if sha(data) != pin['payload_sha256'][row['path'][len(prefix):]]:
                raise ValueError('Account Linker upstream binary differs')
        result.append((p, row['path']))
    result.append((package / 'package-manifest.json', 'KWCE-ACCOUNT-LINKER-manifest.json'))
    return record, result

"""Strict payload boundary for read-only disc/Priiloader diagnostic."""
import hashlib,json
from pathlib import Path
ALLOWED={'apps/kwce-disc-diagnostic/boot.dol','apps/kwce-disc-diagnostic/meta.xml','KWCE-DISC-DIAGNOSTIC-README-ko.txt'}
def sd_files(package):
    package=Path(package).resolve();raw=(package/'package-manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=(package/'package-manifest.sha256').read_text().strip():raise ValueError('Diagnostic manifest mismatch')
    meta=json.loads(raw)
    if meta.get('kind')!='disc-diagnostic-v1' or meta.get('nand_write') or meta.get('console_identifiers') or meta.get('wad_included'):raise ValueError('Diagnostic scope mismatch')
    rows=meta['sd_files']
    if len(rows)!=len(ALLOWED) or {r['path'] for r in rows}!=ALLOWED:raise ValueError('Unexpected diagnostic payload')
    result=[]
    for row in rows:
        path=package/row['path']
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(package):raise ValueError('Diagnostic payload escapes package')
        data=path.read_bytes()
        if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('Diagnostic payload mismatch')
        result.append((path,row['path']))
    result.append((package/'package-manifest.json','KWCE-DISC-DIAGNOSTIC-manifest.json'))
    return meta,result

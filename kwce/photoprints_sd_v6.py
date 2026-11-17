"""Strict SD boundary for the Photo Prints Korean-region trial."""
import hashlib
import json
from pathlib import Path
from .channels import load_library

WAD = 'WAD/KWCE-photo-r6/Photo-Prints-r6.wad'
README = 'KWCE-PHOTO-R6-README-ko.txt'
MANIFEST = 'KWCE-PHOTO-R6-manifest.json'

def sha(b): return hashlib.sha256(b).hexdigest()

def sd_files(package):
    package = Path(package).resolve()
    raw = (package/'package-manifest.json').read_bytes()
    if sha(raw) != (package/'package-manifest.sha256').read_text(encoding='ascii').strip():
        raise ValueError('Photo package manifest mismatch')
    manifest = json.loads(raw)
    if manifest.get('kind') != 'photo-region-trial-v6' or {x['path'] for x in manifest['sd_files']} != {WAD, README} or len(manifest['sd_files']) != 2:
        raise ValueError('Unexpected package scope')
    result = []
    for row in manifest['sd_files']:
        p = package/row['path']
        if not p.resolve().is_relative_to(package) or p.is_symlink() or p.is_junction(): raise ValueError('Indirect source path')
        data = p.read_bytes()
        if len(data) != row['bytes'] or sha(data) != row['sha256']: raise ValueError('Payload hash mismatch')
        if row['path'] == WAD:
            t=load_library().title.Title(); t.load_wad(data)
            if t.tmd.title_id.lower() != '000100014843444a' or t.tmd.region != 4 or not t.get_is_fakesigned(): raise ValueError('Unexpected Photo Prints title')
            for i in range(len(t.tmd.content_records)): t.get_content_by_index(i)
        result.append((p,row['path']))
    result.append((package/'package-manifest.json',MANIFEST))
    return manifest,result

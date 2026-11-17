"""Six individually verified, Wii-only channel candidates for the user's SD."""
import hashlib
import json
from pathlib import Path

from .channels import load_library
from .hardware import local_reference_counts

ROWS = (
    ('personal-data', 2, '000100084843434a', '01-Personal-Data-v2.wad'),
    ('internet', 5, '0001000148414445', '02-Internet-v5.wad'),
    ('kirbytv', 3, '0001000148434d50', '03-Kirby-TV-v3.wad'),
    ('photoprints', 5, '000100014843444a', '04-Photo-Prints-v5.wad'),
    ('food', 4, '000100014843484a', '05-Food-v4.wad'),
    ('wiispeak', 1, '000100014843464b', '06-Wii-Speak-v1.wad'),
)
DATA = 'wad/KWCE-remaining-v1'
README = 'KWCE-REMAINING-README-ko.txt'
MANIFEST = 'KWCE-REMAINING-manifest.json'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def sd_files(package):
    package = Path(package).resolve()
    raw = (package / 'package-manifest.json').read_bytes()
    if sha(raw) != (package / 'package-manifest.sha256').read_text(encoding='ascii').strip():
        raise ValueError('Manifest digest differs')
    record = json.loads(raw)
    if record.get('kind') != 'remaining-six-wii-channels-v1' or record.get('system_title_included'):
        raise ValueError('Package scope differs')
    expected = {f'{DATA}/{row[3]}' for row in ROWS} | {README}
    if len(record['sd_files']) != len(expected) or {x['path'] for x in record['sd_files']} != expected:
        raise ValueError('Unexpected file list')
    lib = load_library()
    result = []
    for item in record['sd_files']:
        path = package / item['path']
        if not path.resolve().is_relative_to(package) or path.is_symlink() or path.is_junction():
            raise ValueError('Package path escapes root')
        data = path.read_bytes()
        if len(data) != item['bytes'] or sha(data) != item['sha256']:
            raise ValueError('Package file hash differs')
        if item['path'] != README:
            tid = next(row[2] for row in ROWS if item['path'] == f'{DATA}/{row[3]}')
            t = lib.title.Title()
            t.load_wad(data)
            if t.tmd.title_id.lower() != tid or not t.get_is_fakesigned():
                raise ValueError('Unexpected title or signature state')
            for i in range(len(t.tmd.content_records)):
                t.get_content_by_index(i)
            if local_reference_counts(t) != item['local_reference_counts']:
                raise ValueError('Local references differ from reviewed candidate')
        result.append((path, item['path']))
    result.append((package / 'package-manifest.json', MANIFEST))
    return record, result

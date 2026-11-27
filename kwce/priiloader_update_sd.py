"""SD package: Priiloader 0.10.0 installer app + the card's active hacks file made 0.10-safe.

Only the Priiloader installer app on the SD changes (apps/Priiloader/boot.dol, META.XML, icon.png
from the official 0.10.0 release zip). The console's installed Priiloader changes only when the
owner runs that app on the Wii. The active apps/Priiloader/hacks_hash.ini keeps every section of
the card's current file; only the KWCE sections are re-split with neutral_fragment so Priiloader
0.8.2 and 0.10 read the same bytes (0.8.2 bytes unchanged). The 0.10 default hacks list is not
copied. build() records the card's pre-update hashes; verify_card() refuses a card that changed
since then.
"""
import hashlib, json, re, subprocess, sys, zipfile
from pathlib import Path
from kwce.priiloader_profile import neutral_fragment, KWCE_SECTION, legacy_bytes, modern_bytes

ZIP_SHA256 = '312881836bc62ae55d496a9caef987d19493f635e26079bc60ecde08a2a31c1d'
ZIP_URL = 'https://github.com/DacoTaco/priiloader/releases/download/0.10.0/Priiloader_v0_10.zip'
APP = 'apps/Priiloader'
FROM_ZIP = {'boot.dol': 'apps/priiloader/boot.dol', 'META.XML': 'apps/priiloader/META.XML',
            'icon.png': 'apps/priiloader/icon.png'}
HACKS = f'{APP}/hacks_hash.ini'
KIND = 'kwce-priiloader-0.10.0-sd'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _meta(raw):
    text = raw.decode('utf-8', 'replace')
    get = lambda tag: (re.search(f'<{tag}>([^<]*)</{tag}>', text) or [None, None])[1]
    return dict(name=get('name'), version=get('version'), release_date=get('release_date'))


def neutral_kwce(raw):
    """Re-split only KWCE sections; other sections stay byte for byte."""
    crlf = b'\r\n' in raw
    text = raw.decode('latin1').replace('\r\n', '\n')
    out = KWCE_SECTION.sub(lambda m: neutral_fragment(m.group(0)), text)
    return (out.replace('\n', '\r\n') if crlf else out).encode('latin1')


def _pairs(raw, conv):
    rows = []
    for line in raw.decode('latin1').replace('\r\n', '\n').split('\n'):
        key, eq, value = line.partition('=')
        if eq and key in ('hash', 'patch'):
            rows.append(b''.join(conv(t) for t in value.split(',')))
    return rows


def build(zip_path, card, out):
    zip_path, card, out = Path(zip_path), Path(card), Path(out)
    if out.exists():
        raise ValueError('Package number already used')
    if sha(zip_path.read_bytes()) != ZIP_SHA256:
        raise ValueError('Release zip hash mismatch')
    z = zipfile.ZipFile(zip_path)
    files = {f'{APP}/{name}': z.read(member) for name, member in FROM_ZIP.items()}
    if _meta(files[f'{APP}/META.XML'])['version'] != '0.10.0':
        raise ValueError('Unexpected release version')
    before = {rel: sha((card / rel).read_bytes()) for rel in [*files, HACKS] if (card / rel).is_file()}
    old = (card / HACKS).read_bytes()
    new = neutral_kwce(old)
    if _pairs(new, legacy_bytes) != _pairs(old, legacy_bytes) or _pairs(new, legacy_bytes) != _pairs(new, modern_bytes):
        raise ValueError('Neutral hacks file changed 0.8.2 bytes or differs under 0.10')
    files[HACKS] = new
    for rel, data in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    manifest = dict(kind=KIND, nand_write=False, console_executed=False, source_zip=ZIP_URL, source_zip_sha256=ZIP_SHA256,
                    previous_app=_meta((card / f'{APP}/META.XML').read_bytes()), new_app=_meta(files[f'{APP}/META.XML']),
                    expected_inputs=before, files={rel: sha(d) for rel, d in files.items()})
    raw = json.dumps(manifest, indent=2, ensure_ascii=False).encode('utf-8')
    (out / 'package-manifest.json').write_bytes(raw)
    (out / 'package-manifest.sha256').write_text(sha(raw) + '\n')
    return manifest


def sd_files(package):
    package = Path(package)
    raw = (package / 'package-manifest.json').read_bytes()
    if sha(raw) != (package / 'package-manifest.sha256').read_text().strip():
        raise ValueError('Priiloader package manifest mismatch')
    m = json.loads(raw)
    if m.get('kind') != KIND or m.get('nand_write') is not False or set(m['files']) != {*(f'{APP}/{n}' for n in FROM_ZIP), HACKS}:
        raise ValueError('Priiloader package scope mismatch')
    for rel, h in m['files'].items():
        if sha((package / rel).read_bytes()) != h:
            raise ValueError('Priiloader package file changed')
    return m, [(package / rel, rel) for rel in sorted(m['files'])]


def verify_card(package, card):
    m, _ = sd_files(package)
    card = Path(card)
    if sys.platform == 'win32':
        label = subprocess.check_output(['powershell.exe', '-NoProfile', '-Command',
                                         f"(Get-Volume -DriveLetter {str(card)[0]}).FileSystemLabel"], text=True).strip()
    else:
        label = Path(card).name
    if label.casefold() != 'wii':
        raise ValueError('Card is not the wii volume')
    for rel, h in m['expected_inputs'].items():
        if sha((card / rel).read_bytes()) != h:
            raise ValueError('SD changed since Priiloader package review')
    return m

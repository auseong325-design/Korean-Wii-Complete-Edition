"""Channel-only installer/package boundary. Never creates a System Menu writer."""
import hashlib,json,re
from pathlib import Path
from .dvd_hardware import installer_source as dvd_source

APP='apps/kwce-installer'
DATA='kwce'
README='KWCE-README-ko.txt'
MANIFEST='KWCE-CHANNELS-package-manifest.json'
IDS={'forecast','news','wiiroom','mii-contest','tvguide'}
def sha(data):return hashlib.sha256(data).hexdigest()

def installer_source(original,rows):
    tids=[r['title_id']for r in rows]
    if len(set(tids))!=len(tids)or any(not re.fullmatch(r'0001000[12][0-9a-f]{8}',t)for t in tids):raise ValueError('Only distinct channel titles')
    source=dvd_source(original,27)
    source=source.replace('#define BASE "sd:/kwce-dvd-test"','#define BASE "sd:/kwce"').replace('0.3-dvd-r27','0.4-channels-v1')
    anchor='    if (tid != 0x000100014b445644ULL) return 0; /* DVD only */'
    if source.count(anchor)!=1:raise ValueError('Installer channel allowlist anchor differs')
    source=source.replace(anchor,'    if ('+' && '.join('tid != 0x'+t+'ULL'for t in tids)+') return 0; /* fixed channel allowlist */')
    source=source.replace('original (WiiLink English)', 'original channel').replace('the original (WiiLink English) channel', 'the original channel')
    source=source.replace('This DVD build has no emulator override.','This channel-only build has no emulator override.')
    if any(x in source for x in ['menu_install(', 'menu_restore(', 'menu_available(', 'allow-current-ios.txt']):raise ValueError('Unexpected menu writer/test override')
    return source

def sd_files(package):
    package=Path(package).resolve();raw=(package/'package-manifest.json').read_bytes()
    if sha(raw)!=(package/'package-manifest.sha256').read_text().strip():raise ValueError('Channel package manifest differs')
    record=json.loads(raw)
    if record.get('kind')!='channel-only-v1'or set(r['id']for r in record['channels'])!=IDS:raise ValueError('Channel package scope differs')
    if record.get('menu_writer_linked')or record.get('priiloader_update')or record.get('iso_included'):raise ValueError('Channel package contains unrelated operations')
    allowed={f'{APP}/{n}'for n in ['boot.dol','meta.xml','icon.png']}|{f'{DATA}/packages.txt',README}
    for row in record['channels']:
        if not re.fullmatch(r'0001000[12][0-9a-f]{8}',row['title_id']):raise ValueError('Not a channel title')
        allowed.update(f'{DATA}/{row["id"]}/{n}.wad'for n in ['korean','original'])
    if len(record['sd_files'])!=len(allowed)or {x['path']for x in record['sd_files']}!=allowed:raise ValueError('Unexpected channel SD file')
    result=[]
    for item in record['sd_files']:
        p=package/item['path']
        if not p.resolve().is_relative_to(package)or p.is_symlink()or p.is_junction():raise ValueError('Channel source escapes package')
        if p.stat().st_size!=item['bytes']or sha(p.read_bytes())!=item['sha256']:raise ValueError('Channel package payload differs')
        result.append((p,item['path']))
    result.append((package/'package-manifest.json',MANIFEST))
    return record,result

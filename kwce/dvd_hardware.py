"""DVD-only hardware package guards; no console operations in this module."""
import hashlib,json,re
from pathlib import Path

APP='apps/kwce-dvd-installer'
DATA='kwce-dvd-test'
README='KWCE-DVD-README-ko.txt'
MANIFEST='KWCE-DVD-package-manifest.json'
TITLE='000100014b445644'

def sha(data):return hashlib.sha256(data).hexdigest()

def installer_source(original,revision=19):
    """Derive the channel installer without linking the menu resource writer."""
    def replace(old,new):
        nonlocal original
        if original.count(old)!=1:raise ValueError('DVD installer source anchor differs')
        original=original.replace(old,new)
    replace('#define BASE "sd:/kwce"','#define BASE "sd:/kwce-dvd-test"')
    replace('#define VERSION "0.2-alpha"','#define VERSION "0.3-dvd-r19"')
    replace('static int menu_row = -1;          /* index of the System Menu resource row, or -1 */\nstatic const char *menu_status = "";\n','')
    replace('static int allowed_tid(u64 tid)\n{','static int allowed_tid(u64 tid)\n{\n    if (tid != 0x000100014b445644ULL) return 0; /* DVD only */')
    a=original.index('    if (menu_row >= 0)\n');b=original.index('    printf("\\n  Up/Down',a)
    original=original[:a]+original[b:]
    a=original.index('    if (!cios_ok) {\n');b=original.index('    if (load_packages()',a)
    original=original[:a]+'''    if (!cios_ok) {
        say("\\n  cIOS 249 (d2x) could not be loaded. Nothing was changed.\\n");
        wait_any(); return 0;
    }
'''+original[b:]
    a=original.index('    if (ISFS_Initialize() >= 0 && menu_available())');b=original.index('    int sel = 0;',a)
    original=original[:a]+'    int rows = npkg;\n'+original[b:]
    a=original.index('            if (sel == menu_row) {');b=original.index('            else do_restore(&pkgs[sel]);',a)
    original=original[:a]+'            if (k == K_INSTALL) do_install(&pkgs[sel]);\n'+original[b:]
    original=original.replace('fails (sd:/kwce/allow-current-ios.txt overrides this for emulator tests).','fails. This DVD build has no emulator override.')
    if any(x in original for x in ['menu_row','menu_available(', 'menu_install(', 'menu_restore(', 'allow-current-ios.txt']):
        raise ValueError('DVD installer still has a menu or emulator entry point')
    if revision not in (19,20,21,24,25,26,27):raise ValueError("Unreviewed DVD player revision")
    original=original.replace('#define VERSION "0.3-dvd-r19"',f'#define VERSION "0.3-dvd-r{revision}"')
    return '/* DVD-only derived installer: generated from the reviewed KWCE channel installer. */\n'+original

def merge_hacks(current,dvd):
    from .priiloader_hacks import legacy_sections,DVD_GROUP
    text=current.decode('latin1').replace('\r\n','\n')
    _,dropped=legacy_sections(text)
    if dropped:raise ValueError('Existing Priiloader has unsupported sections; preserving it unchanged')
    new=dvd.decode('ascii').replace('\r\n','\n')
    _,dropped=legacy_sections(new)
    if dropped or re.findall(r'^\[([^]]+)\]',new,re.M)!=[DVD_GROUP]:raise ValueError('Expected one DVD-only hack')
    text=re.sub(r'^\['+re.escape(DVD_GROUP)+r'\]\n.*?(?=^\[|\Z)','',text,flags=re.M|re.S)
    prefix=text.rstrip('\n')
    merged=((prefix+'\n'if prefix else'')+new).replace('\n','\r\n').encode('latin1')
    from .priiloader_legacy import parse
    parse(merged)
    return merged

def sd_files(package):
    """Verify the complete immutable SD payload, including its manifest sidecar."""
    package=Path(package).resolve()
    raw=(package/'package-manifest.json').read_bytes()
    if sha(raw)!=(package/'package-manifest.sha256').read_text().strip():raise ValueError('DVD package manifest differs')
    record=json.loads(raw)
    if record.get('kind')not in {'dvd-only-r19','dvd-only-r20','dvd-only-r21','dvd-only-r24','dvd-only-r25','dvd-only-r26','dvd-only-r27'} or record.get('title_id')!=TITLE:raise ValueError('Unknown DVD package type')
    allowed={f'{APP}/boot.dol',f'{APP}/meta.xml',f'{APP}/icon.png',f'{DATA}/packages.txt',f'{DATA}/dvd-player/korean.wad',README}
    if {r['path']for r in record['sd_files']}!=allowed or len(record['sd_files'])!=len(allowed):raise ValueError('DVD SD payload scope differs')
    plan=[]
    for item in record['sd_files']:
        p=package/item['path']
        if not p.resolve().is_relative_to(package) or p.is_symlink() or p.is_junction():raise ValueError('DVD source path escapes package')
        if p.stat().st_size!=item['bytes'] or sha(p.read_bytes())!=item['sha256']:raise ValueError('DVD SD file differs')
        plan.append((p,item['path']))
    hack=package/'priiloader/kwce-hacks.ini'
    if sha(hack.read_bytes())!=record['priiloader_sha256']:raise ValueError('DVD hack differs')
    merge_hacks(b'',hack.read_bytes())
    plan.append((package/'package-manifest.json',MANIFEST))
    return record,plan

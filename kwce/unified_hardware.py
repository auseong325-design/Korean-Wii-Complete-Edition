"""Reproducible, channel-only installer and SD update boundaries."""
import hashlib,json,re
from pathlib import Path
from .channel_hardware import installer_source

ROWS=[('forecast','0001000248414645','Forecast r103',0),('news','0001000248414745','News r20',0),('wiiroom','000100014843494a','Wii Room r51',0),('mii-contest','0001000148415045','Mii Contest r25',0),('tvguide','0001000148424e4a','TV Guide r8 trial',1),('votes','0001000148414a45','Everybody Votes r17',0),('nintendo','0001000148415445','Nintendo r4 trial',1),('dvd-player','000100014b445644','DVD Player r27',0)]
APP_DIRS=('apps/kwce-installer','apps/kwce-wiiroom-installer','apps/kwce-dvd-installer')
UPSTREAM={'CleanRip-v2.4.zip':'95e02c5e5d4c06334853d0f46a412634059c083fe73a5a35e48f5b2de82db8a5','mupen64-20260410.zip':'168f32b9fd659cae1bdca218afc6fdb4050fb73737c0e05954d3c1c757e68560','usbloadergx_r1283.zip':'83e3fa9e18fd715c9617125d674b4b965eddff2ee8c54f11394c0bbc04a421a2','VisualBoyAdvanceGX-3.0.4-Wii.zip':'f5e9a4df170b4ee6fd1d5cfa783a48986c184dedd7ca7e5fca6731705fd9b363'}
def sha(data):return hashlib.sha256(data).hexdigest()

def source(original):
    s=installer_source(original,[{'title_id':r[1]} for r in ROWS]).replace('0.4-channels-v1','0.5-unified-v1')
    def sub(old,new):
        nonlocal s
        if s.count(old)!=1:raise ValueError('Unified source anchor differs')
        s=s.replace(old,new)
    sub('u32 w = WPAD_ButtonsDown(0);','u32 w = 0;\n        for (int i = 0; i < 4; i++) w |= WPAD_ButtonsDown(i);')
    sub('    snprintf(out, n, BASE "/state/%s.txt", p->id);','    if (!strcmp(p->id, "dvd-player")) snprintf(out, n, "sd:/kwce-dvd-test/state/dvd-player.txt");\n    else snprintf(out, n, BASE "/state/%s.txt", p->id);')
    sub('    mkdir(BASE "/state", 0777);','    mkdir(BASE "/state", 0777);\n    if (!strcmp(p->id, "dvd-player")) mkdir("sd:/kwce-dvd-test/state", 0777);')
    sub('    snprintf(out, n, BASE "/%s/%s.wad", p->id, kind);','    if (!strcmp(p->id, "dvd-player")) snprintf(out, n, "sd:/kwce-dvd-test/dvd-player/%s.wad", kind);\n    else snprintf(out, n, BASE "/%s/%s.wad", p->id, kind);')
    anchor='        p->tid = strtoull(field[1], NULL, 16);'
    conditions=' || '.join(f'(!strcmp(p->id,"{i}") && p->tid == 0x{t}ULL)' for i,t,_,_ in ROWS)
    sub(anchor,anchor+'\n        if (!('+conditions+')) { say("  Unknown channel entry; skipped.\\n"); continue; }')
    sub('    printf("\\n  Up/Down select   1 (GC X): install Korean   2 (GC Y): restore\\n");','    printf("\\n  Up/Down: select channel   A: actions   HOME: exit\\n");\n    printf("  Shortcuts: 1 install, 2 restore. B cancels.\\n");')
    anchor='        else if (k == K_INSTALL || k == K_RESTORE) {'
    sub(anchor,'''        else if (k == K_A) {
            say("\\n  %s: UP install / DOWN restore / B cancel\\n", pkgs[sel].name);
            int action = 0;
            for (;;) {
                say("  Selected: %s (A confirms, B cancels)\\n", action ? "Restore" : "Install");
                int a = read_key();
                if (a == K_UP) action = 0;
                else if (a == K_DOWN) action = 1;
                else if (a == K_A) { if (action) do_restore(&pkgs[sel]); else do_install(&pkgs[sel]); break; }
                else if (a == K_B || a == K_EXIT) break;
            }
        }
'''+anchor)
    if any(x in s for x in ['menu_install(', 'menu_restore(', 'allow-current-ios.txt']):raise ValueError('Unexpected privileged/test entry point')
    return s

def allowed(path):
    if path in {f'{d}/{n}' for d in APP_DIRS for n in ('boot.dol','meta.xml','icon.png')}:return True
    if path in {'kwce/packages.txt','kwce/news/korean.wad','KWCE-UNIFIED-README-ko.txt'}:return True
    if path in {f'apps/{d}/{n}' for d in ('CleanRip','vbagx') for n in ('boot.dol','icon.png','meta.xml')}:return True
    if path in {f'apps/usbloader_gx/{n}' for n in ('boot.dol','icon.png','meta.xml')}:return True
    if re.fullmatch(r'apps/usbloader_gx/language/[a-z]+\.lang',path):return True
    if re.fullmatch(r'apps/not64/(boot\.dol|not64\.dol|data\.iso|icon\.png|meta\.xml|LICENCE\.txt|licences/[A-Za-z0-9_-]+\.txt)',path):return True
    return False

def verify_card(card,root):
    """Refuse a partial/unknown existing card; check payloads without printing them."""
    card=Path(card);base=Path(root)/'workspace/hardware'
    groups={'forecast':'kwce-channels-v1','mii-contest':'kwce-channels-v1','tvguide':'kwce-channels-v1','votes':'kwce-alpha-v7','nintendo':'kwce-alpha-v7'}
    for channel,package in groups.items():
        for kind in ('korean','original'):
            rel=Path('kwce')/channel/(kind+'.wad');a=card/rel;b=base/package/rel
            if not a.is_file() or not b.is_file() or sha(a.read_bytes())!=sha(b.read_bytes()):raise ValueError('Existing channel package differs: '+channel)
    for channel in ('news','wiiroom'):
        korean=Path('kwce')/channel/'korean.wad';original=Path('kwce')/channel/'original.wad'
        for rel,package in ((korean,'kwce-loading-news20-room51-v1'),(original,'kwce-channels-v1')):
            a=card/rel;b=base/package/rel
            candidates=[b]
            if channel=='news' and rel==korean:candidates.append(base/'kwce-unified-sd-v2'/rel)
            if not a.is_file() or not any(p.is_file() and sha(a.read_bytes())==sha(p.read_bytes()) for p in candidates):raise ValueError('Existing channel package differs: '+channel)
    dvd=Path('kwce-dvd-test/dvd-player/korean.wad');a=card/dvd;b=base/'kwce-dvd-r27-v1'/dvd
    if not a.is_file() or not b.is_file() or sha(a.read_bytes())!=sha(b.read_bytes()):raise ValueError('Existing DVD package differs')

def sd_files(package):
    package=Path(package).resolve(); raw=(package/'package-manifest.json').read_bytes()
    if sha(raw)!=(package/'package-manifest.sha256').read_text().strip():raise ValueError('Unified manifest differs')
    record=json.loads(raw)
    if record.get('kind')!='unified-homebrew-v1' or record.get('menu_writer_linked') or record.get('priiloader_update'):raise ValueError('Package scope differs')
    result=[]; seen=set()
    for item in record['sd_files']:
        name=item['path'];p=package/name
        if name in seen or not allowed(name) or not p.resolve().is_relative_to(package) or p.is_symlink() or p.is_junction():raise ValueError('Unexpected package path')
        if p.stat().st_size!=item['bytes'] or sha(p.read_bytes())!=item['sha256']:raise ValueError('Payload differs')
        seen.add(name);result.append((p,name))
    if not {f'{d}/boot.dol' for d in APP_DIRS}.issubset(seen) or 'kwce/packages.txt' not in seen:raise ValueError('Missing unified installer')
    result.append((package/'package-manifest.json','KWCE-UNIFIED-manifest.json'))
    return record,result

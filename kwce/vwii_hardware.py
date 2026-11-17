"""Separate, install-only channel candidate for the linked Korean vWii setup.

Ordinary Wii channels remain ordinary Wii channels: neither the vWii system
title flag nor the IOS binding or title ID is rewritten. Only the TMD region
and its fakesign fields change. No system title is accepted.
"""
import hashlib
import json
import re
from pathlib import Path

from .channel_hardware import installer_source as channel_installer
from .channels import load_library
from .hardware import hardware_wad

APP = 'apps/kwce-vwii-installer'
DATA = 'kwce-vwii'
README = 'KWCE-vWii-README-ko.txt'
MANIFEST = 'KWCE-vWii-package-manifest.json'
KIND = 'korean-vwii-channels-v1'
TITLES = {
    'forecast': '0001000248414645',
    'news': '0001000248414745',
    'votes': '0001000148414a45',
    'mii-contest': '0001000148415045',
    'wiiroom': '000100014843494a',
    'tvguide': '0001000148424e4a',
    'nintendo': '0001000148415445',
}
IOS = {'forecast': 31, 'news': 31, 'votes': 31, 'mii-contest': 35,
       'wiiroom': 56, 'tvguide': 35, 'nintendo': 55}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def readonly_config_source():
    # libogc WPAD normally persists controller active/guest lists. This
    # candidate must not persist any console settings, including that side
    # effect. --wrap intercepts library calls while retaining normal input.
    return '''/* vWii candidate: suppress libogc's automatic SYSCONF saves. */
#include <gccore.h>
s32 __wrap_CONF_SaveChanges(void) { return CONF_ERR_OK; }
'''


def validate_rows(rows):
    if len(rows) != len(TITLES) or {r['id'] for r in rows} != set(TITLES):
        raise ValueError('Expected the seven reviewed vWii channel candidates')
    for row in rows:
        if row['title_id'] != TITLES[row['id']]:
            raise ValueError('vWii channel title is outside the fixed allowlist')


def convert_wad(korean, original, channel):
    """Return a deterministic region-free WAD with byte-identical contents."""
    if channel not in TITLES:
        raise ValueError('Unreviewed vWii channel')
    checked, checks = hardware_wad(korean, original)
    lib = load_library()
    title = lib.title.Title()
    title.load_wad(checked)
    if title.tmd.title_id.lower() != TITLES[channel]:
        raise ValueError('Unexpected vWii channel title')
    if title.tmd.ios_tid.lower() != f'00000001000000{IOS[channel]:02x}':
        raise ValueError('Unexpected channel IOS binding')
    # These are regular channels, not vWii system/ancast titles. Do not turn
    # this into a flag/key/IOS conversion merely because the target is vWii.
    if title.tmd.vwii != 0 or title.ticket.common_key_index != 0:
        raise ValueError('Expected a standard, non-personalized Wii channel')
    if title.ticket.console_id != 0:
        raise ValueError('Personalized tickets are not package inputs')
    if title.ticket.title_id != bytes.fromhex(TITLES[channel]):
        raise ValueError('Ticket/channel title mismatch')
    payloads = [title.get_content_by_index(i) for i in range(len(title.tmd.content_records))]
    for payload, record in zip(payloads, title.tmd.content_records):
        if hashlib.sha1(payload).hexdigest() != record.content_hash.decode():
            raise ValueError('Channel content hash mismatch')
    before = title.tmd.dump()
    source_region = title.tmd.region
    title.tmd.region = 3
    title.fakesign()
    result = title.dump_wad()
    roundtrip = lib.title.Title()
    roundtrip.load_wad(result)
    if not roundtrip.get_is_fakesigned() or roundtrip.tmd.region != 3:
        raise ValueError('vWii candidate metadata/fakesign check failed')
    if any(roundtrip.get_content_by_index(i) != payload for i, payload in enumerate(payloads)):
        raise ValueError('vWii conversion changed a channel content')
    after = roundtrip.tmd.dump()
    allowed = set(range(4, 260)) | {0x19c, 0x19d, 0x1e2, 0x1e3}
    if len(before) != len(after) or any(a != b and i not in allowed
                                            for i, (a, b) in enumerate(zip(before, after))):
        raise ValueError('Unexpected TMD modification')
    return result, dict(checks, source_region=source_region, target_region=3,
                        content_bytes_preserved=True, ios_binding_preserved=True,
                        title_id_preserved=True, standard_channel_flag_preserved=True,
                        hardware_success_verified=False, full_localization_complete=False)


def installer_source(original, rows):
    """Generate an isolated installer; no restore/downgrade/menu writer."""
    validate_rows(rows)
    source = channel_installer(original, rows)

    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError('Reviewed vWii installer source anchor differs')
        source = source.replace(old, new)

    # Replace the inherited description as well as the paths shown on screen.
    source = '/* Korean vWii channel candidate. Install only; no system/menu writer. */\n' + source[source.index('#include <gccore.h>'):]
    replace('#define BASE "sd:/kwce"', '#define BASE "sd:/kwce-vwii"')
    replace('#define VERSION "0.4-channels-v1"', '#define VERSION "0.1-vwii-ko"')
    replace('int reload = IOS_ReloadIOS(249);', '''int target_vwii = (*(vu16 *)0xCD8005A0 == 0xCAFE);
    int conf_ok = CONF_Init() >= 0;
    int target_korean = conf_ok && CONF_GetLanguage() == CONF_LANG_KOREAN
                       && CONF_GetArea() == CONF_AREA_KOR;
    /* No IOS reload on Wii or a setup that has not received the Korean patch. */
    int reload = target_vwii && target_korean ? IOS_ReloadIOS(249) : -1;''')
    replace('    if (!fatInitDefault())', '''    if (!target_vwii || !target_korean) {
        say("\\n  Requires Wii U vWii with the linked Korean setup applied.\\n");
        say("  No channel was changed. HOME exits.\\n");
        wait_any(); return 0;
    }
    if (!fatInitDefault())''')
    a = source.index('/* Remove contents and tickets;')
    b = source.index('/* ---- actions', a)
    # A failed first install may leave a ticket. Keep that cleanup narrow;
    # there is no title-content deletion or uninstall operation in this build.
    source = source[:a] + '''static void cleanup_first_ticket(u64 tid)
{
    if (!allowed_tid(tid)) return;
    u32 views = 0;
    if (ES_GetNumTicketViews(tid, &views) >= 0 && views && views < 16) {
        tikview *v = memalign(32, sizeof(tikview) * views);
        if (v && ES_GetTicketViews(tid, v, views) >= 0)
            for (u32 i = 0; i < views; i++) ES_DeleteTicket(&v[i]);
        free(v);
    }
}

''' + source[b:]
    replace('''        if (!confirm("Remove the installed contents first (save data is kept)?")) return -1;
        remove_title(p->tid);''', '''        say("  Downgrades are refused by this vWii candidate. Nothing changed.\\n");
        return -1;''')
    a = source.index('static void do_restore(')
    b = source.index('/* ---- packages', a)
    source = source[:a] + source[b:]
    replace('        remove_title(p->tid);', '        cleanup_first_ticket(p->tid);')
    replace('else if (k == K_INSTALL || k == K_RESTORE)', 'else if (k == K_INSTALL)')
    replace('            else do_restore(&pkgs[sel]);\n', '')
    replace('1 (GC X): install Korean   2 (GC Y): restore', '1: install Korean (vWii candidate)')
    replace('HOME (GC START): exit.', 'HOME: exit.')
    replace('KWCE channel installer %s', 'KWCE Korean vWii installer %s')
    replace('Cannot write the restore record', 'Cannot write the first-install record')
    # Validate the ID/title pairing while parsing, before any state/path use.
    pairs = ' ||\n             '.join(f'(!strcmp(p->id, "{r["id"]}") && p->tid == 0x{r["title_id"]}ULL)' for r in rows)
    replace('        npkg++;', f'''        if (!({pairs})) {{
            say("  Skipped an unreviewed channel entry\\n"); continue;
        }}
        int duplicate = 0;
        for (int i = 0; i < npkg; i++) if (pkgs[i].tid == p->tid) duplicate = 1;
        if (duplicate) continue;
        npkg++;''')
    # Match the package metadata at runtime; the source IOS is retained and
    # must already be installed. This program never installs an IOS.
    runtime_pairs = ' ||\n          '.join(f'(tid == 0x{TITLES[c]}ULL && ios == 0x00000001000000{IOS[c]:02x}ULL)' for c in TITLES)
    replace('    if (tmd_len < 0x1E4 + 36u * count)', f'''    if (tmd[0x183] != 0 || *(u16 *)(tmd + 0x19C) != 3 || tik[0x1F1] != 0 ||
        !({runtime_pairs})) {{
        say("  Not the reviewed standard-channel vWii candidate\\n"); goto out;
    }}
    if (tmd_len < 0x1E4 + 36u * count)''')
    if any(x in source for x in ('menu_install(', 'menu_restore(', 'menu_available(',
                                 'do_restore(', 'remove_title(', 'ES_DeleteTitleContent(',
                                 'allow-current-ios.txt', 'CONF_SaveChanges(', 'original.wad')):
        raise ValueError('Unexpected vWii write/restore/test path')
    return source


def sd_files(package):
    """Check an immutable candidate and return its isolated copy allowlist."""
    package = Path(package).resolve()
    raw = (package / 'package-manifest.json').read_bytes()
    if sha(raw) != (package / 'package-manifest.sha256').read_text().strip():
        raise ValueError('vWii manifest digest differs')
    record = json.loads(raw)
    if record.get('kind') != KIND or not re.fullmatch(r'kwce-vwii-ko-v[1-9][0-9]*', record.get('package', '')):
        raise ValueError('Unknown vWii package')
    validate_rows(record['channels'])
    for flag in ('menu_writer_linked', 'priiloader_update', 'system_titles_included',
                 'iso_included', 'hardware_success_verified', 'publish'):
        if record.get(flag) is not False:
            raise ValueError('vWii package boundary differs')
    if record.get('install_only') is not True or record.get('downgrade_allowed') is not False:
        raise ValueError('vWii installer operation scope differs')
    if (record.get('compile_warnings') != 0 or record.get('forbidden_symbols_absent') is not True
            or record.get('configuration_save_wrapped') is not True):
        raise ValueError('vWii installer build audit differs')
    allowed = {f'{APP}/{n}' for n in ('boot.dol', 'meta.xml', 'icon.png')}
    allowed |= {f'{DATA}/packages.txt', README}
    allowed |= {f'{DATA}/{c}/korean.wad' for c in TITLES}
    if len(record['sd_files']) != len(allowed) or {r['path'] for r in record['sd_files']} != allowed:
        raise ValueError('vWii SD payload scope differs')
    result = []
    for item in record['sd_files']:
        p = package / item['path']
        if not p.resolve().is_relative_to(package) or any(q.is_symlink() or q.is_junction()
                                                       for q in (p, *p.parents) if q != package.parent):
            raise ValueError('vWii payload escapes package')
        if p.stat().st_size != item['bytes'] or sha(p.read_bytes()) != item['sha256']:
            raise ValueError('vWii payload differs')
        result.append((p, item['path']))
    result.append((package / 'package-manifest.json', MANIFEST))
    return record, result

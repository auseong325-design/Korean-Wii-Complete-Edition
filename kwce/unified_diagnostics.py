"""Diagnostic-enabled unified installer and narrowly-scoped SD package."""
import json
from pathlib import Path
from .unified_hardware import APP_DIRS,sha,source

def diagnostic_source(original):
    s=source(original).replace('0.5-unified-v1','0.6-diag-v1')
    def sub(old,new):
        nonlocal s
        if s.count(old)!=1:raise ValueError('Diagnostic installer anchor differs')
        s=s.replace(old,new)
    sub('#include "kwce.h"','#include "kwce.h"\n#include "kwce_diagnostics.h"')
    sub('K_INSTALL, K_RESTORE, K_EXIT','K_INSTALL, K_RESTORE, K_DIAG, K_EXIT')
    sub('        if ((w & WPAD_BUTTON_HOME)', '        if ((w & WPAD_BUTTON_MINUS) || (g & PAD_TRIGGER_Z)) return K_DIAG;\n        if ((w & WPAD_BUTTON_HOME)')
    sub('    printf("  Shortcuts: 1 install, 2 restore. B cancels.\\n");','    printf("  1 install, 2 restore. MINUS: diagnostic report.\\n");')
    before='static void draw(int sel)\n{'
    helper='''static void diagnostic_menu(void)
{
    const char *names[] = {"Before testing", "After News", "After Wii Room", "Other"};
    const char *phases[] = {"before", "after_news", "after_room", "other"};
    int selected = 0;
    for (;;) {
        say("\\n  Diagnostic phase: %s\\n  UP/DOWN choose, A save, B cancel.\\n", names[selected]);
        int k=read_key();
        if (k==K_UP) selected=(selected+3)%4;
        else if (k==K_DOWN) selected=(selected+1)%4;
        else if (k==K_A) { kwce_diagnostic_capture(phases[selected],installed_version); wait_any(); return; }
        else if (k==K_B || k==K_EXIT) return;
    }
}

'''
    sub(before,helper+before)
    sub('        if (k == K_UP) sel = (sel + rows - 1) % rows;', '        if (k == K_DIAG) diagnostic_menu();\n        else if (k == K_UP) sel = (sel + rows - 1) % rows;')
    if any(x in s for x in ('menu_install(', 'menu_restore(', 'allow-current-ios.txt')):raise ValueError('Unexpected unsafe installer code')
    return s

def sd_files(package):
    package=Path(package).resolve();raw=(package/'package-manifest.json').read_bytes()
    if sha(raw)!=(package/'package-manifest.sha256').read_text().strip():raise ValueError('Diagnostic manifest differs')
    record=json.loads(raw)
    if record.get('kind')!='unified-diagnostics-v1' or record.get('menu_writer_linked') or record.get('channel_wads'):raise ValueError('Diagnostic scope differs')
    allowed={f'{d}/{n}' for d in APP_DIRS for n in ('boot.dol','meta.xml','icon.png')}|{'KWCE-DIAGNOSTIC-README-ko.txt'}
    rows=record['sd_files']
    if len(rows)!=len(allowed) or {x['path'] for x in rows}!=allowed:raise ValueError('Diagnostic payload scope')
    out=[]
    for r in rows:
        p=package/r['path']
        if not p.resolve().is_relative_to(package) or p.is_symlink() or p.is_junction() or p.stat().st_size!=r['bytes'] or sha(p.read_bytes())!=r['sha256']:raise ValueError('Diagnostic payload differs')
        out.append((p,r['path']))
    out.append((package/'package-manifest.json','KWCE-DIAGNOSTIC-manifest.json'))
    return record,out

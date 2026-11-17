/*
 * KWCE unified channel installer / restorer -- release candidate.
 *
 * Installs the Korean channel WADs prepared by scripts/export_rc_hardware.py
 * from sd:/kwce-rc/, and restores each channel to its state before the first
 * KWCE change: the original (WiiLink) WAD if the channel was installed, or
 * removal of the title if it was not. Save data is never deleted. Only channel
 * titles listed in sd:/kwce-rc/packages.txt are touched; system titles, IOS,
 * the System Menu, boot2 and BC/MIOS are refused, and this app links no System
 * Menu / NAND resource writer at all.
 *
 * Upgrades over the alpha installer: one tool for every KWCE channel family,
 * an "install all" / "restore all" bulk action beside per-channel selection,
 * and console-model detection (RVL-001 vs RVL-101 / vWii). The GameCube
 * disc-channel restore is a Priiloader memory hack delivered on the SD, not a
 * NAND write, and it applies only to a GameCube-capable RVL-001 -- on an
 * RVL-101 or vWii the tool installs channel titles only and says so.
 *
 * Fakesigned WADs need an IOS with the signature-check patch: the app reloads
 * to the d2x cIOS 249 first and refuses to change anything if that fails
 * (sd:/kwce-rc/allow-current-ios.txt overrides this for emulator tests).
 */
#include <gccore.h>
#include <wiiuse/wpad.h>
#include <fat.h>
#include <malloc.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "kwce.h"

#define BASE "sd:/kwce-rc"
#define VERSION "1.0-rc2"
#define MAX_PKG 24
#define CHUNK (64 * 1024)
#define ALIGN64(x) (((x) + 63) & ~63u)
#define ALIGN16(x) (((x) + 15) & ~15u)

typedef struct {
    char id[32];
    char name[48];
    u64 tid;
    int experimental;
    int gamecube_only; /* 1 = skipped on a console without GameCube ports */
} package;

static package pkgs[MAX_PKG];
static int npkg;
static void *xfb;
static GXRModeObj *mode;
static FILE *logfile;
static int cios_ok;
static console_model model;
static int gc_ok;

void say(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    vprintf(fmt, ap);
    va_end(ap);
    if (logfile) {
        va_start(ap, fmt);
        vfprintf(logfile, fmt, ap);
        va_end(ap);
        fflush(logfile);
    }
}

/* ---- input ------------------------------------------------------------ */

enum { K_NONE, K_UP, K_DOWN, K_A, K_B, K_INSTALL, K_RESTORE, K_ALL, K_EXIT };

static int read_key(void)
{
    for (;;) {
        WPAD_ScanPads();
        PAD_ScanPads();
        u32 w = 0;
        for (int i = 0; i < 4; i++) w |= WPAD_ButtonsDown(i);
        u32 g = PAD_ButtonsDown(0);
        VIDEO_WaitVSync();
        if ((w & WPAD_BUTTON_UP) || (g & PAD_BUTTON_UP)) return K_UP;
        if ((w & WPAD_BUTTON_DOWN) || (g & PAD_BUTTON_DOWN)) return K_DOWN;
        if ((w & WPAD_BUTTON_A) || (g & PAD_BUTTON_A)) return K_A;
        if ((w & WPAD_BUTTON_B) || (g & PAD_BUTTON_B)) return K_B;
        if ((w & WPAD_BUTTON_1) || (g & PAD_BUTTON_X)) return K_INSTALL;
        if ((w & WPAD_BUTTON_2) || (g & PAD_BUTTON_Y)) return K_RESTORE;
        if ((w & WPAD_BUTTON_PLUS) || (g & PAD_BUTTON_START)) return K_ALL;
        if ((w & WPAD_BUTTON_HOME) || (g & PAD_TRIGGER_Z)) return K_EXIT;
    }
}

int confirm(const char *what)
{
    say("\n  %s\n  Press A to continue, B to cancel.\n", what);
    for (;;) {
        int k = read_key();
        if (k == K_A) return 1;
        if (k == K_B || k == K_EXIT) return 0;
    }
}

void wait_any(void)
{
    say("\n  Press any button.\n");
    read_key();
}

/* ---- title queries ------------------------------------------------------ */

static int installed_version(u64 tid)
{
    u32 size = 0;
    if (ES_GetStoredTMDSize(tid, &size) < 0 || size == 0 || size > 0x10000) return -1;
    signed_blob *tmd = memalign(32, ALIGN64(size));
    if (!tmd) return -1;
    int version = -1;
    if (ES_GetStoredTMD(tid, tmd, size) >= 0) version = *(u16 *)((u8 *)tmd + 0x1DC);
    free(tmd);
    return version;
}

/* Channel titles only. 00010001/00010002 by type; the one hidden channel KWCE
   ships (Set Personal Data, HCCJ = 00010008-4843434a) by exact id. No other
   00010008 title, no system title (00000001) and no IOS is ever accepted. */
static int channel_title(u64 tid)
{
    u32 type = (u32)(tid >> 32);
    return type == 0x00010001 || type == 0x00010002 || tid == 0x000100084843434aULL;
}

static int allowed_tid(u64 tid)
{
    if (!channel_title(tid)) return 0;
    for (int i = 0; i < npkg; i++)
        if (pkgs[i].tid == tid) return 1;
    return 0;
}

/* ---- state (before the first KWCE change) ---------------------------------- */

static void state_path(const package *p, char *out, size_t n)
{
    snprintf(out, n, BASE "/state/%s.txt", p->id);
}

static int state_before(const package *p, int *version)
{
    char path[96];
    state_path(p, path, sizeof path);
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    int before = -1, v = -1;
    if (fscanf(f, "before=%d version=%d", &before, &v) < 1) before = -1;
    fclose(f);
    if (version) *version = v;
    return before;
}

static int record_state(const package *p)
{
    char path[96];
    if (state_before(p, NULL) >= 0) return 0;
    mkdir(BASE "/state", 0777);
    state_path(p, path, sizeof path);
    FILE *f = fopen(path, "w");
    if (!f) return -1;
    int v = installed_version(p->tid);
    fprintf(f, "before=%d version=%d\n", v >= 0, v);
    fclose(f);
    say("  Recorded the state before KWCE: %s (version %d).\n", v >= 0 ? "installed" : "not installed", v);
    return 0;
}

/* ---- WAD installation -------------------------------------------------------- */

static void *read_block(FILE *f, u32 offset, u32 size)
{
    void *buf = memalign(32, ALIGN64(size ? size : 1));
    if (!buf) return NULL;
    if (fseek(f, offset, SEEK_SET) || fread(buf, 1, size, f) != size) {
        free(buf);
        return NULL;
    }
    return buf;
}

static int install_wad(const char *path, u64 expect)
{
    int ret = -1;
    u8 *certs = NULL, *tik = NULL, *tmd = NULL, *chunk = NULL;
    FILE *f = fopen(path, "rb");
    if (!f) { say("  Cannot open %s\n", path); return -1; }
    u32 h[8];
    if (fread(h, 4, 8, f) != 8) { say("  Short WAD header\n"); goto out; }
    u32 hdr = h[0], certs_len = h[2], crl_len = h[3], tik_len = h[4], tmd_len = h[5];
    if (hdr != 0x20 || tmd_len < 0x1E4 || tmd_len > 0x10000 || tik_len != 0x2A4) { say("  Not a supported WAD\n"); goto out; }
    u32 o = ALIGN64(hdr);
    certs = read_block(f, o, certs_len); o += ALIGN64(certs_len);
    o += ALIGN64(crl_len);
    tik = read_block(f, o, tik_len); o += ALIGN64(tik_len);
    tmd = read_block(f, o, tmd_len); o += ALIGN64(tmd_len);
    chunk = memalign(32, CHUNK);
    if (!certs || !tik || !tmd || !chunk) { say("  Out of memory / read error\n"); goto out; }

    u64 tid = *(u64 *)(tmd + 0x18C), tik_tid = *(u64 *)(tik + 0x1DC), ios = *(u64 *)(tmd + 0x184);
    u16 count = *(u16 *)(tmd + 0x1DE);
    if (tid != expect || tik_tid != tid || !allowed_tid(tid)) { say("  Title is not an allowed KWCE channel\n"); goto out; }
    if (tmd_len < 0x1E4 + 36u * count) { say("  Truncated TMD\n"); goto out; }
    if ((u32)(ios >> 32) != 1 || installed_version(ios) < 0) { say("  Required IOS%u is not installed\n", (u32)ios); goto out; }

    say("  Installing %016llx v%u (%u contents, IOS%u)\n", tid, *(u16 *)(tmd + 0x1DC), count, (u32)ios);
    ret = ES_AddTicket((signed_blob *)tik, tik_len, (signed_blob *)certs, certs_len, NULL, 0);
    if (ret < 0) { say("  ES_AddTicket failed: %d\n", ret); goto out; }
    ret = ES_AddTitleStart((signed_blob *)tmd, tmd_len, (signed_blob *)certs, certs_len, NULL, 0);
    if (ret < 0) { say("  ES_AddTitleStart failed: %d\n", ret); goto out; }
    for (u16 i = 0; i < count; i++) {
        u8 *rec = tmd + 0x1E4 + 36 * i;
        u32 cid = *(u32 *)rec;
        u64 size = *(u64 *)(rec + 8);
        u32 left = ALIGN16((u32)size);
        s32 cfd = ES_AddContentStart(tid, cid);
        if (cfd < 0) { ret = cfd; say("  ES_AddContentStart %u failed: %d\n", i, ret); goto cancel; }
        if (fseek(f, o, SEEK_SET)) { ret = -1; goto cancel; }
        while (left) {
            u32 n = left < CHUNK ? left : CHUNK;
            if (fread(chunk, 1, n, f) != n) { ret = -1; say("  Read error in content %u\n", i); goto cancel; }
            ret = ES_AddContentData(cfd, chunk, n);
            if (ret < 0) { say("  ES_AddContentData %u failed: %d\n", i, ret); goto cancel; }
            left -= n;
        }
        ret = ES_AddContentFinish(cfd);
        if (ret < 0) { say("  ES_AddContentFinish %u failed: %d\n", i, ret); goto cancel; }
        o += ALIGN64((u32)size);
        say("  content %u/%u ok\r", i + 1, count);
    }
    ret = ES_AddTitleFinish();
    if (ret < 0) { say("\n  ES_AddTitleFinish failed: %d\n", ret); goto cancel; }
    say("\n  Done.\n");
    goto out;
cancel:
    ES_AddTitleCancel();
    say("  Installation cancelled; the previous title files were not finalized.\n");
out:
    free(certs); free(tik); free(tmd); free(chunk);
    fclose(f);
    return ret;
}

static int remove_title(u64 tid)
{
    if (!allowed_tid(tid)) return -1;
    int ret = ES_DeleteTitleContent(tid);
    say("  Delete contents: %d\n", ret);
    u32 views = 0;
    if (ES_GetNumTicketViews(tid, &views) >= 0 && views && views < 16) {
        tikview *v = memalign(32, sizeof(tikview) * views);
        if (v && ES_GetTicketViews(tid, v, views) >= 0)
            for (u32 i = 0; i < views; i++) say("  Delete ticket: %d\n", ES_DeleteTicket(&v[i]));
        free(v);
    }
    return ret;
}

/* ---- actions --------------------------------------------------------------- */

static void wad_path(const package *p, const char *kind, char *out, size_t n)
{
    snprintf(out, n, BASE "/%s/%s.wad", p->id, kind);
}

static int prepare_overwrite(const package *p, const char *kind)
{
    char path[96];
    wad_path(p, kind, path, sizeof path);
    FILE *f = fopen(path, "rb");
    if (!f) { say("  Missing %s\n", path); return -1; }
    u32 h[8];
    int ok = fread(h, 4, 8, f) == 8;
    u16 version = 0;
    if (ok) {
        u32 o = ALIGN64(h[0]) + ALIGN64(h[2]) + ALIGN64(h[3]) + ALIGN64(h[4]) + 0x1DC;
        ok = !fseek(f, o, SEEK_SET) && fread(&version, 2, 1, f) == 1;
    }
    fclose(f);
    if (!ok) return -1;
    int installed = installed_version(p->tid);
    if (installed > version) {
        say("  Installed version %d is newer than %u.\n", installed, version);
        if (!confirm("Remove the installed contents first (save data is kept)?")) return -1;
        remove_title(p->tid);
    }
    return 0;
}

/* Returns 1 on a completed install, 0 on skip/cancel, -1 on error. */
static int do_install(const package *p, int quiet)
{
    char path[96];
    say("\n== Install Korean: %s\n", p->name);
    if (p->gamecube_only && !gc_ok) { say("  Skipped: needs GameCube ports (this console has none).\n"); return 0; }
    if (p->experimental) say("  EXPERIMENTAL: this channel did not reach its main screen in emulator tests.\n");
    if (!quiet && !confirm("Install the Korean channel? Do not power off during installation.")) return 0;
    if (record_state(p) < 0) { say("  Cannot write the restore record on SD; nothing changed.\n"); if (!quiet) wait_any(); return -1; }
    if (prepare_overwrite(p, "korean") < 0) { if (!quiet) wait_any(); return -1; }
    wad_path(p, "korean", path, sizeof path);
    int ret = install_wad(path, p->tid);
    if (ret < 0 && state_before(p, NULL) == 0 && installed_version(p->tid) < 0) {
        say("  Removing the ticket left by the failed installation.\n");
        remove_title(p->tid);
    }
    if (!quiet) wait_any();
    return ret < 0 ? -1 : 1;
}

static void do_restore(const package *p, int quiet)
{
    char path[96];
    int version = -1;
    int before = state_before(p, &version);
    say("\n== Restore: %s\n", p->name);
    if (before < 0) {
        if (quiet) { say("  No KWCE record; left unchanged.\n"); return; }
        say("  No KWCE record: this channel was not changed by KWCE.\n");
        if (!confirm("Install the original (WiiLink) WAD anyway?")) return;
        before = 1;
    }
    if (before == 0) {
        if (!quiet && !confirm("The channel was not installed before KWCE. Remove it (save data is kept)?")) return;
        remove_title(p->tid);
    } else {
        say("  Before KWCE: installed, version %d.\n", version);
        if (!quiet && !confirm("Reinstall the original (WiiLink) channel?")) return;
        if (prepare_overwrite(p, "original") < 0) { if (!quiet) wait_any(); return; }
        wad_path(p, "original", path, sizeof path);
        install_wad(path, p->tid);
    }
    if (!quiet) wait_any();
}

static void do_all(int restore)
{
    int done = 0, skipped = 0, failed = 0, n_exp = 0, include_exp = 0;
    char skipped_names[256] = "", failed_names[256] = "";
    say("\n== %s all channels\n", restore ? "Restore" : "Install Korean:");
    if (!confirm(restore ? "Restore every listed channel to its pre-KWCE state?"
                         : "Install every Korean channel now?")) return;
    if (!restore) {
        /* rc1 skipped experimental channels without asking; rc2 asks once and names them. */
        for (int i = 0; i < npkg; i++)
            if (pkgs[i].experimental && !(pkgs[i].gamecube_only && !gc_ok)) n_exp++;
        if (n_exp) {
            say("\n  Experimental (not fully verified in emulator tests):");
            for (int i = 0; i < npkg; i++)
                if (pkgs[i].experimental && !(pkgs[i].gamecube_only && !gc_ok)) say(" %s;", pkgs[i].name);
            say("\n");
            include_exp = confirm("Also install the experimental channel(s)? (B = skip them)");
        }
    }
    for (int i = 0; i < npkg; i++) {
        int skip = (pkgs[i].gamecube_only && !gc_ok) || (!restore && pkgs[i].experimental && !include_exp);
        if (skip) {
            skipped++;
            if (strlen(skipped_names) + strlen(pkgs[i].name) + 3 < sizeof skipped_names) {
                strcat(skipped_names, " ");
                strcat(skipped_names, pkgs[i].name);
                strcat(skipped_names, ";");
            }
            continue;
        }
        if (restore) do_restore(&pkgs[i], 1);
        else {
            int r = do_install(&pkgs[i], 1);
            if (r == 1) done++;
            else if (r < 0) {
                failed++;
                if (strlen(failed_names) + strlen(pkgs[i].name) + 3 < sizeof failed_names) {
                    strcat(failed_names, " ");
                    strcat(failed_names, pkgs[i].name);
                    strcat(failed_names, ";");
                }
            }
        }
    }
    say("\n  %s complete: %d channel(s), %d skipped, %d failed.\n", restore ? "Restore" : "Install",
        done, skipped, failed);
    if (skipped) say("  Skipped:%s\n", skipped_names);
    if (failed) say("  FAILED:%s\n  (details: " BASE "/log.txt)\n", failed_names);
    wait_any();
}

/* ---- packages / screen ---------------------------------------------------------- */

static int load_packages(void)
{
    FILE *f = fopen(BASE "/packages.txt", "r");
    if (!f) { say("  Cannot open " BASE "/packages.txt\n"); return -1; }
    char line[192];
    while (npkg < MAX_PKG && fgets(line, sizeof line, f)) {
        line[strcspn(line, "\r\n")] = 0;
        if (line[0] == '#' || !line[0]) continue;
        /* id|title id (16 hex)|name|experimental|gamecube_only */
        char *field[5];
        int n = 0;
        for (char *s = line; n < 5; n++) {
            field[n] = s;
            char *bar = strchr(s, '|');
            if (!bar) { n++; break; }
            *bar = 0;
            s = bar + 1;
        }
        if (n < 4 || strlen(field[1]) != 16) { say("  Skipped package line (fields %d)\n", n); continue; }
        package *p = &pkgs[npkg];
        snprintf(p->id, sizeof p->id, "%s", field[0]);
        snprintf(p->name, sizeof p->name, "%s", field[2]);
        p->tid = strtoull(field[1], NULL, 16);
        p->experimental = atoi(field[3]);
        p->gamecube_only = n >= 5 ? atoi(field[4]) : 0;
        if (!channel_title(p->tid)) { say("  Skipped non-channel title %08x\n", (u32)(p->tid >> 32)); continue; }
        npkg++;
    }
    fclose(f);
    return npkg;
}

static void draw(int sel)
{
    printf("\x1b[2J\x1b[1;0H");
    printf("  KWCE channel installer %s   IOS%d%s\n", VERSION, IOS_GetVersion(), cios_ok ? "" : " (no cIOS: test mode)");
    printf("  Console: %s\n", console_model_name(model));
    printf("  ------------------------------------------------------------\n");
    for (int i = 0; i < npkg; i++) {
        int v = installed_version(pkgs[i].tid), b = state_before(&pkgs[i], NULL);
        int off = pkgs[i].gamecube_only && !gc_ok;
        printf("  %s %-24s %s%s v%-5d %s%s\n", i == sel ? ">" : " ", pkgs[i].name,
               off ? "n/a      " : (v >= 0 ? "installed" : "absent   "), off ? "" : "", v,
               b < 0 ? "" : "[record] ", pkgs[i].experimental ? "[exp]" : "");
    }
    printf("\n  Up/Down select   1(X): install   2(Y): restore   +(START): all\n");
    if (!gc_ok)
        printf("  GameCube disc-channel restore is not available on this console.\n");
    else
        printf("  GameCube disc channel: set its mode in Priiloader (RESET at power-on).\n");
    printf("  HOME (GC Z): exit.  Log: " BASE "/log.txt\n");
}

int main(void)
{
    int reload = IOS_ReloadIOS(249);
    cios_ok = reload >= 0 && IOS_GetVersion() == 249;

    VIDEO_Init();
    mode = VIDEO_GetPreferredMode(NULL);
    xfb = MEM_K0_TO_K1(SYS_AllocateFramebuffer(mode));
    console_init(xfb, 20, 20, mode->fbWidth, mode->xfbHeight, mode->fbWidth * VI_DISPLAY_PIX_SZ);
    VIDEO_Configure(mode);
    VIDEO_SetNextFramebuffer(xfb);
    VIDEO_SetBlack(FALSE);
    VIDEO_Flush();
    VIDEO_WaitVSync();
    WPAD_Init();
    PAD_Init();

    if (!fatInitDefault()) { printf("\n  SD card not found.\n"); wait_any(); return 0; }
    logfile = fopen(BASE "/log.txt", "a");
    say("\n--- KWCE %s, IOS reload %d, running IOS%d\n", VERSION, reload, IOS_GetVersion());
    model = read_console_model();
    gc_ok = console_supports_gamecube(model);
    say("  Console model: %s\n", console_model_name(model));
    if (!cios_ok) {
        FILE *t = fopen(BASE "/allow-current-ios.txt", "r");
        if (t) { fclose(t); say("  Test mode: continuing without cIOS 249.\n"); }
        else { say("\n  cIOS 249 (d2x) could not be loaded. Nothing was changed.\n"); wait_any(); return 0; }
    }
    if (load_packages() <= 0) { say("\n  No packages in " BASE "/packages.txt\n"); wait_any(); return 0; }

    int sel = 0;
    for (;;) {
        draw(sel);
        int k = read_key();
        if (k == K_UP) sel = (sel + npkg - 1) % npkg;
        else if (k == K_DOWN) sel = (sel + 1) % npkg;
        else if (k == K_INSTALL) do_install(&pkgs[sel], 0);
        else if (k == K_RESTORE) do_restore(&pkgs[sel], 0);
        else if (k == K_ALL) {
            say("\n  All channels:  1(X) install all   2(Y) restore all   B cancel\n");
            int a = read_key();
            if (a == K_INSTALL) do_all(0);
            else if (a == K_RESTORE) do_all(1);
        }
        else if (k == K_EXIT) break;
    }
    if (logfile) fclose(logfile);
    return 0;
}

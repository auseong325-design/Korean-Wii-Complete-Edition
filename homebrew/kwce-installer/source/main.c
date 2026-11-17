/*
 * KWCE channel installer / restorer (alpha).
 *
 * Installs the Korean channel WADs prepared by scripts/export_hardware_package.py
 * from sd:/kwce/, and restores each channel to its state before the first
 * KWCE change: the original (WiiLink English) WAD if the channel was
 * installed, or removal of the title if it was not. Save data is never
 * deleted. Only channel titles listed in sd:/kwce/packages.txt are touched;
 * system titles, IOS, the System Menu, boot2 and BC/MIOS are refused.
 *
 * Fakesigned WADs need an IOS with the signature-check patch: the app
 * reloads to the d2x cIOS 249 first and refuses to change anything if that
 * fails (sd:/kwce/allow-current-ios.txt overrides this for emulator tests).
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

#define BASE "sd:/kwce"
#define VERSION "0.2-alpha"
#define MAX_PKG 16
#define CHUNK (64 * 1024)
#define ALIGN64(x) (((x) + 63) & ~63u)
#define ALIGN16(x) (((x) + 15) & ~15u)

typedef struct {
    char id[32];
    char name[48];
    u64 tid;
    int experimental;
} package;

static package pkgs[MAX_PKG];
static int npkg;
static void *xfb;
static GXRModeObj *mode;
static FILE *logfile;
static int cios_ok;
static int menu_row = -1;          /* index of the System Menu resource row, or -1 */
static const char *menu_status = "";

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

enum { K_NONE, K_UP, K_DOWN, K_A, K_B, K_INSTALL, K_RESTORE, K_EXIT };

static int read_key(void)
{
    for (;;) {
        WPAD_ScanPads();
        PAD_ScanPads();
        u32 w = WPAD_ButtonsDown(0);
        u32 g = PAD_ButtonsDown(0);
        VIDEO_WaitVSync();
        if ((w & WPAD_BUTTON_UP) || (g & PAD_BUTTON_UP)) return K_UP;
        if ((w & WPAD_BUTTON_DOWN) || (g & PAD_BUTTON_DOWN)) return K_DOWN;
        if ((w & WPAD_BUTTON_A) || (g & PAD_BUTTON_A)) return K_A;
        if ((w & WPAD_BUTTON_B) || (g & PAD_BUTTON_B)) return K_B;
        if ((w & WPAD_BUTTON_1) || (g & PAD_BUTTON_X)) return K_INSTALL;
        if ((w & WPAD_BUTTON_2) || (g & PAD_BUTTON_Y)) return K_RESTORE;
        if ((w & WPAD_BUTTON_HOME) || (g & PAD_BUTTON_START)) return K_EXIT;
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
    if (ES_GetStoredTMD(tid, tmd, size) >= 0) version = *(u16 *)((u8 *)tmd + 0x1DC); /* title_version */
    free(tmd);
    return version;
}

static int allowed_tid(u64 tid)
{
    u32 type = (u32)(tid >> 32);
    if (type != 0x00010001 && type != 0x00010002) return 0;
    for (int i = 0; i < npkg; i++)
        if (pkgs[i].tid == tid) return 1;
    return 0;
}

/* ---- state (before the first KWCE change) ---------------------------------- */

static void state_path(const package *p, char *out, size_t n)
{
    snprintf(out, n, BASE "/state/%s.txt", p->id);
}

/* Returns 1 installed / 0 not installed / -1 no record. */
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
    if (state_before(p, NULL) >= 0) return 0; /* keep the first record */
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

/* Remove contents and tickets; the title's save data stays. */
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
    /* ES refuses to install over a newer installed version: remove contents first. */
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

static void do_install(const package *p)
{
    char path[96];
    say("\n== Install Korean: %s\n", p->name);
    if (p->experimental) say("  EXPERIMENTAL: this channel did not reach its main screen in emulator tests.\n");
    if (!confirm("Install the Korean channel? Do not power off during installation.")) return;
    if (record_state(p) < 0) { say("  Cannot write the restore record on SD; nothing changed.\n"); wait_any(); return; }
    if (prepare_overwrite(p, "korean") < 0) { wait_any(); return; }
    wad_path(p, "korean", path, sizeof path);
    if (install_wad(path, p->tid) < 0 && state_before(p, NULL) == 0 && installed_version(p->tid) < 0) {
        /* A failed first install can leave the imported ticket: remove it again. */
        say("  Removing the ticket left by the failed installation.\n");
        remove_title(p->tid);
    }
    wait_any();
}

static void do_restore(const package *p)
{
    char path[96];
    int version = -1;
    int before = state_before(p, &version);
    say("\n== Restore: %s\n", p->name);
    if (before < 0) {
        say("  No KWCE record: this channel was not changed by KWCE.\n");
        if (!confirm("Install the original (WiiLink English) WAD anyway?")) return;
        before = 1;
    }
    if (before == 0) {
        if (!confirm("The channel was not installed before KWCE. Remove it (save data is kept)?")) return;
        remove_title(p->tid);
    } else {
        say("  Before KWCE: installed, version %d.\n", version);
        if (!confirm("Reinstall the original (WiiLink English) channel?")) return;
        if (prepare_overwrite(p, "original") < 0) { wait_any(); return; }
        wad_path(p, "original", path, sizeof path);
        install_wad(path, p->tid);
    }
    wait_any();
}

/* ---- packages / screen ---------------------------------------------------------- */

static int load_packages(void)
{
    FILE *f = fopen(BASE "/packages.txt", "r");
    if (!f) { say("  Cannot open " BASE "/packages.txt\n"); return -1; }
    char line[160];
    int lines = 0;
    while (npkg < MAX_PKG && fgets(line, sizeof line, f)) {
        lines++;
        line[strcspn(line, "\r\n")] = 0;
        if (line[0] == '#' || !line[0]) continue;
        /* id|title id (16 hex)|name|experimental */
        char *field[4];
        int n = 0;
        for (char *s = line; n < 4; n++) {
            field[n] = s;
            char *bar = strchr(s, '|');
            if (!bar) { n++; break; }
            *bar = 0;
            s = bar + 1;
        }
        if (n != 4 || strlen(field[1]) != 16) { say("  Skipped package line (fields %d)\n", n); continue; }
        package *p = &pkgs[npkg];
        snprintf(p->id, sizeof p->id, "%s", field[0]);
        snprintf(p->name, sizeof p->name, "%s", field[2]);
        p->tid = strtoull(field[1], NULL, 16);
        p->experimental = atoi(field[3]);
        u32 type = (u32)(p->tid >> 32);
        if (type != 0x00010001 && type != 0x00010002) { say("  Skipped non-channel title %08x\n", type); continue; }
        npkg++;
    }
    if (!npkg) say("  packages.txt: %d lines read, error %d, eof %d\n", lines, ferror(f), feof(f));
    fclose(f);
    return npkg;
}

static void draw(int sel)
{
    printf("\x1b[2J\x1b[1;0H");
    printf("  KWCE channel installer %s   IOS%d%s\n", VERSION, IOS_GetVersion(), cios_ok ? "" : " (no cIOS: test mode)");
    printf("  ------------------------------------------------------------\n");
    for (int i = 0; i < npkg; i++) {
        int v = installed_version(pkgs[i].tid), b = state_before(&pkgs[i], NULL);
        printf("  %s %-26s %s v%-5d %s%s\n", i == sel ? ">" : " ", pkgs[i].name, v >= 0 ? "installed" : "absent   ",
               v, b < 0 ? "" : "[record] ", pkgs[i].experimental ? "[experimental]" : "");
    }
    if (menu_row >= 0)
        printf("  %s %-26s %s\n", sel == menu_row ? ">" : " ", "System Menu GC visuals", menu_status);
    printf("\n  Up/Down select   1 (GC X): install Korean   2 (GC Y): restore\n");
    printf("  HOME (GC START): exit.  Log: " BASE "/log.txt\n");
}

int main(void)
{
    /* Reload to the signature-patched d2x cIOS before any other subsystem. */
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
    if (!cios_ok) {
        FILE *t = fopen(BASE "/allow-current-ios.txt", "r");
        if (t) { fclose(t); say("  Test mode: continuing without cIOS 249.\n"); }
        else { say("\n  cIOS 249 (d2x) could not be loaded. Nothing was changed.\n"); wait_any(); return 0; }
    }
    if (load_packages() <= 0) { say("\n  No packages in " BASE "/packages.txt\n"); wait_any(); return 0; }

    if (ISFS_Initialize() >= 0 && menu_available()) {
        menu_row = npkg;
        menu_status = menu_state();
    }
    int rows = npkg + (menu_row >= 0);
    int sel = 0;
    for (;;) {
        draw(sel);
        int k = read_key();
        if (k == K_UP) sel = (sel + rows - 1) % rows;
        else if (k == K_DOWN) sel = (sel + 1) % rows;
        else if (k == K_INSTALL || k == K_RESTORE) {
            if (sel == menu_row) {
                if (k == K_INSTALL) menu_install(); else menu_restore();
                menu_status = menu_state();
            } else if (k == K_INSTALL) do_install(&pkgs[sel]);
            else do_restore(&pkgs[sel]);
        }
        else if (k == K_EXIT) break;
    }
    if (logfile) fclose(logfile);
    return 0;
}

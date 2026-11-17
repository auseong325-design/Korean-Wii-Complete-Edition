/*
 * KWCE unified channel installer / restorer -- release candidate.
 *
 * Installs the Korean channel WADs prepared by scripts/export_rc_hardware.py from sd:/kwce-rc/,
 * restores each channel to its state before the first KWCE change (the original WAD if the
 * channel was installed, removal of the title if it was not) and deletes a channel on request.
 * Save data is never deleted. Only channel titles listed in sd:/kwce-rc/packages.txt are
 * touched; system titles, IOS, the System Menu, boot2 and BC/MIOS are refused, and this app links
 * no System Menu / NAND resource writer at all.
 *
 * RC4 adds version detection. The build on the console is identified from its stored TMD
 * (versions.c) and compared with this package's WADs and with sd:/kwce-rc/versions.txt, which
 * lists every older KWCE release and the channel originals. Each channel shows "up to date",
 * "UPDATE: RCn -> RCm", "original", "not installed" or an unknown version. Install-all skips
 * channels that are already up to date, "updates only" installs just the older KWCE builds, and
 * every install, restore and delete is checked on the console afterwards. A per-channel menu (A)
 * shows the details and offers install / restore / delete. POWER and RESET pressed during a
 * change take effect after the current step instead of interrupting the NAND write.
 * RC5: ES keeps a deleted channel's TMD, so a title counts as installed only while its boot
 * content is on the NAND (RC4 read the TMD alone and showed deleted channels as installed).
 * RC9: channel editions (sd:/kwce-rc/editions.txt). The channel menu picks, with left/right, the
 * standard Korean build or an edition WAD (kwce-rc/<channel>/korean-<key>.wad); the Food Channel
 * offers the WiiLink real-order editions this way. An installed edition counts as up to date and
 * stays the choice; install-all never switches editions.
 *
 * Console-model detection (RVL-001 vs RVL-101 / vWii): the GameCube disc-channel restore is a
 * Priiloader memory hack delivered on the SD, not a NAND write, and it applies only to a
 * GameCube-capable RVL-001 -- on an RVL-101 or vWii the tool installs channel titles only.
 *
 * Fakesigned WADs need an IOS with the signature-check patch: the app reloads to the d2x cIOS 249
 * first and refuses to change anything if that fails (sd:/kwce-rc/allow-current-ios.txt
 * overrides this for emulator tests).
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
#define VERSION "1.0.8"
#define MAX_PKG 24
#define CHUNK (64 * 1024)
#define ALIGN64(x) (((x) + 63) & ~63u)
#define ALIGN16(x) (((x) + 15) & ~15u)
#define RULE "  ------------------------------------------------------------------\n"

typedef struct {
    char id[32];
    char name[48];
    u64 tid;
    int experimental;
    int gamecube_only; /* 1 = skipped on a console without GameCube ports */
    int remove_only; /* legacy title: keep detection/removal, never install */
} package;

/* What the console has, compared with this package and the version list. */
typedef enum {
    ST_NA, ST_ABSENT, ST_LATEST, ST_UPDATE, ST_ORIGINAL, ST_NEWER, ST_KWCE_OTHER, ST_OTHER, ST_COUNT
} chan_state;

typedef struct {
    chan_state state;
    int installed;
    identity inst;
    int marks;                 /* contents only KWCE builds have */
    const known_build *known;  /* entry of versions.txt, or NULL */
    int region_ok;             /* 1 = this System Menu starts it, 0 = refuses it, -1 = unknown */
    int edition;               /* installed build is this package's edition n (1-based); 0 = not an edition */
} chan_status;

typedef struct {
    int have_korean, have_original;
    identity korean, original;
} package_files;

/* RC9+: optional editions of a channel from sd:/kwce-rc/editions.txt (channel|key|label), installed
   from sd:/kwce-rc/<channel>/korean-<key>.wad instead of korean.wad when chosen in the channel menu.
   The Food Channel uses this for the WiiLink real-order editions (Domino's, Just Eat). */
#define MAX_ED 16
typedef struct {
    int pkg;
    char key[24];
    char label[40];
    int have;
    identity id;
} edition;

enum { BULK_INSTALL, BULK_UPDATES, BULK_RESTORE };

static package pkgs[MAX_PKG];
static package_files files[MAX_PKG];
static chan_status st[MAX_PKG];
static int npkg;
static edition eds[MAX_ED];
static int ned;
static int sel_ed[MAX_PKG];   /* build install uses: 0 = standard Korean build, n = edition n of the package */
static void *xfb;
static GXRModeObj *mode;
static FILE *logfile;
static int cios_ok;
static console_model model;
static int gc_ok;
static int release;     /* N of VERSION "1.0-rcN"; the final "1.0" is release 32 */
static int versions_n;  /* builds in versions.txt; <0 = missing / unknown format */
static int wl_state;
static volatile int power_req, reset_req;

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

static void log_only(const char *fmt, ...)
{
    if (!logfile) return;
    va_list ap;
    va_start(ap, fmt);
    vfprintf(logfile, fmt, ap);
    va_end(ap);
    fflush(logfile);
}

/* ---- input ------------------------------------------------------------ */

enum { K_NONE, K_UP, K_DOWN, K_A, K_B, K_INSTALL, K_RESTORE, K_ALL, K_DISC, K_EXIT, K_SYS, K_LEFT, K_RIGHT };

/* POWER / RESET only set a flag; the main loop acts on it between steps. */
static void on_power(void) { power_req = 1; }
static void on_reset(u32 irq, void *ctx) { (void)irq; (void)ctx; reset_req = 1; }
static void on_remote_power(s32 chan) { (void)chan; power_req = 1; }

#ifdef KWCE_TEST_SCRIPT
/* Emulator test builds only (scripts/test_rc_installer.py; never in a package):
   the keys come from sd:/kwce-rc/test-keys.txt and the end of the file acts as RESET. */
static FILE *keyscript;

static int script_key(void)
{
    static const struct { const char *name; int key; } map[] = {
        { "UP", K_UP }, { "DOWN", K_DOWN }, { "A", K_A }, { "B", K_B }, { "1", K_INSTALL },
        { "2", K_RESTORE }, { "PLUS", K_ALL }, { "MINUS", K_DISC }, { "HOME", K_EXIT },
        { "LEFT", K_LEFT }, { "RIGHT", K_RIGHT },
    };
    char tok[16];
    for (int f = 0; f < 20; f++) VIDEO_WaitVSync();
    while (fscanf(keyscript, "%15s", tok) == 1) {
        if (tok[0] == '#') {
            int c;
            while ((c = fgetc(keyscript)) != EOF && c != '\n') {}
            continue;
        }
        for (unsigned i = 0; i < sizeof map / sizeof map[0]; i++)
            if (!strcmp(tok, map[i].name)) {
                log_only("  [test key] %s\n", tok);
                return map[i].key;
            }
    }
    reset_req = 1;
    return K_SYS;
}
#endif

static int read_key(void)
{
    for (;;) {
        if (power_req || reset_req) return K_SYS;
#ifdef KWCE_TEST_SCRIPT
        if (keyscript) return script_key();
#endif
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
        if ((w & WPAD_BUTTON_MINUS) || (g & PAD_TRIGGER_L)) return K_DISC;
        if ((w & WPAD_BUTTON_HOME) || (g & PAD_TRIGGER_Z)) return K_EXIT;
        if ((w & WPAD_BUTTON_LEFT) || (g & PAD_BUTTON_LEFT)) return K_LEFT;
        if ((w & WPAD_BUTTON_RIGHT) || (g & PAD_BUTTON_RIGHT)) return K_RIGHT;
    }
}

int choose_ab(void)
{
    for (;;) {
        int k = read_key();
        if (k == K_A) return 1;
        if (k == K_B || k == K_EXIT) return 0;
        if (k == K_SYS) return -1;
    }
}

int confirm(const char *what)
{
    say("\n  %s\n  Press A to continue, B to cancel.\n", what);
    return choose_ab() > 0;
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
    snprintf(out, n, BASE "/state/%.31s.txt", p->id);
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

/* Version of the title when its TMD and every content are on the NAND, else -1.
   ES keeps a deleted channel's TMD, so the TMD alone does not mean "installed". */
static int present_version(const package *p)
{
    identity id;
    if (installed_identity(p->tid, p->id, &id, NULL) < 0 || !id.complete) return -1;
    return id.version;
}

static int record_state(const package *p)
{
    char path[96];
    if (state_before(p, NULL) >= 0) return 0;
    mkdir(BASE "/state", 0777);
    state_path(p, path, sizeof path);
    FILE *f = fopen(path, "w");
    if (!f) return -1;
    int v = present_version(p);
    fprintf(f, "before=%d version=%d\n", v >= 0, v);
    fclose(f);
    say("  Recorded the state before KWCE: %s (version %d).\n", v >= 0 ? "installed" : "not installed", v);
    return 0;
}

/* ---- versions: this package vs the console ---------------------------------- */

static const char *region_name(unsigned r)
{
    static const char *names[] = { "JPN", "USA", "EUR", "any", "KOR" };
    return r < 5 ? names[r] : "?";
}

static const char *area_text(void)
{
    return console_area()[0] ? console_area() : "unknown";
}

static const char *wiilink_text(void)
{
    /* 0 only means the Mail Patcher's settings are absent: WiiLink via DNS is not visible. */
    return wl_state == 1 ? "detected" : wl_state == 0 ? "unconfirmed" : "unknown";
}

#define FINAL_1_0 32   /* "1.0" follows RC31; keep in step with kwce/rc_hardware.py */
static int release_of(const char *v)
{
    const char *r = strstr(v, "-rc");
    if (r) return atoi(r + 3);
    if (strcmp(v, "1.0.1") == 0) return FINAL_1_0 + 1;
    if (strcmp(v, "1.0.2") == 0) return FINAL_1_0 + 2;
    if (strcmp(v, "1.0.3") == 0) return FINAL_1_0 + 3;
    if (strcmp(v, "1.0.4") == 0) return FINAL_1_0 + 4;
    if (strcmp(v, "1.0.5") == 0) return FINAL_1_0 + 5;
    if (strcmp(v, "1.0.6") == 0) return FINAL_1_0 + 6;
    if (strcmp(v, "1.0.7") == 0) return FINAL_1_0 + 7;
    if (strcmp(v, "1.0.8") == 0) return FINAL_1_0 + 8;
    return strcmp(v, "1.0") == 0 ? FINAL_1_0 : 0;
}

/* "RC12" or "1.0"; four rotating buffers so one printf can name two releases. */
static const char *rel_name(int n)
{
    static char buf[4][16];
    static int next;
    char *b = buf[next++ & 3];
    if (n == FINAL_1_0) snprintf(b, sizeof buf[0], "1.0");
    else if (n == FINAL_1_0 + 1) snprintf(b, sizeof buf[0], "1.0.1");
    else if (n == FINAL_1_0 + 2) snprintf(b, sizeof buf[0], "1.0.2");
    else if (n == FINAL_1_0 + 3) snprintf(b, sizeof buf[0], "1.0.3");
    else if (n == FINAL_1_0 + 4) snprintf(b, sizeof buf[0], "1.0.4");
    else if (n == FINAL_1_0 + 5) snprintf(b, sizeof buf[0], "1.0.5");
    else if (n == FINAL_1_0 + 6) snprintf(b, sizeof buf[0], "1.0.6");
    else if (n == FINAL_1_0 + 7) snprintf(b, sizeof buf[0], "1.0.7");
    else if (n == FINAL_1_0 + 8) snprintf(b, sizeof buf[0], "1.0.8");
    else snprintf(b, sizeof buf[0], "RC%d", n);
    return b;
}

static void wad_path(const package *p, const char *kind, char *out, size_t n)
{
    snprintf(out, n, BASE "/%.31s/%.8s.wad", p->id, kind);
}

static void edition_path(const edition *e, char *out, size_t n)
{
    snprintf(out, n, BASE "/%.31s/korean-%.23s.wad", pkgs[e->pkg].id, e->key);
}

/* Number of editions package i has. */
static int n_editions(int i)
{
    int n = 0;
    for (int e = 0; e < ned; e++)
        if (eds[e].pkg == i) n++;
    return n;
}

/* Edition k (1-based) of package i, or NULL. */
static const edition *edition_of(int i, int k)
{
    for (int e = 0; e < ned && k > 0; e++)
        if (eds[e].pkg == i && --k == 0) return &eds[e];
    return NULL;
}

/* sd:/kwce-rc/editions.txt: "channel id|edition key|label"; optional (no file = no editions). */
static void load_editions(void)
{
    FILE *f = fopen(BASE "/editions.txt", "r");
    if (!f) return;
    char line[160];
    while (ned < MAX_ED && fgets(line, sizeof line, f)) {
        line[strcspn(line, "\r\n")] = 0;
        if (line[0] == '#' || !line[0]) continue;
        char *key = strchr(line, '|');
        char *label = key ? strchr(key + 1, '|') : NULL;
        if (!label) continue;
        *key++ = 0;
        *label++ = 0;
        int ok = key[0] && strlen(key) < sizeof eds[0].key && label[0];
        for (const char *c = key; *c; c++)
            if (!((*c >= 'a' && *c <= 'z') || (*c >= '0' && *c <= '9') || *c == '-')) ok = 0;
        int p = -1;
        for (int i = 0; i < npkg; i++)
            if (!strcmp(pkgs[i].id, line)) p = i;
        if (!ok || p < 0) { say("  Skipped edition line\n"); continue; }
        edition *e = &eds[ned++];
        e->pkg = p;
        snprintf(e->key, sizeof e->key, "%s", key);
        snprintf(e->label, sizeof e->label, "%s", label);
    }
    fclose(f);
}

static void load_files(void)
{
    char path[96];
    for (int i = 0; i < npkg; i++) {
        package_files *f = &files[i];
        wad_path(&pkgs[i], "korean", path, sizeof path);
        f->have_korean = wad_identity(path, &f->korean) == 0 && f->korean.tid == pkgs[i].tid;
        wad_path(&pkgs[i], "original", path, sizeof path);
        f->have_original = wad_identity(path, &f->original) == 0 && f->original.tid == pkgs[i].tid;
    }
    for (int e = 0; e < ned; e++) {
        edition_path(&eds[e], path, sizeof path);
        eds[e].have = wad_identity(path, &eds[e].id) == 0 && eds[e].id.tid == pkgs[eds[e].pkg].tid;
    }
}

/* Which of package i's editions has build fingerprint fp (1-based), 0 = none. */
static int edition_with_fp(int i, u64 fp)
{
    for (int k = 1; k <= n_editions(i); k++) {
        const edition *e = edition_of(i, k);
        if (e->have && e->id.fp == fp) return k;
    }
    return 0;
}

/* The build an install of package i uses: the chosen edition or the standard Korean build.
   Fills path and *label (NULL for the standard build). Returns 0 when the WAD is on SD, -1 if not. */
static int chosen_build(int i, const identity **id, char *path, size_t n, const char **label)
{
    const edition *e = sel_ed[i] ? edition_of(i, sel_ed[i]) : NULL;
    if (e) {
        edition_path(e, path, n);
        *id = &e->id;
        *label = e->label;
        return e->have ? 0 : -1;
    }
    wad_path(&pkgs[i], "korean", path, n);
    *id = &files[i].korean;
    *label = NULL;
    return files[i].have_korean ? 0 : -1;
}

static void scan_one(int i)
{
    const package *p = &pkgs[i];
    chan_status *s = &st[i];
    memset(s, 0, sizeof *s);
    s->region_ok = -1;
    if (p->gamecube_only && !gc_ok) { s->state = ST_NA; return; }
    if (installed_identity(p->tid, p->id, &s->inst, &s->marks) < 0 || !s->inst.complete) {
        s->state = ST_ABSENT;   /* also a deleted channel whose TMD is still on the NAND */
        return;
    }
    s->installed = 1;
    int want = console_tmd_region();
    if (want >= 0) s->region_ok = s->inst.region == 3 || s->inst.region == want;
    s->known = versions_lookup(p->id, s->inst.fp);
    if (files[i].have_korean && s->inst.fp == files[i].korean.fp) s->state = ST_LATEST;
    else if ((s->edition = edition_with_fp(i, s->inst.fp)) > 0) s->state = ST_LATEST;
    else if (files[i].have_original && s->inst.fp == files[i].original.fp) s->state = ST_ORIGINAL;
    else if (s->known && s->known->kind == 'O') s->state = ST_ORIGINAL;
    else if (s->known) s->state = s->known->rank >= release ? ST_NEWER : ST_UPDATE;
    else s->state = s->marks ? ST_KWCE_OTHER : ST_OTHER;
}

static void scan_all(void)
{
    for (int i = 0; i < npkg; i++) scan_one(i);
}

static int unknown_state(chan_state s)
{
    return s == ST_OTHER || s == ST_KWCE_OTHER || s == ST_NEWER;
}

/* Short text for the list (at most 25 characters). */
static const char *state_text(int i, char *buf, size_t n)
{
    const chan_status *s = &st[i];
    switch (s->state) {
        case ST_NA: return "n/a (no GameCube ports)";
        case ST_ABSENT: return "not installed";
        case ST_LATEST:
            if (!s->edition) return "Korean, up to date";
            snprintf(buf, n, "Korean %.10s, latest", edition_of(i, s->edition)->key);
            return buf;
        case ST_UPDATE:
            if (s->known->rank > 0) snprintf(buf, n, "UPDATE: %s -> %s", rel_name(s->known->rank), rel_name(release));
            else snprintf(buf, n, "UPDATE: test build -> %s", rel_name(release));
            return buf;
        case ST_ORIGINAL: return "original";
        case ST_NEWER: snprintf(buf, n, "Korean, newer (%s)", rel_name(s->known->rank)); return buf;
        case ST_KWCE_OTHER: return "Korean, unlisted build";
        default: snprintf(buf, n, "other version v%u", (unsigned)s->inst.version); return buf;
    }
}

static void describe_installed(int i, char *buf, size_t n)
{
    const chan_status *s = &st[i];
    char what[64];
    switch (s->state) {
        case ST_NA: snprintf(buf, n, "n/a on this console"); return;
        case ST_ABSENT: snprintf(buf, n, "not installed"); return;
        case ST_LATEST:
            if (s->edition) snprintf(what, sizeof what, "edition %.39s", edition_of(i, s->edition)->label);
            else snprintf(what, sizeof what, "the Korean build of this package");
            break;
        case ST_UPDATE:
            if (s->known->rank > 0) snprintf(what, sizeof what, "Korean build from %s", rel_name(s->known->rank));
            else snprintf(what, sizeof what, "Korean test build (%s)", s->known->label);
            break;
        case ST_ORIGINAL: snprintf(what, sizeof what, "the original channel"); break;
        case ST_NEWER: snprintf(what, sizeof what, "Korean build from %s (newer than this tool)", rel_name(s->known->rank)); break;
        case ST_KWCE_OTHER: snprintf(what, sizeof what, "a Korean build this list does not know"); break;
        default: snprintf(what, sizeof what, "a version this tool does not know"); break;
    }
    snprintf(buf, n, "%s, v%u, region %s", what, (unsigned)s->inst.version, region_name(s->inst.region));
}

static void hex16(u64 v, char *out)
{
    snprintf(out, 17, "%016llx", (unsigned long long)v);
}

static void log_scan(const char *when)
{
    char buf[64], fp[17];
    log_only("  Channel scan (%s):\n", when);
    for (int i = 0; i < npkg; i++) {
        const chan_status *s = &st[i];
        if (!s->installed) {
            log_only("    %-14s %s\n", pkgs[i].id, state_text(i, buf, sizeof buf));
            continue;
        }
        hex16(s->inst.fp, fp);
        log_only("    %-14s %-25s v%u %s fp %s%s\n", pkgs[i].id, state_text(i, buf, sizeof buf),
                 (unsigned)s->inst.version, region_name(s->inst.region), fp,
                 s->region_ok == 0 ? " (this System Menu will not start it)" : "");
    }
}

static void log_files(void)
{
    char k[17], o[17];
    log_only("  Package files:\n");
    for (int i = 0; i < npkg; i++) {
        hex16(files[i].korean.fp, k);
        hex16(files[i].original.fp, o);
        log_only("    %-14s korean %s  original %s\n", pkgs[i].id, files[i].have_korean ? k : "missing",
                 files[i].have_original ? o : "none");
    }
    for (int e = 0; e < ned; e++) {
        hex16(eds[e].id.fp, k);
        log_only("    %-14s edition %s %s\n", pkgs[eds[e].pkg].id, eds[e].key, eds[e].have ? k : "missing");
    }
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

static void install_hint(int ret)
{
    if (ret == -2011)
        say("  Hint: the signature check failed.\n"
            "  Run this tool with d2x cIOS 249 installed.\n");
    else if (ret == -1022)
        say("  Hint: a content did not match its hash. The WAD on SD may be damaged;\n"
            "  copy the package to the SD card again.\n");
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

/* After a change: does the console now hold exactly the wanted build? */
static int verify_installed(int i, const identity *want, const char *what)
{
    scan_one(i);
    if (st[i].installed && st[i].inst.fp == want->fp) {
        say("  Verified on the console: %s,\n  v%u, region %s.\n", what, (unsigned)want->version,
            region_name(want->region));
        return 0;
    }
    if (st[i].installed)
        say("  NOTE: the installed title is not %s.\n  The list shows what is installed.\n", what);
    else
        say("  WARNING: the title is not installed after the installation.\n");
    return -1;
}

/* ---- screen layout ----------------------------------------------------------- */

/* Longest line shown. The console is 77 columns wide and TVs crop the edges. */
#define WRAP_COLS 74

static void new_screen(void)
{
    printf("\x1b[2J\x1b[1;0H");
}

/* Folds text into lines of at most WRAP_COLS columns. col is the column where the text starts and
   where later lines are indented to. A line breaks at a space, preferably after a ';' so that a
   name such as "Wii Room" stays whole; a word longer than a line is cut. Returns out. */
static const char *fold(char *out, size_t n, const char *text, size_t col)
{
    size_t o = 0, room = col < WRAP_COLS ? WRAP_COLS - col : 1;
    while (*text && o + 1 < n) {
        size_t len = strlen(text), cut = len;
        if (len > room) {
            size_t space = 0, semi = 0;
            for (size_t i = 1; i <= room; i++) {
                if (text[i] != ' ') continue;
                space = i;
                if (text[i - 1] == ';') semi = i;
            }
            cut = semi ? semi : space ? space : room;
        }
        for (size_t i = 0; i < cut && o + 1 < n; i++) out[o++] = text[i];
        text += cut;
        while (*text == ' ') text++;
        if (*text) {
            if (o + 1 + col >= n) break;
            out[o++] = '\n';
            for (size_t i = 0; i < col; i++) out[o++] = ' ';
        }
    }
    out[o] = 0;
    return out;
}

/* A heading, then the names ("A; B; C") folded under it. */
static void say_names(const char *heading, const char *names)
{
    char text[512];
    say("%s\n    %s\n", heading, fold(text, sizeof text, names, 4));
}

/* ---- actions --------------------------------------------------------------- */

/* Before replacing a title: when the console holds a NEWER version than the WAD (for example
   restoring an older original over a Korean build), the installed contents have to go first.
   Asked even during bulk actions. Returns 0 to go on, -1 when the user declines. */
static int allow_overwrite(int i, const identity *w)
{
    int have = present_version(&pkgs[i]);
    if (have <= (int)w->version) return 0;
    say("  The console has v%d of this channel; this WAD has v%u.\n"
        "  The console may refuse to replace a newer version, so the installed\n"
        "  contents are removed first. Save data is kept.\n", have, (unsigned)w->version);
    if (!confirm("Remove the installed contents and continue?")) return -1;
    remove_title(pkgs[i].tid);
    return 0;
}

/* Shown before an edition is installed (WiiLink real-order editions of the Food Channel). */
static void edition_warning(const char *label)
{
    say("  Edition: %.39s (WiiLink real-order edition)\n", label);
    say("  It sends REAL orders through WiiLink; its menus are English. KWCE never\n"
        "  placed an order with it and never ran it on a Korean Wii. It can work\n"
        "  only if you live in this country, link this Wii to a WiiLink account\n"
        "  with the WiiLink Account Linker (Open Shop Channel) and enter an English\n"
        "  address and a local phone number in Set Personal Data.\n");
}

/* Returns 1 on a completed install, 0 on skip/cancel, -1 on error. */
static int do_install(int i, int quiet)
{
    const package *p = &pkgs[i];
    if (p->remove_only) {
        say("  DVD now starts directly from the Disc Channel.\n"
            "  This legacy channel is not needed. No title was installed.\n"
            "  Use Disc channel mode (GameCube + DVD), then enable the KWCE\n"
            "  DVD entry in Priiloader. Keep the kwce/dvd folder on the SD.\n");
        if (!quiet) wait_any();
        return 0;
    }
    char path[96], inst[160], folded[256];
    const identity *want = NULL;
    const char *ed = NULL;
    if (!quiet) new_screen();
    say("\n== Install Korean: %s\n", p->name);
    if (p->gamecube_only && !gc_ok) { say("  Skipped: needs GameCube ports (this console has none).\n"); return 0; }
    if (chosen_build(i, &want, path, sizeof path, &ed) < 0) {
        say("  Missing or unreadable %s.\n  Copy the package again.\n", path);
        if (!quiet) wait_any();
        return -1;
    }
    if (ed) edition_warning(ed);
    scan_one(i);
    describe_installed(i, inst, sizeof inst);
    say("  On this console: %s\n", fold(folded, sizeof folded, inst, 19));
    if (p->experimental) say("  EXPERIMENTAL: it did not reach its main screen in emulator tests.\n");
    int area = console_tmd_region();
    if (area >= 0 && want->region != 3 && (int)want->region != area)
        say("  WARNING: this build is for region %s; this console (region %s)\n"
            "  will not start it.\n", region_name(want->region), area_text());
    if (st[i].installed && st[i].inst.fp == want->fp) {
        say("  This console already has %s.\n", ed ? "this edition" : "the Korean build of this package");
        if (quiet || !confirm("Reinstall it anyway (repair)?")) return 0;
    } else if (!quiet && !confirm(ed ? "Install this edition? Do not power off during installation."
                                     : "Install the Korean channel? Do not power off during installation.")) {
        return 0;
    }
    if (record_state(p) < 0) {
        say("  Cannot write the restore record on SD; nothing changed.\n");
        if (!quiet) wait_any();
        return -1;
    }
    if (allow_overwrite(i, want) < 0) { if (!quiet) wait_any(); return -1; }
    if (ed) say("  WAD: %s\n", path);
    int ret = install_wad(path, p->tid);
    if (ret < 0) {
        install_hint(ret);
        if (state_before(p, NULL) == 0 && present_version(p) < 0) {
            say("  Removing the ticket left by the failed installation.\n");
            remove_title(p->tid);
        }
    } else {
        verify_installed(i, want, ed ? "the chosen edition of this package" : "the Korean build of this package");
    }
    if (!quiet) wait_any();
    return ret < 0 ? -1 : 1;
}

/* Returns 1 when something was restored, 0 when nothing needed doing / cancelled, -1 on error. */
static int do_restore(int i, int quiet)
{
    const package *p = &pkgs[i];
    char path[96];
    int version = -1, result = 1;
    int before = state_before(p, &version);
    if (!quiet) new_screen();
    say("\n== Restore: %s\n", p->name);
    if (p->gamecube_only && !gc_ok) { say("  Skipped: needs GameCube ports (this console has none).\n"); return 0; }
    scan_one(i);
    if (before < 0) {
        if (quiet) { say("  No KWCE record; left unchanged.\n"); return 0; }
        say("  No KWCE record: this channel was not changed by KWCE.\n");
        if (!files[i].have_original) { say("  This package has no original WAD for it. Nothing to do.\n"); wait_any(); return 0; }
        if (st[i].installed && st[i].inst.fp == files[i].original.fp) {
            say("  The original channel of this package is already installed.\n"
                "  Nothing to do.\n");
            wait_any();
            return 0;
        }
        if (!confirm("Install the original channel anyway?")) return 0;
        before = 1;
    }
    if (before == 0) {
        say("  Before KWCE: not installed.\n");
        if (!st[i].installed) {
            say("  It is not installed now either. Nothing to do.\n");
            if (!quiet) wait_any();
            return 0;
        }
        if (!quiet && !confirm("Remove the channel (save data is kept)?")) return 0;
        remove_title(p->tid);
        scan_one(i);
        if (st[i].installed) {
            say("  WARNING: the title is still installed.\n");
            result = -1;
        } else {
            say("  Verified on the console: the channel is removed.\n");
        }
    } else {
        say("  Before KWCE: installed, version %d.\n", version);
        if (!files[i].have_original) {
            say("  Missing " BASE "/%s/original.wad. Nothing changed.\n", p->id);
            if (!quiet) wait_any();
            return -1;
        }
        if (st[i].installed && st[i].inst.fp == files[i].original.fp) {
            say("  The original channel of this package is already installed.\n");
            if (quiet || !confirm("Reinstall the original anyway (repair)?")) return 0;
        } else if (!quiet && !confirm("Reinstall the original channel?")) {
            return 0;
        }
        if (allow_overwrite(i, &files[i].original) < 0) { if (!quiet) wait_any(); return -1; }
        wad_path(p, "original", path, sizeof path);
        int ret = install_wad(path, p->tid);
        if (ret < 0) {
            install_hint(ret);
            result = -1;
        } else {
            verify_installed(i, &files[i].original, "the original channel of this package");
        }
    }
    if (!quiet) wait_any();
    return result;
}

static void do_delete(int i)
{
    const package *p = &pkgs[i];
    new_screen();
    say("\n== Step 2 of 3: Review deletion\n  Channel: %s\n", p->name);
    scan_one(i);
    if (!st[i].installed) {
        say("  Not installed. Nothing to delete.\n");
        wait_any();
        return;
    }
    char inst[160], folded[256];
    describe_installed(i, inst, sizeof inst);
    say("  Installed: %s\n", fold(folded, sizeof folded, inst, 20));
    say("  Removes this channel's program files and ticket.\n"
        "  Save data stays on the console.\n"
        "  Restore is a separate action and depends on the saved record\n"
        "  and the original package available on the SD card.\n");
    if (!confirm("Delete this channel from the console?")) return;
    say("\n== Step 3 of 3: Final confirmation\n  Channel: %s\n", p->name);
    say("  Press -(GC L) to delete. Any other button cancels.\n");
    if (read_key() != K_DISC) {
        say("  Cancelled. Nothing changed.\n");
        return;
    }
    if (record_state(p) < 0) {
        say("  Cannot write the restore record on SD; nothing changed.\n");
        wait_any();
        return;
    }
    int ret = remove_title(p->tid);
    scan_one(i);
    if (ret < 0)
        say("  WARNING: deletion returned an error; check channel status.\n");
    else if (st[i].installed)
        say("  WARNING: the title is still installed.\n");
    else
        say("  Verified on the console: the channel is deleted.\n");
    wait_any();
}

/* Adds a name to a list printed as "A; B; C": a separator before every name but the first. */
static void add_name(char *list, size_t n, const char *name)
{
    size_t used = strlen(list), sep = used ? 2 : 0;
    if (used + sep + strlen(name) < n) {
        if (sep) strcat(list, "; ");
        strcat(list, name);
    }
}

static void do_all(int bulk)
{
    static const char *title[] = { "Install / update all", "Install updates only", "Restore all" };
    int done = 0, unchanged = 0, skipped = 0, failed = 0, n_exp = 0, n_unknown = 0, todo = 0;
    int include_exp = 0, include_unknown = 0;
    char skipped_names[320] = "", failed_names[320] = "", list[320] = "", question[160];
    new_screen();
    say("\n== %s\n", title[bulk]);
    scan_all();
    for (int i = 0; i < npkg; i++) {
        chan_state s = st[i].state;
        if (s == ST_NA || bulk == BULK_RESTORE || pkgs[i].remove_only) continue;
        if (bulk == BULK_UPDATES && s != ST_UPDATE) continue;
        if (s == ST_LATEST) continue;
        todo++;
        if (sel_ed[i] && edition_of(i, sel_ed[i])) {
            char named[80];
            snprintf(named, sizeof named, "%s (%s)", pkgs[i].name, edition_of(i, sel_ed[i])->key);
            add_name(list, sizeof list, named);
        } else {
            add_name(list, sizeof list, pkgs[i].name);
        }
        if (bulk == BULK_INSTALL && pkgs[i].experimental) n_exp++;
        if (bulk == BULK_INSTALL && unknown_state(s)) n_unknown++;
    }
    if (bulk != BULK_RESTORE && !todo) {
        say("  Nothing to do: %s.\n", bulk == BULK_UPDATES ? "no channel has an older Korean build"
                                                           : "every channel is up to date");
        wait_any();
        return;
    }
    if (bulk != BULK_RESTORE) say_names("  Channels:", list);
    if (!confirm(fold(question, sizeof question,
                      bulk == BULK_RESTORE ? "Restore every listed channel to its pre-KWCE state?"
                      : "Install these Korean channels now? Do not power off during installation.", 2))) return;
    if (n_exp) {
        char names[320] = "";
        for (int i = 0; i < npkg; i++)
            if (pkgs[i].experimental && st[i].state != ST_NA && st[i].state != ST_LATEST)
                add_name(names, sizeof names, pkgs[i].name);
        say_names("\n  Experimental (not fully verified in emulator tests):", names);
        include_exp = confirm("Also install the experimental channel(s)? (B = skip them)");
    }
    if (n_unknown) {
        char names[320] = "";
        for (int i = 0; i < npkg; i++)
            if (unknown_state(st[i].state)) add_name(names, sizeof names, pkgs[i].name);
        say_names("\n  Versions this tool does not know:", names);
        include_unknown = confirm("Replace them with this package's Korean builds? (B = keep them)");
    }
    for (int i = 0; i < npkg; i++) {
        if (power_req || reset_req) {
            say("\n  POWER/RESET pressed: stopping before %s.\n", pkgs[i].name);
            break;
        }
        chan_state s = st[i].state;
        int r;
        if (bulk != BULK_RESTORE && pkgs[i].remove_only) continue;
        if (s == ST_NA) {
            skipped++;
            add_name(skipped_names, sizeof skipped_names, pkgs[i].name);
            continue;
        }
        if (bulk == BULK_RESTORE) {
            r = do_restore(i, 1);
        } else {
            if (bulk == BULK_UPDATES && s != ST_UPDATE) continue;
            if (s == ST_LATEST) { unchanged++; continue; }
            if ((bulk == BULK_INSTALL && pkgs[i].experimental && !include_exp) || (unknown_state(s) && !include_unknown)) {
                skipped++;
                add_name(skipped_names, sizeof skipped_names, pkgs[i].name);
                continue;
            }
            r = do_install(i, 1);
        }
        if (r == 1) done++;
        else if (r == 0) unchanged++;
        else {
            failed++;
            add_name(failed_names, sizeof failed_names, pkgs[i].name);
        }
    }
    scan_all();
    log_scan(title[bulk]);
    say("\n  %s finished.\n  %d changed, %d already fine, %d skipped, %d failed.\n", title[bulk], done,
        unchanged, skipped, failed);
    if (skipped) say_names("  Skipped:", skipped_names);
    if (failed) {
        say_names("  FAILED:", failed_names);
        say("  (details: " BASE "/log.txt)\n");
    }
    wait_any();
}

static void bulk_menu(void)
{
    int c[ST_COUNT];
    scan_all();
    memset(c, 0, sizeof c);
    for (int i = 0; i < npkg; i++) c[st[i].state]++;
    printf("\n== All channels: %d update(s), %d not installed, %d up to date\n", c[ST_UPDATE], c[ST_ABSENT],
           c[ST_LATEST]);
    printf("  1(X): install / update all (channels already up to date are skipped)\n"
           "  A   : install updates only (%d channel(s))\n"
           "  2(Y): restore all channels to the state before KWCE\n"
           "  B   : cancel\n", c[ST_UPDATE]);
    int k = read_key();
    if (k == K_INSTALL) do_all(BULK_INSTALL);
    else if (k == K_A) do_all(BULK_UPDATES);
    else if (k == K_RESTORE) do_all(BULK_RESTORE);
}

static void channel_menu(int i)
{
    const package *p = &pkgs[i];
    int action = 0;
    for (;;) {
        char inst[160], folded[256], buf[64];
        int version = -1, before = state_before(p, &version);
        scan_one(i);
        describe_installed(i, inst, sizeof inst);
        printf("\x1b[2J\x1b[1;0H");
        printf("  %s   (%016llx)\n", p->name, (unsigned long long)p->tid);
        printf(RULE);
        printf("  On this console : %s\n", fold(folded, sizeof folded, inst, 20));
        if (files[i].have_korean)
            printf("  This package    : Korean build (%s), v%u, region %s\n", rel_name(release),
                   (unsigned)files[i].korean.version, region_name(files[i].korean.region));
        else
            printf("  This package    : Korean WAD missing on the SD card\n");
        if (files[i].have_original)
            printf("  Original on SD  : v%u, region %s\n", (unsigned)files[i].original.version,
                   region_name(files[i].original.region));
        else
            printf("  Original on SD  : none (restore removes the channel)\n");
        printf("  Status          : %s\n", state_text(i, buf, sizeof buf));
        if (before < 0) printf("  Before KWCE     : no record yet (written at the first change)\n");
        else if (before == 0) printf("  Before KWCE     : not installed -> restore removes the channel\n");
        else printf("  Before KWCE     : installed (v%d) -> restore reinstalls the original\n", version);
        if (p->experimental) printf("  Experimental    : yes (did not reach its main screen in emulator tests)\n");
        if (st[i].region_ok == 0)
            printf("  !! Installed region %s: this console's System Menu will not start it.\n",
                   region_name(st[i].inst.region));
        int n_ed = n_editions(i);
        const edition *e = sel_ed[i] ? edition_of(i, sel_ed[i]) : NULL;
        if (n_ed) {
            printf("  Edition (<- ->) : %d/%d %s\n", sel_ed[i] + 1, n_ed + 1,
                   e ? e->label : "standard Korean build (browse only)");
            if (e) printf("                    WiiLink real-order edition: real orders, English menus,\n"
                          "                    never tested by KWCE. %s\n", e->have ? "" : "(WAD missing on SD)");
        }
        printf(RULE);
        printf("  Step 1: Choose an action with Up/Down, then press A.\n");
        if (p->remove_only) printf("  %s Native DVD setup information (no channel install)\n", action == 0 ? ">" : " ");
        else printf("  %s Install / update%s\n", action == 0 ? ">" : " ", n_ed ? " selected edition" : " Korean build");
        printf("  %s Restore previous state (may remove channel)\n", action == 1 ? ">" : " ");
        printf("  %s Delete channel (keeps save data)\n", action == 2 ? ">" : " ");
        printf("  B: back | shortcuts: 1 install, 2 restore, - delete\n");
        int k = read_key();
        if ((k == K_LEFT || k == K_RIGHT) && n_ed) sel_ed[i] = (sel_ed[i] + (k == K_RIGHT ? 1 : n_ed)) % (n_ed + 1);
        else if (k == K_UP) action = (action + 2) % 3;
        else if (k == K_DOWN) action = (action + 1) % 3;
        else if (k == K_A) { if (action == 0) do_install(i, 0); else if (action == 1) do_restore(i, 0); else do_delete(i); }
        else if (k == K_INSTALL) do_install(i, 0);
        else if (k == K_RESTORE) do_restore(i, 0);
        else if (k == K_DISC) do_delete(i);
        else if (k == K_B || k == K_EXIT || k == K_SYS) return;
    }
}

/* Read-only snapshot for support: no console ids, no serial number. */
static void status_report(void)
{
    char path[96], buf[64], fp[17];
    int n = 1;
    for (; n < 100; n++) {
        snprintf(path, sizeof path, BASE "/status-%02d.txt", n);
        FILE *t = fopen(path, "rb");
        if (!t) break;
        fclose(t);
    }
    FILE *f = n < 100 ? fopen(path, "w") : NULL;
    if (!f) {
        say("  Could not create a status file in " BASE ".\n");
        return;
    }
    scan_all();
    fprintf(f, "KWCE channel status (read only; no console ids or serial number)\n");
    fprintf(f, "tool %s (release %d), IOS%d%s\n", VERSION, release, IOS_GetVersion(), cios_ok ? "" : " (test mode)");
    fprintf(f, "console %s, region %s, WiiLink %s\n", console_model_name(model), area_text(), wiilink_text());
    if (versions_n >= 0) fprintf(f, "version list: %d builds (release %d)\n", versions_n, versions_release());
    else fprintf(f, "version list: missing\n");
    fprintf(f, "channel|title|state|version|region|starts here|list entry|fingerprint|before KWCE\n");
    for (int i = 0; i < npkg; i++) {
        const chan_status *s = &st[i];
        int version = -1, before = state_before(&pkgs[i], &version);
        hex16(s->inst.fp, fp);
        fprintf(f, "%s|%016llx|%s|", pkgs[i].id, (unsigned long long)pkgs[i].tid, state_text(i, buf, sizeof buf));
        if (s->installed)
            fprintf(f, "%u|%s|%s|%s|%s|", (unsigned)s->inst.version, region_name(s->inst.region),
                    s->region_ok == 1 ? "yes" : s->region_ok == 0 ? "NO" : "?",
                    s->edition ? edition_of(i, s->edition)->key : s->known ? s->known->label : "-", fp);
        else
            fprintf(f, "-|-|-|-|-|");
        if (before < 0) fprintf(f, "no record\n");
        else if (before == 0) fprintf(f, "not installed\n");
        else fprintf(f, "installed v%d\n", version);
    }
    if (fclose(f) != 0) say("  Write error while saving %s.\n", path);
    else say("  Saved %s\n", path);
}

static void tools_menu(void)
{
    printf("\n== Tools\n"
           "  1(X): WiiLink setup (check, or copy the WiiLink Mail Patcher to apps/)\n"
           "  2(Y): save a WiiConnect24 status report (read only)\n"
           "  +(START): save a channel status report (read only)\n"
           "  B: back\n");
    int k = read_key();
    if (k == K_INSTALL) {
        wiilink_setup(0);
        wl_state = wiilink_state();
    } else if (k == K_RESTORE) {
        say("\n== WiiConnect24 status report (read only)\n"
            "  Open News / Forecast / Nintendo Channel first, then save this report.\n");
        wc24_report(model, VERSION);
        wait_any();
    } else if (k == K_ALL) {
        say("\n== Channel status report (read only)\n");
        status_report();
        wait_any();
    }
}

/* 0 = stay, 1 = Homebrew Channel, 2 = Wii Menu */
static int exit_menu(void)
{
    printf("\n  HOME again: back to the Homebrew Channel\n"
           "  A: go to the Wii Menu (to try the channels)\n"
           "  B: stay here\n");
    int k = read_key();
    if (k == K_EXIT || k == K_SYS) return 1;
    if (k == K_A) return 2;
    return 0;
}

/* ---- disc-channel mode (Priiloader hacks file on SD; no NAND write) ---------------
   The PC deploy tool builds two COMPLETE Priiloader files from the card's current
   hacks_hash.ini (every non-KWCE hack kept, only the KWCE disc sections replaced):
   kwce-rc/priiloader/gc-only.ini and gc-dvd.ini. This step backs up the active file
   and copies the chosen one over it. Priiloader itself still applies the hacks. */

#define PRII_FILE "sd:/apps/Priiloader/hacks_hash.ini"
#define PROFILE_MAX (512 * 1024)

static int load_file(const char *path, u8 **out, u32 *len)
{
    *out = NULL;
    *len = 0;
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    if (fseek(f, 0, SEEK_END)) { fclose(f); return -1; }
    long n = ftell(f);
    if (n <= 0 || n > PROFILE_MAX || fseek(f, 0, SEEK_SET)) { fclose(f); return -1; }
    u8 *buf = malloc((size_t)n);
    if (!buf) { fclose(f); return -1; }
    if (fread(buf, 1, (size_t)n, f) != (size_t)n) { free(buf); fclose(f); return -1; }
    fclose(f);
    *out = buf;
    *len = (u32)n;
    return 0;
}

/* Write, then read back; 0 only when the file on SD equals data. */
static int store_file(const char *path, const u8 *data, u32 len)
{
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    size_t written = fwrite(data, 1, len, f);
    if (fclose(f) != 0 || written != len) return -1;
    u8 *back = NULL;
    u32 blen = 0;
    if (load_file(path, &back, &blen) < 0) return -1;
    int same = blen == len && !memcmp(back, data, len);
    free(back);
    return same ? 0 : -1;
}

static int contains(const u8 *hay, u32 n, const char *needle)
{
    u32 m = (u32)strlen(needle);
    for (u32 i = 0; m && i + m <= n; i++)
        if (!memcmp(hay + i, needle, m)) return 1;
    return 0;
}

static int native_dvd_files_ready(void)
{
    int native = 0;
    for (int i = 0; i < npkg; ++i) if (pkgs[i].remove_only) native = 1;
    if (!native) return 1;
    const char *names[] = {"boot.ash", "player.dol", "menu.arc", "icon.arc", "home.arc", "wbf1.brfna"};
    for (unsigned i = 0; i < sizeof names / sizeof *names; ++i) {
        char path[96]; struct stat st;
        snprintf(path, sizeof path, "sd:/kwce/dvd/%s", names[i]);
        if (stat(path, &st) || !S_ISREG(st.st_mode) || st.st_size < 32 || st.st_size > 16*1024*1024) {
            say("  Native DVD resource missing or invalid: %s\n"
                "  Copy the complete RC package again. Nothing changed.\n", names[i]);
            return 0;
        }
    }
    say("  Native DVD resources found on SD. No DVD channel is required.\n"
        "  Keep this SD inserted; the loader verifies the player before launch.\n");
    return 1;
}

static void do_disc_profile(void)
{
    new_screen();
    say("\n== Disc channel mode (Priiloader hacks file)\n");
    if (!gc_ok) {
        say("  Not available: this console has no GameCube ports (channels only).\n");
        wait_any();
        return;
    }
    say("  1(X): GameCube only  - original two-disc layout, no DVD player\n"
        "  2(Y): GameCube + DVD - three-disc layout with the DVD player\n"
        "  B: cancel\n");
    int k;
    do k = read_key(); while (k != K_INSTALL && k != K_RESTORE && k != K_B && k != K_EXIT && k != K_SYS);
    if (k == K_B || k == K_EXIT || k == K_SYS) return;
    int gc_only = k == K_INSTALL;
    if (!gc_only && !native_dvd_files_ready()) { wait_any(); return; }
    const char *src = gc_only ? BASE "/priiloader/gc-only.ini" : BASE "/priiloader/gc-dvd.ini";
    const char *want = gc_only ? "[KWCE GC: GC-only disc layout (DVD off)]" : "[KWCE DVD: disc channel DVD player]";
    u8 *next = NULL, *cur = NULL;
    u32 nlen = 0, clen = 0;
    if (load_file(src, &next, &nlen) < 0 || next[0] != '['
        || !contains(next, nlen, "[KWCE GC: Wii/GC save menu]") || !contains(next, nlen, want)) {
        say("  This profile is missing or is not complete:\n  %s\n"
            "  Copy this package with the PC deploy tool; it builds the profile from\n"
            "  your current Priiloader file so your other hacks are kept.\n"
            "  Nothing changed.\n", src);
        free(next);
        wait_any();
        return;
    }
    int have = load_file(PRII_FILE, &cur, &clen) == 0;
    if (have && clen == nlen && !memcmp(cur, next, nlen)) {
        say("  This mode is already the active Priiloader file. Nothing changed.\n");
        free(cur);
        free(next);
        wait_any();
        return;
    }
    if (!confirm("Replace apps/Priiloader/hacks_hash.ini with this mode?\n  The current file is backed up first.")) {
        free(cur);
        free(next);
        return;
    }
    if (have) {
        char bak[96];
        int i = 1;
        mkdir(BASE "/priiloader/backup", 0777);
        for (; i < 100; i++) {
            snprintf(bak, sizeof bak, BASE "/priiloader/backup/hacks_hash-%02d.ini", i);
            FILE *t = fopen(bak, "rb");
            if (!t) break;
            fclose(t);
        }
        if (i >= 100 || store_file(bak, cur, clen) < 0) {
            say("  Could not back up the current Priiloader file. Nothing changed.\n");
            free(cur);
            free(next);
            wait_any();
            return;
        }
        say("  Backup: %s\n", bak);
    }
    if (store_file(PRII_FILE, next, nlen) < 0)
        say("  WRITE FAILED. On a PC, copy the backup above back to\n"
            "  apps/Priiloader/hacks_hash.ini.\n");
    else
        say("  Done (%u bytes).\n"
            "  Next: hold RESET while powering on to open Priiloader > System Menu\n"
            "  Hacks, check the KWCE GC entries and the %s entry,\n"
            "  then save.\n",
            nlen, gc_only ? "GC-only layout" : "DVD player");
    free(cur);
    free(next);
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
        /* id|title id (16 hex)|name|experimental|gamecube_only|remove_only */
        char *field[6];
        int n = 0;
        for (char *s = line; n < 6; n++) {
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
        p->remove_only = n >= 6 ? atoi(field[5]) : 0;
        if (!channel_title(p->tid)) { say("  Skipped non-channel title %08x\n", (u32)(p->tid >> 32)); continue; }
        npkg++;
    }
    fclose(f);
    return npkg;
}

static void draw(int sel)
{
    char buf[64];
    int c[ST_COUNT];
    memset(c, 0, sizeof c);
    for (int i = 0; i < npkg; i++) c[st[i].state]++;
    int want = console_tmd_region();
    printf("\x1b[2J\x1b[1;0H");
    printf("  KWCE channel installer %s   IOS%d%s\n", VERSION, IOS_GetVersion(), cios_ok ? "" : " (no cIOS: test mode)");
    printf("  Console: %s  Region: %s  WiiLink: %s\n", console_model_name(model), area_text(), wiilink_text());
    printf("  Updates %d   Not installed %d   Up to date %d   Original %d   Other %d\n", c[ST_UPDATE], c[ST_ABSENT],
           c[ST_LATEST], c[ST_ORIGINAL], c[ST_NEWER] + c[ST_KWCE_OTHER] + c[ST_OTHER]);
    if (want >= 0 && want != 4)
        printf("  !! This package is for Korean Wii consoles; its Korean channels\n"
               "     will not start here.\n");
    if (versions_n < 0)
        printf("  (No version list on SD: older Korean builds show as \"other version\".)\n");
    printf(RULE);
    for (int i = 0; i < npkg; i++)
        printf("  %s %-24.24s %-25.25s%s%s\n", i == sel ? ">" : " ", pkgs[i].name, state_text(i, buf, sizeof buf),
               st[i].region_ok == 0 ? " !REGION" : "", pkgs[i].experimental ? " [exp]" : "");
    printf(RULE);
    if (ned) printf("  %.30s editions (WiiLink real orders): A, then <- ->\n", pkgs[eds[0].pkg].name);
    printf("  A: channel menu   1(X): install/update   2(Y): restore   +(START): all\n");
    printf("  %s   B: tools   HOME (GC Z): exit\n", gc_ok ? "-(GC L): disc channel mode" : "(disc mode: n/a)");
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
    SYS_SetPowerCallback(on_power);
    SYS_SetResetCallback(on_reset);
    WPAD_SetPowerButtonCallback(on_remote_power);

    if (!fatInitDefault()) { printf("\n  SD card not found.\n"); wait_any(); return 0; }
    logfile = fopen(BASE "/log.txt", "a");
#ifdef KWCE_TEST_SCRIPT
    keyscript = fopen(BASE "/test-keys.txt", "r");
#endif
    release = release_of(VERSION);
    say("\n--- KWCE %s, IOS reload %d, running IOS%d\n", VERSION, reload, IOS_GetVersion());
    model = read_console_model();
    gc_ok = console_supports_gamecube(model);
    say("  Console model: %s, region %s\n", console_model_name(model), area_text());
    if (!cios_ok) {
        FILE *t = fopen(BASE "/allow-current-ios.txt", "r");
        if (t) { fclose(t); say("  Test mode: continuing without cIOS 249.\n"); }
        else { say("\n  cIOS 249 (d2x) could not be loaded. Nothing was changed.\n"); wait_any(); return 0; }
    }
    if (load_packages() <= 0) { say("\n  No packages in " BASE "/packages.txt\n"); wait_any(); return 0; }
    versions_n = versions_load(BASE "/versions.txt");
    if (versions_n >= 0)
        say("  Version list: %d builds (release %d).\n", versions_n, versions_release());
    else
        say("  Version list: %s; older builds show as \"other version\".\n",
            versions_n == -2 ? "unknown format" : "missing");
    load_editions();
    load_files();
    log_files();
    scan_all();
    log_scan("start");
    /* An installed edition stays the choice; a listed older edition build ("RCn <key>") too. */
    for (int i = 0; i < npkg; i++) {
        sel_ed[i] = st[i].edition;
        const char *sp = !sel_ed[i] && st[i].known && st[i].known->kind == 'K' ? strchr(st[i].known->label, ' ') : NULL;
        for (int k = 1; sp && k <= n_editions(i); k++)
            if (!strcmp(edition_of(i, k)->key, sp + 1)) sel_ed[i] = k;
    }

    /* WiiLink: silent when detected or answered before (kwce-rc/wiilink-skip.txt); otherwise asked
       once, never blocking the installer. B (tools) > 1 opens it again on request. */
    wl_state = wiilink_state();
    if (wl_state != 1) {
        wiilink_setup(1);
        wl_state = wiilink_state();
    }

    int sel = 0, leave = 0;
    while (!leave) {
        draw(sel);
        int k = read_key();
        if (k == K_UP) sel = (sel + npkg - 1) % npkg;
        else if (k == K_DOWN) sel = (sel + 1) % npkg;
        else if (k == K_A) channel_menu(sel);
        else if (k == K_INSTALL) do_install(sel, 0);
        else if (k == K_RESTORE) do_restore(sel, 0);
        else if (k == K_ALL) bulk_menu();
        else if (k == K_DISC) do_disc_profile();
        else if (k == K_B) tools_menu();
        else if (k == K_EXIT) leave = exit_menu();
        else if (k == K_SYS) leave = 1;
    }
    say("--- exit: %s\n", power_req ? "POWER pressed" : leave == 2 ? "Wii Menu" : "Homebrew Channel");
    if (logfile) fclose(logfile);
    fatUnmount("sd:");
#ifdef KWCE_TEST_SCRIPT
    /* Emulator test build: stay on a silent black screen until the harness stops Dolphin. */
    if (keyscript) for (;;) VIDEO_WaitVSync();
#endif
    WPAD_Shutdown();
    if (power_req) SYS_ResetSystem(SYS_POWEROFF, 0, 0);
    if (leave == 2) SYS_ResetSystem(SYS_RETURNTOMENU, 0, 0);
    return 0;
}

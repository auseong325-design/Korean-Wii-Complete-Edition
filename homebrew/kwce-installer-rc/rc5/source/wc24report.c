/*
 * Read-only WiiConnect24 status snapshot for the KWCE RC installer.
 *
 * News, the Forecast banner and the Nintendo Channel all depend on the console's
 * WiiConnect24 download tasks; RC1/RC2 hardware tests showed no task for News. This
 * report tells, after the user has opened those channels, whether the console's WC24
 * setup can hold tasks at all. It READS /shared2/wc24/nwc24msg.cfg and nwc24dl.bin and
 * writes one text file to SD (kwce-rc/wc24-NN.txt). Nothing is written to NAND.
 *
 * Privacy: it never prints the WC24 id, the e-mail user part, the password, the mail
 * check id, any URL path/query, or the ids of non-KWCE titles. Only counts, the
 * creation stage, the mail domain, URL host names and the KWCE channels' own task state.
 */
#include <gccore.h>
#include <ogc/conf.h>
#include <ogc/isfs.h>
#include <malloc.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

#include "kwce.h"

#define REPORT_BASE "sd:/kwce-rc"
#define DL_BYTES 0xf800u
#define CFG_BYTES 0x400u
#define DL_ENTRIES 120u

static unsigned be16(const u8 *p) { return ((unsigned)p[0] << 8) | p[1]; }
static unsigned be32(const u8 *p)
{
    return ((unsigned)p[0] << 24) | ((unsigned)p[1] << 16) | ((unsigned)p[2] << 8) | p[3];
}

static s32 read_nand(const char *path, u8 *buf, u32 len)
{
    s32 fd = ISFS_Open(path, ISFS_OPEN_READ);
    if (fd < 0) return fd;
    s32 n = ISFS_Read(fd, buf, len);
    ISFS_Close(fd);
    return n;
}

static int host_char(char c)
{
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' || c == '-';
}

/* Host name of an http(s) URL field, or "none"/"unrecognized"; never the path or query. */
static void url_host(const u8 *field, char *out, size_t outn)
{
    const char *s = (const char *)field;
    size_t skip = 0;
    if (!strncmp(s, "http://", 7)) skip = 7;
    else if (!strncmp(s, "https://", 8)) skip = 8;
    if (!skip) { snprintf(out, outn, "%s", field[0] ? "unrecognized" : "none"); return; }
    size_t n = 0;
    for (size_t i = skip; i < 0x80 && host_char(s[i]) && n + 1 < outn && n < 63; i++) out[n++] = s[i];
    out[n] = 0;
    if (!n) snprintf(out, outn, "unrecognized");
}

/* Part after '@' of the 64-byte e-mail field; the user part (WC24 id) is never copied. */
static void mail_domain(const u8 *field, char *out, size_t outn)
{
    const char *at = memchr(field, '@', 0x40);
    size_t n = 0;
    if (at)
        for (const char *p = at + 1; p < (const char *)field + 0x40 && host_char(*p) && n + 1 < outn && n < 40; p++)
            out[n++] = *p;
    out[n] = 0;
    if (!n) snprintf(out, outn, "none");
}

static const char *kwce_channel(unsigned hi, unsigned lo)
{
    if (hi == 0x00010002 && lo == 0x48414745) return "news";
    if (hi == 0x00010002 && lo == 0x48414645) return "forecast";
    if (hi == 0x00010001 && lo == 0x48415445) return "nintendo";
    if (hi == 0x00010001 && lo == 0x48414a45) return "votes";
    if (hi == 0x00010001 && lo == 0x48415045) return "mii_contest";
    if (hi == 0x00010001 && lo == 0x4843494a) return "wii_room";
    if (hi == 0x00010001 && lo == 0x48424e4a) return "tv_guide";
    return NULL;
}

static void config_part(FILE *f)
{
    u8 *cfg = memalign(32, CFG_BYTES);
    if (!cfg) { fprintf(f, "msgcfg_result=allocation_failed\n"); return; }
    s32 n = read_nand("/shared2/wc24/nwc24msg.cfg", cfg, CFG_BYTES);
    fprintf(f, "msgcfg_read_result=%d\n", (int)n);
    if (n == (s32)CFG_BYTES && be32(cfg) == 0x57634366) {
        char text[72];
        fprintf(f, "msgcfg_format=recognized\nmsgcfg_version=%u\n", be32(cfg + 4));
        unsigned stage = be32(cfg + 0x14);
        fprintf(f, "id_creation_stage=%u (%s)\n", stage,
                stage == 0 ? "initial: no id" : stage == 1 ? "generated, not registered" :
                stage == 2 ? "registered" : "unknown");
        mail_domain(cfg + 0x18, text, sizeof text);
        fprintf(f, "mail_domain=%s\n", text);
        static const char *names[5] = { "account", "check", "receive", "delete", "send" };
        for (int i = 0; i < 5; i++) {
            url_host(cfg + 0x9c + 0x80 * i, text, sizeof text);
            fprintf(f, "%s_host=%s\n", names[i], text);
        }
        fprintf(f, "enable_booting=%u\n", be32(cfg + 0x3f8));
    } else {
        fprintf(f, "msgcfg_format=missing_or_unrecognized\n");
    }
    memset(cfg, 0, CFG_BYTES);
    free(cfg);
}

static void tasks_part(FILE *f)
{
    u8 *dl = memalign(32, DL_BYTES);
    if (!dl) { fprintf(f, "dllist_result=allocation_failed\n"); return; }
    s32 n = read_nand("/shared2/wc24/nwc24dl.bin", dl, DL_BYTES);
    fprintf(f, "dllist_read_result=%d\n", (int)n);
    if (n != (s32)DL_BYTES || be32(dl) != 0x5763446c || be32(dl + 4) != 1) {
        fprintf(f, "dllist_format=missing_or_unrecognized\n");
        free(dl);
        return;
    }
    unsigned used = 0, kwce = 0;
    for (unsigned i = 0; i < DL_ENTRIES; i++) {
        const u8 *e = dl + 2048 + 512 * i;
        unsigned hi = be32(e + 8), lo = be32(e + 12);
        if (!hi && !lo) continue;
        used++;
        const char *name = kwce_channel(hi, lo);
        if (!name) continue;
        fprintf(f, "task_%u_channel=%s\n", kwce, name);
        fprintf(f, "task_%u_flags=%u\n", kwce, be32(e + 4));
        fprintf(f, "task_%u_remaining_downloads=%u\n", kwce, be16(e + 24));
        fprintf(f, "task_%u_error_count=%u\n", kwce, be16(e + 26));
        fprintf(f, "task_%u_retry_minutes=%u\n", kwce, be16(e + 30));
        fprintf(f, "task_%u_error_code=%d\n", kwce, (int)(s32)be32(e + 32));
        fprintf(f, "task_%u_subtask_mask=%u\n", kwce, be32(e + 40));
        fprintf(f, "task_%u_last_download_minutes_2000=%u\n", kwce, be32(e + 48));
        kwce++;
    }
    fprintf(f, "dllist_format=recognized_v1\ntasks_used=%u\ntasks_free=%u\nkwce_tasks=%u\n",
            used, DL_ENTRIES - used, kwce);
    free(dl);
}

int wc24_report(console_model model, const char *version)
{
    char path[64];
    FILE *f = NULL;
    for (int i = 1; i < 100; i++) {
        snprintf(path, sizeof path, REPORT_BASE "/wc24-%02d.txt", i);
        FILE *old = fopen(path, "rb");
        if (old) { fclose(old); continue; }
        f = fopen(path, "wb");
        break;
    }
    if (!f) { say("  Cannot create a report file in " REPORT_BASE ".\n"); return -1; }
    fprintf(f, "KWCE_RC_WC24_REPORT_V1\ninstaller=%s\nconsole=%s\n", version, console_model_name(model));
    s32 isfs = ISFS_Initialize();
    fprintf(f, "isfs_init=%d\n", (int)isfs);
    s32 c = CONF_Init();
    fprintf(f, "conf_init=%d\n", (int)c);
    if (c >= 0)
        fprintf(f, "area=%d\nlanguage=%d\nwc24_enabled=%d\n", CONF_GetArea(), CONF_GetLanguage(),
                CONF_GetWiiConnect24());
    if (isfs >= 0) {
        config_part(f);
        tasks_part(f);
        ISFS_Deinitialize();
    }
    int bad = fflush(f) != 0 || ferror(f);
    if (fclose(f) != 0) bad = 1;
    if (bad) { say("  Report write failed: %s\n", path); return -1; }
    say("  Saved %s (read only; no ids, passwords or URL paths).\n", path);
    return 0;
}

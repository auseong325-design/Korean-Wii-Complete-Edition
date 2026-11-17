/*
 * WiiLink detection and optional WiiLink Mail Patcher setup for the KWCE RC installer.
 *
 * Detection reads /shared2/wc24/nwc24msg.cfg (read only). A console counts as set up for WiiLink
 * when its WiiConnect24 id is registered (creation stage 2) AND both the mail domain and the
 * account URL host belong to WiiLink / RiiConnect24 (rc24.xyz, wiilink*). This is the same
 * state the Mail Patcher itself produces. If it is set up, nothing is offered.
 * WiiLink used through DNS or patched channels leaves Nintendo's hosts in that file, so it cannot
 * be seen here. The start-up question is therefore asked once: every answer is kept in
 * sd:/kwce-rc/wiilink-skip.txt, and B (tools) > 1 opens the question again on request.
 *
 * If it is not, the user may copy the bundled, unmodified WiiLink Mail Patcher (GPLv3, see its
 * LICENSE and SOURCE.txt) from sd:/kwce-rc/extras into sd:/apps so it shows up in the Homebrew
 * Channel. This file only copies files on the SD card and verifies them by read-back; the
 * Mail Patcher itself is run by the user and talks to WiiLink on its own.
 */
#include <gccore.h>
#include <ogc/isfs.h>
#include <malloc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include "kwce.h"

#define CFG_BYTES 0x400u
#define EXTRA_SRC "sd:/kwce-rc/extras/wiilink-mail-patcher"
#define EXTRA_DST "sd:/apps/WiiLink-Mail-Patcher"
#define COPY_CHUNK (64 * 1024)

static unsigned be32(const u8 *p)
{
    return ((unsigned)p[0] << 24) | ((unsigned)p[1] << 16) | ((unsigned)p[2] << 8) | p[3];
}

static int wiilink_name(const char *s)
{
    return strstr(s, "rc24.xyz") != NULL || strstr(s, "wiilink") != NULL;
}

int wiilink_state(void)
{
    int state = -1;
    u8 *cfg = memalign(32, CFG_BYTES);
    if (!cfg) return -1;
    if (ISFS_Initialize() >= 0) {
        s32 fd = ISFS_Open("/shared2/wc24/nwc24msg.cfg", ISFS_OPEN_READ);
        if (fd >= 0) {
            s32 n = ISFS_Read(fd, cfg, CFG_BYTES);
            ISFS_Close(fd);
            if (n == (s32)CFG_BYTES && be32(cfg) == 0x57634366) {
                char mail[0x41], account[0x81];
                memcpy(mail, cfg + 0x18, 0x40);
                mail[0x40] = 0;
                memcpy(account, cfg + 0x9c, 0x80);
                account[0x80] = 0;
                const char *at = strchr(mail, '@');
                int domain_ok = at != NULL && wiilink_name(at + 1);
                state = (be32(cfg + 0x14) == 2 && domain_ok && wiilink_name(account)) ? 1 : 0;
            }
        }
        ISFS_Deinitialize();
    }
    memset(cfg, 0, CFG_BYTES);
    free(cfg);
    return state;
}

static int file_exists(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f) return 0;
    fclose(f);
    return 1;
}

static int copy_file(const char *src, const char *dst)
{
    FILE *in = fopen(src, "rb");
    if (!in) return -1;
    FILE *out = fopen(dst, "wb");
    if (!out) { fclose(in); return -1; }
    u8 *buf = memalign(32, COPY_CHUNK);
    int ok = buf != NULL;
    size_t n;
    while (ok && (n = fread(buf, 1, COPY_CHUNK, in)) > 0)
        if (fwrite(buf, 1, n, out) != n) ok = 0;
    if (ferror(in)) ok = 0;
    fclose(in);
    if (fclose(out) != 0) ok = 0;
    free(buf);
    return ok ? 0 : -1;
}

static int same_file(const char *a, const char *b)
{
    FILE *fa = fopen(a, "rb"), *fb = fopen(b, "rb");
    u8 *x = memalign(32, COPY_CHUNK), *y = memalign(32, COPY_CHUNK);
    int same = fa && fb && x && y;
    while (same) {
        size_t na = fread(x, 1, COPY_CHUNK, fa), nb = fread(y, 1, COPY_CHUNK, fb);
        if (na != nb || memcmp(x, y, na)) same = 0;
        if (na == 0) break;
    }
    if (fa) fclose(fa);
    if (fb) fclose(fb);
    free(x);
    free(y);
    return same;
}

static int install_mail_patcher(void)
{
    static const char *names[] = { "boot.dol", "meta.xml", "icon.png", "LICENSE", "SOURCE.txt", "source.zip" };
    char src[96], dst[96];
    mkdir("sd:/apps", 0777);
    mkdir(EXTRA_DST, 0777);
    for (unsigned i = 0; i < sizeof names / sizeof names[0]; i++) {
        snprintf(src, sizeof src, EXTRA_SRC "/%s", names[i]);
        snprintf(dst, sizeof dst, EXTRA_DST "/%s", names[i]);
        if (!file_exists(src)) {
            if (i < 3) { say("  Missing %s\n", src); return -1; }
            continue;
        }
        if (file_exists(dst) && same_file(src, dst)) { say("  %s: already up to date\n", names[i]); continue; }
        if (copy_file(src, dst) < 0 || !same_file(src, dst)) { say("  Copy failed: %s\n", names[i]); return -1; }
        say("  %s copied and verified\n", names[i]);
    }
    return 0;
}

/* Any file here means the start-up question was answered (RC5 wrote it empty, and only for B). */
#define SKIP_MARK "sd:/kwce-rc/wiilink-skip.txt"

/* Writes the answer into SKIP_MARK and reads it back; 0 = saved. */
static int save_answer(const char *answer)
{
    char line[128], back[128];
    int n = snprintf(line, sizeof line, "KWCE WiiLink question answered: %s. Delete this file to be asked again.\n",
                     answer);
    if (n <= 0 || n >= (int)sizeof line) return -1;
    FILE *f = fopen(SKIP_MARK, "wb");
    if (!f) return -1;
    int ok = fwrite(line, 1, (size_t)n, f) == (size_t)n;
    if (fclose(f) != 0) ok = 0;
    if (!ok || !(f = fopen(SKIP_MARK, "rb"))) return -1;
    ok = fread(back, 1, sizeof back, f) == (size_t)n && !memcmp(back, line, (size_t)n);
    fclose(f);
    return ok ? 0 : -1;
}

static void keep_answer(const char *answer)
{
    if (save_answer(answer) == 0)
        say("  Answer saved on the SD card: this question will not appear at start-up\n"
            "  again. To open it later: B (tools) > 1 on the main screen.\n");
    else
        say("  This answer could not be saved on the SD card (locked or full?), so the\n"
            "  question may appear again. Installing channels works either way.\n");
}

void wiilink_setup(int startup)
{
    if (startup && file_exists(SKIP_MARK)) return;   /* answered before (any content, even empty) */
    int state = wiilink_state();
    say("\n== WiiLink setup (optional)\n");
    if (state == 1) {
        say("  WiiLink mail settings found on this console. Nothing to do.\n");
        if (!startup) wait_any();
        return;
    }
    if (state < 0)
        say("  The WiiConnect24 mail settings could not be read.\n");
    else
        say("  This console's WiiConnect24 mail settings do not point to WiiLink.\n");
    say("  That is normal if WiiLink was set up with DNS or patched channels: this\n"
        "  check only sees the WiiLink Mail Patcher. Installing channels works\n"
        "  either way; KWCE does not change these settings itself.\n");
    if (!file_exists(EXTRA_SRC "/boot.dol")) {
        say("  The WiiLink Mail Patcher is not in this package. It is available at\n"
            "  https://github.com/WiiLink24/Mail-Patcher - copy it to apps/ and run it\n"
            "  from the Homebrew Channel.\n");
        keep_answer("no Mail Patcher in this package");
        wait_any();
        return;
    }
    say("\n  A: copy the WiiLink Mail Patcher (unmodified, GPLv3) to apps/\n"
        "  B: continue without it (choose this if you already use WiiLink)\n"
        "  Either answer is saved, so this is not asked again at start-up.\n");
    int k = choose_ab();
    if (k < 0) return;                     /* POWER / RESET: the tool closes, nothing is saved */
    if (k == 0) {
        say("  Continuing without the Mail Patcher.\n");
        keep_answer("continue without the Mail Patcher");
    } else if (install_mail_patcher() < 0) {
        say("  The Mail Patcher could not be copied. Nothing else was changed.\n");
        keep_answer("Mail Patcher copy failed");
    } else {
        say("\n  Done. To use it: exit with HOME, open the Homebrew Channel and run\n"
            "  \"WiiLink Mail Patcher\" (it contacts WiiLink only when YOU run it).\n");
        keep_answer("Mail Patcher copied to apps/");
    }
    wait_any();
}

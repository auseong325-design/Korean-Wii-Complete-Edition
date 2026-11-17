/*
 * WiiLink detection and optional WiiLink Mail Patcher setup for the KWCE RC installer.
 *
 * Detection reads /shared2/wc24/nwc24msg.cfg (read only). A console counts as set up for WiiLink
 * when its WiiConnect24 id is registered (creation stage 2) AND both the mail domain and the
 * account URL host belong to WiiLink / RiiConnect24 (rc24.xyz, wiilink*). This is the same
 * state the Mail Patcher itself produces. If it is set up, nothing is offered.
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

#define SKIP_MARK "sd:/kwce-rc/wiilink-skip.txt"

void wiilink_setup(int startup)
{
    int state = wiilink_state();
    if (startup && file_exists(SKIP_MARK)) return;   /* the user already chose to skip */
    say("\n== WiiLink setup\n");
    if (state == 1) {
        say("  WiiLink is already set up on this console. Nothing to do.\n");
        return;
    }
    if (state < 0)
        say("  The WiiConnect24 settings could not be read, so the WiiLink state is unknown.\n");
    else
        say("  This console's WiiConnect24 settings do not point to WiiLink.\n");
    say("  The online channels (News, Forecast, Nintendo Channel, Wii Room, Everybody Votes, ...)\n"
        "  depend on WiiLink. KWCE does not change those settings itself.\n");
    if (!file_exists(EXTRA_SRC "/boot.dol")) {
        say("  The WiiLink Mail Patcher is not in this package. Get it from\n"
            "  https://github.com/WiiLink24/Mail-Patcher , copy it to apps/ and run it from the\n"
            "  Homebrew Channel, then start this tool again.\n");
        wait_any();
        return;
    }
    if (!confirm("Copy the WiiLink Mail Patcher into the Homebrew Channel (apps/WiiLink-Mail-Patcher)?\n"
                 "  It is unmodified WiiLink software (GPLv3). B = skip and continue without WiiLink.")) {
        FILE *m = fopen(SKIP_MARK, "wb");
        if (m) fclose(m);
        say("  Skipped. This question will not appear at start-up again.\n"
            "  You can still open it later: B (tools) > 1 on the main screen.\n");
        return;
    }
    if (install_mail_patcher() < 0) {
        say("  The Mail Patcher could not be copied. Nothing else was changed.\n");
    } else {
        say("\n  Done. Exit with HOME, open the Homebrew Channel, run \"WiiLink Mail Patcher\" and follow\n"
            "  its screens (it contacts WiiLink when YOU run it). Then start this tool again;\n"
            "  once WiiLink is detected this question no longer appears.\n");
    }
    wait_any();
}

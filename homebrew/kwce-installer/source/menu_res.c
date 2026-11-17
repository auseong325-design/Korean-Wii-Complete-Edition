/*
 * System Menu GC resources (43K v518 content 0000009d.app), theme-installer style.
 *
 * Only the resource archive file is replaced; the menu executable, its TMD,
 * Priiloader and IOS are not touched. The current file must be the exact
 * original (SHA-1 from sd:/kwce/menu/resource.txt) before anything is
 * written; it is first backed up to sd:/kwce/menu/backup-0000009d.app and
 * re-read. The new file is written to /tmp, verified, then swapped in with
 * the original attributes and verified again. Restore writes the backup back
 * the same way. A resource from an earlier KWCE package (previous_sha1= in
 * resource.txt) is replaced directly when the verified original backup made
 * by that first install is on the SD card. If the menu ever fails to start, hold RESET at power-on for
 * Priiloader, start the Homebrew Channel and use "restore" here.
 */
#include <gccore.h>
#include <malloc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include "kwce.h"

#define MENU_DIR "sd:/kwce/menu"
#define NAND_RES "/title/00000001/00000002/content/0000009d.app"
/* IOS only renames across directories when the file names are equal. */
#define NAND_TMP "/tmp/0000009d.app"
#define BLOCK (64 * 1024)

/* ---- SHA-1 (FIPS 180-1) ---- */
static u32 rol(u32 v, int n) { return (v << n) | (v >> (32 - n)); }

static void sha1_digest(const u8 *data, u32 len, u8 out[20])
{
    u32 h[5] = {0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0};
    u64 bits = (u64)len * 8;
    u32 total = ((len + 8) / 64 + 1) * 64;
    for (u32 block = 0; block < total; block += 64) {
        u8 chunk[64];
        for (int i = 0; i < 64; i++) {
            u32 at = block + i;
            if (at < len) chunk[i] = data[at];
            else if (at == len) chunk[i] = 0x80;
            else if (at >= total - 8) chunk[i] = (u8)(bits >> (8 * (total - 1 - at)));
            else chunk[i] = 0;
        }
        u32 w[80];
        for (int i = 0; i < 16; i++) w[i] = (chunk[4 * i] << 24) | (chunk[4 * i + 1] << 16) | (chunk[4 * i + 2] << 8) | chunk[4 * i + 3];
        for (int i = 16; i < 80; i++) w[i] = rol(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
        u32 a = h[0], b = h[1], c = h[2], d = h[3], e = h[4];
        for (int i = 0; i < 80; i++) {
            u32 f, k;
            if (i < 20) { f = (b & c) | (~b & d); k = 0x5A827999; }
            else if (i < 40) { f = b ^ c ^ d; k = 0x6ED9EBA1; }
            else if (i < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8F1BBCDC; }
            else { f = b ^ c ^ d; k = 0xCA62C1D6; }
            u32 t = rol(a, 5) + f + e + k + w[i];
            e = d; d = c; c = rol(b, 30); b = a; a = t;
        }
        h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e;
    }
    for (int i = 0; i < 20; i++) out[i] = (u8)(h[i / 4] >> (24 - 8 * (i % 4)));
}

static void hex(const u8 d[20], char out[41])
{
    for (int i = 0; i < 20; i++) sprintf(out + 2 * i, "%02x", d[i]);
}

static int sha_is(const u8 *data, u32 len, const char *expect)
{
    u8 d[20];
    char h[41];
    sha1_digest(data, len, d);
    hex(d, h);
    return strcmp(h, expect) == 0;
}

/* ---- files ---- */
static char want_original[41], want_patched[41];
#define MAX_PREVIOUS 4
static char want_previous[MAX_PREVIOUS][41];
static int npre;

static int load_config(void)
{
    FILE *f = fopen(MENU_DIR "/resource.txt", "r");
    if (!f) return -1;
    char line[128];
    while (fgets(line, sizeof line, f)) {
        line[strcspn(line, "\r\n")] = 0;
        if (!strncmp(line, "original_sha1=", 14)) snprintf(want_original, sizeof want_original, "%.40s", line + 14);
        if (!strncmp(line, "patched_sha1=", 13)) snprintf(want_patched, sizeof want_patched, "%.40s", line + 13);
        if (!strncmp(line, "previous_sha1=", 14) && npre < MAX_PREVIOUS && strlen(line + 14) == 40)
            snprintf(want_previous[npre++], sizeof want_previous[0], "%.40s", line + 14);
    }
    fclose(f);
    return strlen(want_original) == 40 && strlen(want_patched) == 40 ? 0 : -1;
}

static u8 *read_sd(const char *path, u32 *len)
{
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    u8 *buf = n > 0 && n < 32 * 1024 * 1024 ? memalign(32, (n + 31) & ~31) : NULL;
    if (buf && fread(buf, 1, n, f) != (size_t)n) { free(buf); buf = NULL; }
    fclose(f);
    if (buf) *len = (u32)n;
    return buf;
}

static int write_sd(const char *path, const u8 *data, u32 len)
{
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    int ok = fwrite(data, 1, len, f) == len;
    fclose(f);
    return ok ? 0 : -1;
}

static u8 *read_nand(const char *path, u32 *len)
{
    static fstats st ATTRIBUTE_ALIGN(32);
    s32 fd = ISFS_Open(path, ISFS_OPEN_READ);
    if (fd < 0) return NULL;
    u8 *buf = NULL;
    if (ISFS_GetFileStats(fd, &st) >= 0 && st.file_length && st.file_length < 32 * 1024 * 1024) {
        buf = memalign(32, (st.file_length + 31) & ~31);
        u32 done = 0;
        while (buf && done < st.file_length) {
            u32 n = st.file_length - done < BLOCK ? st.file_length - done : BLOCK;
            if (ISFS_Read(fd, buf + done, n) != (s32)n) { free(buf); buf = NULL; break; }
            done += n;
        }
        if (buf) *len = st.file_length;
    }
    ISFS_Close(fd);
    return buf;
}

static int nand_matches(const char *path, const char *expect)
{
    u32 len = 0;
    u8 *buf = read_nand(path, &len);
    if (!buf) return 0;
    int ok = sha_is(buf, len, expect);
    free(buf);
    return ok;
}

/* Write data to /tmp, verify, swap into place keeping attributes, verify again. */
static int replace_resource(const u8 *data, u32 len, const char *expect)
{
    /* Attributes of the installed file (or the menu defaults when it is missing). */
    u32 owner = 0; u16 group = 0; u8 attr = 0, op = 3, gp = 3, otp = 1;
    s32 r = ISFS_GetAttr(NAND_RES, &owner, &group, &attr, &op, &gp, &otp);
    if (r < 0) say("  Resource attributes unavailable (%d); using system defaults.\n", r);
    ISFS_Delete(NAND_TMP);
    r = ISFS_CreateFile(NAND_TMP, 0, 3, 3, 1);
    if (r < 0) { say("  Cannot create %s (%d). Nothing changed.\n", NAND_TMP, r); return -1; }
    s32 fd = ISFS_Open(NAND_TMP, ISFS_OPEN_WRITE);
    u8 *chunk = memalign(32, BLOCK);
    if (fd < 0 || !chunk) { say("  Cannot open the temporary file (%d). Nothing changed.\n", fd); if (fd >= 0) ISFS_Close(fd); free(chunk); ISFS_Delete(NAND_TMP); return -1; }
    for (u32 done = 0; done < len;) {
        u32 n = len - done < BLOCK ? len - done : BLOCK;
        memcpy(chunk, data + done, n);
        if (ISFS_Write(fd, chunk, n) != (s32)n) { say("  NAND write failed. Nothing changed.\n"); ISFS_Close(fd); free(chunk); ISFS_Delete(NAND_TMP); return -1; }
        done += n;
    }
    ISFS_Close(fd);
    free(chunk);
    if (!nand_matches(NAND_TMP, expect)) { say("  Temporary copy does not verify. Nothing changed.\n"); ISFS_Delete(NAND_TMP); return -1; }
    say("  Swapping the resource file...\n");
    /* Rename replaces the destination; the old file is only removed if that is refused. */
    r = ISFS_Rename(NAND_TMP, NAND_RES);
    if (r < 0) {
        say("  Direct replace refused (%d); removing the old file first.\n", r);
        s32 d = ISFS_Delete(NAND_RES);
        r = ISFS_Rename(NAND_TMP, NAND_RES);
        if (r < 0) {
            say("  Rename failed (%d, delete %d)! Run restore now (do not power off).\n", r, d);
            return -2;
        }
    }
    ISFS_SetAttr(NAND_RES, owner, group, attr, op, gp, otp);
    if (!nand_matches(NAND_RES, expect)) { say("  Final verification FAILED. Use restore before powering off.\n"); return -2; }
    say("  Verified.\n");
    return 0;
}

/* ---- menu entry ---- */
static int is_previous(const u8 *data, u32 len)
{
    for (int i = 0; i < npre; i++)
        if (sha_is(data, len, want_previous[i])) return 1;
    return 0;
}

int menu_available(void)
{
    struct stat s;
    return stat(MENU_DIR, &s) == 0 && load_config() == 0;
}

const char *menu_state(void)
{
    u32 len = 0;
    u8 *buf = read_nand(NAND_RES, &len);
    if (!buf) return "unreadable";
    const char *s = sha_is(buf, len, want_patched) ? "KWCE" : sha_is(buf, len, want_original) ? "original"
                  : is_previous(buf, len) ? "older KWCE" : "unknown";
    free(buf);
    return s;
}

void menu_install(void)
{
    u32 len = 0, blen = 0;
    say("\n== System Menu GC visuals (resource file only)\n");
    u8 *cur = read_nand(NAND_RES, &len);
    if (!cur) { say("  Cannot read %s. Nothing changed.\n", NAND_RES); wait_any(); return; }
    if (sha_is(cur, len, want_patched)) { say("  Already installed.\n"); free(cur); wait_any(); return; }
    int older = is_previous(cur, len);
    if (!older && !sha_is(cur, len, want_original)) { say("  The installed file is not the expected original 4.3K resource. Nothing changed.\n"); free(cur); wait_any(); return; }
    u8 *bak = read_sd(MENU_DIR "/backup-0000009d.app", &blen);
    if (older && (!bak || !sha_is(bak, blen, want_original))) {
        /* the backup of the original was made when the older KWCE resource went in */
        say("  An older KWCE resource is installed but the SD backup of the original is missing. Nothing changed.\n");
        free(bak); free(cur); wait_any(); return;
    }
    if (older) say("  Older KWCE resource found; the SD backup of the original verifies.\n");
    if (!bak || !sha_is(bak, blen, want_original)) {
        free(bak);
        if (write_sd(MENU_DIR "/backup-0000009d.app", cur, len) < 0) { say("  Cannot write the SD backup. Nothing changed.\n"); free(cur); wait_any(); return; }
        bak = read_sd(MENU_DIR "/backup-0000009d.app", &blen);
        if (!bak || !sha_is(bak, blen, want_original)) { say("  SD backup does not verify. Nothing changed.\n"); free(bak); free(cur); wait_any(); return; }
        say("  Backed up the original resource to " MENU_DIR "/backup-0000009d.app\n");
    }
    free(bak);
    free(cur);
    u32 plen = 0;
    u8 *patched = read_sd(MENU_DIR "/kwce-0000009d.app", &plen);
    if (!patched || !sha_is(patched, plen, want_patched)) { say("  Package resource missing or damaged. Nothing changed.\n"); free(patched); wait_any(); return; }
    if (confirm("Replace the System Menu resource file? Do not power off.")) replace_resource(patched, plen, want_patched);
    free(patched);
    wait_any();
}

void menu_restore(void)
{
    u32 len = 0;
    say("\n== Restore System Menu resource\n");
    u8 *bak = read_sd(MENU_DIR "/backup-0000009d.app", &len);
    if (!bak || !sha_is(bak, len, want_original)) { say("  No verified SD backup. Nothing changed.\n"); free(bak); wait_any(); return; }
    if (nand_matches(NAND_RES, want_original)) { say("  The original resource is already installed.\n"); free(bak); wait_any(); return; }
    if (confirm("Write the original resource back? Do not power off.")) replace_resource(bak, len, want_original);
    free(bak);
    wait_any();
}

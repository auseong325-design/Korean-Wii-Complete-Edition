/*
 * Optional "GameCube pictures" (1.0.10): System Menu 4.3K v518 resource content 0000009d.app,
 * theme-installer style. The only NAND file this app may write; the build refuses NAND write
 * symbols in every other source file (kwce/rc_hardware.py).
 *
 * Without it the Priiloader hacks restore the GameCube functions but the Korean resource has no
 * GameCube memory-card picture on the Data Management / Save Data tiles and no two-line
 * "Nintendo GameCube" label. The KWCE resource (from the 1.0 alpha, in use on the owner console
 * since 2026-10) changes three files inside it: diskBann2.ash, setupSel2.ash, ipl_common.bmg.
 *
 * Refused unless: the console has GameCube ports, Priiloader is installed (the renamed menu boot
 * content 1xxxxxxx.app exists, as Priiloader 0.10.0 SystemMenu.cpp looks it up) so the console
 * can always reach the Homebrew Channel and this restore, and the installed file is exactly the
 * 4.3K original. The original is backed up to the SD and re-read first; the new file goes to
 * /tmp, is verified, swapped in with the original attributes and verified again. Restore writes
 * the SD backup (or the original rebuilt by the PC patcher) back the same way.
 */
#include <gccore.h>
#include <malloc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "kwce.h"

#define PIC_DIR "sd:/kwce-rc/menu"
#define PIC_NEW PIC_DIR "/kwce-0000009d.app"
#define PIC_ORIG PIC_DIR "/original-0000009d.app"
#define PIC_BAK PIC_DIR "/backup-0000009d.app"
#define NAND_RES "/title/00000001/00000002/content/0000009d.app"
/* IOS only renames across directories when the file names are equal. */
#define NAND_TMP "/tmp/0000009d.app"
#define BLOCK (64 * 1024)
#define MAX_RES (32 * 1024 * 1024)

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

static int sha_is(const u8 *data, u32 len, const char *expect)
{
    u8 d[20];
    char h[41];
    sha1_digest(data, len, d);
    for (int i = 0; i < 20; i++) sprintf(h + 2 * i, "%02x", d[i]);
    return strcmp(h, expect) == 0;
}

/* ---- files ---- */
static char want_original[41], want_patched[41];

static int load_config(void)
{
    FILE *f = fopen(PIC_DIR "/resource.txt", "r");
    if (!f) return -1;
    char line[128];
    want_original[0] = want_patched[0] = 0;
    while (fgets(line, sizeof line, f)) {
        line[strcspn(line, "\r\n")] = 0;
        if (!strncmp(line, "original_sha1=", 14)) snprintf(want_original, sizeof want_original, "%.40s", line + 14);
        if (!strncmp(line, "patched_sha1=", 13)) snprintf(want_patched, sizeof want_patched, "%.40s", line + 13);
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
    u8 *buf = n > 0 && n < MAX_RES ? memalign(32, (n + 31) & ~31) : NULL;
    if (buf && fread(buf, 1, n, f) != (size_t)n) { free(buf); buf = NULL; }
    fclose(f);
    if (buf) *len = (u32)n;
    return buf;
}

/* The verified SD copy of the original: the backup made at install, else the patcher's copy. */
static u8 *read_original(u32 *len, const char **from)
{
    const char *paths[2] = {PIC_BAK, PIC_ORIG};
    for (int i = 0; i < 2; i++) {
        u8 *b = read_sd(paths[i], len);
        if (b && sha_is(b, *len, want_original)) { *from = paths[i]; return b; }
        free(b);
    }
    return NULL;
}

static int write_sd(const char *path, const u8 *data, u32 len)
{
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    int ok = fwrite(data, 1, len, f) == len;
    if (fclose(f) != 0) ok = 0;
    return ok ? 0 : -1;
}

static u8 *read_nand(const char *path, u32 *len)
{
    static fstats st ATTRIBUTE_ALIGN(32);
    s32 fd = ISFS_Open(path, ISFS_OPEN_READ);
    if (fd < 0) return NULL;
    u8 *buf = NULL;
    if (ISFS_GetFileStats(fd, &st) >= 0 && st.file_length && st.file_length < MAX_RES) {
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

/* 1 = Priiloader installed: the System Menu boot content was renamed to 1xxxxxxx.app. */
static int priiloader_present(void)
{
    u32 size = 0;
    if (ES_GetStoredTMDSize(0x0000000100000002ULL, &size) < 0 || size == 0 || size > 0x10000) return 0;
    signed_blob *blob = memalign(32, (size + 31) & ~31);
    if (!blob) return 0;
    int found = 0;
    if (ES_GetStoredTMD(0x0000000100000002ULL, blob, size) >= 0) {
        tmd *t = SIGNATURE_PAYLOAD(blob);
        if (t->boot_index < t->num_contents) {
            u32 cid = t->contents[t->boot_index].cid;
            char path[64] ATTRIBUTE_ALIGN(32);
            snprintf(path, sizeof path, "/title/00000001/00000002/content/%08x.app", 0x10000000u | (cid & 0x0FFFFFFFu));
            s32 fd = ISFS_Open(path, ISFS_OPEN_READ);
            if (fd >= 0) { found = 1; ISFS_Close(fd); }
        }
    }
    free(blob);
    return found;
}

/* Write data to /tmp, verify, swap into place keeping attributes, verify again. */
static int replace_resource(const u8 *data, u32 len, const char *expect)
{
    u32 owner = 0; u16 group = 0; u8 attr = 0, op = 3, gp = 3, otp = 1;
    s32 r = ISFS_GetAttr(NAND_RES, &owner, &group, &attr, &op, &gp, &otp);
    if (r < 0) { say("  Cannot read the resource attributes (%d). Nothing changed.\n", r); return -1; }
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
    say("  Swapping the resource file. Do not power off...\n");
    /* Rename replaces the destination; the old file is only removed if that is refused. */
    r = ISFS_Rename(NAND_TMP, NAND_RES);
    if (r < 0) {
        say("  Direct replace refused (%d); removing the old file first.\n", r);
        s32 d = ISFS_Delete(NAND_RES);
        r = ISFS_Rename(NAND_TMP, NAND_RES);
        if (r < 0) {
            say("  RENAME FAILED (%d, delete %d). Choose 2 (restore) now; do not power off.\n", r, d);
            return -2;
        }
    }
    ISFS_SetAttr(NAND_RES, owner, group, attr, op, gp, otp);
    if (!nand_matches(NAND_RES, expect)) { say("  FINAL CHECK FAILED. Choose 2 (restore) now; do not power off.\n"); return -2; }
    say("  Verified.\n");
    return 0;
}

/* ---- screen ---- */
typedef enum { PIC_UNREADABLE, PIC_ORIGINAL, PIC_KWCE, PIC_OTHER } pic_state;

static pic_state current_state(void)
{
    u32 len = 0;
    u8 *buf = read_nand(NAND_RES, &len);
    if (!buf) return PIC_UNREADABLE;
    pic_state s = sha_is(buf, len, want_patched) ? PIC_KWCE : sha_is(buf, len, want_original) ? PIC_ORIGINAL : PIC_OTHER;
    free(buf);
    return s;
}

static void gcpic_install(void)
{
    u32 len = 0, blen = 0, plen = 0;
    const char *from = NULL;
    u8 *cur = read_nand(NAND_RES, &len);
    if (!cur) { say("  Cannot read the resource file. Nothing changed.\n"); return; }
    if (sha_is(cur, len, want_patched)) { say("  Already installed.\n"); free(cur); return; }
    if (!sha_is(cur, len, want_original)) {
        say("  The installed file is not the original 4.3K Korean resource\n"
            "  (a theme or another change?). Nothing changed.\n");
        free(cur);
        return;
    }
    u8 *patched = read_sd(PIC_NEW, &plen);
    if (!patched || !sha_is(patched, plen, want_patched)) {
        say("  %s is missing or damaged. Run the PC patcher again.\n  Nothing changed.\n", PIC_NEW);
        free(patched); free(cur);
        return;
    }
    u8 *bak = read_original(&blen, &from);
    if (!bak || strcmp(from, PIC_BAK)) {
        free(bak);
        if (write_sd(PIC_BAK, cur, len) < 0) { say("  Cannot write the SD backup. Nothing changed.\n"); free(patched); free(cur); return; }
        bak = read_sd(PIC_BAK, &blen);
        if (!bak || !sha_is(bak, blen, want_original)) { say("  The SD backup does not verify. Nothing changed.\n"); free(bak); free(patched); free(cur); return; }
        say("  Backed up the original to " PIC_BAK "\n");
    }
    free(bak);
    free(cur);
    if (confirm("Replace the System Menu resource file (0000009d.app)?\n  Do not power off until it says Verified."))
        replace_resource(patched, plen, want_patched);
    free(patched);
}

static void gcpic_restore(void)
{
    u32 len = 0;
    const char *from = NULL;
    pic_state s = current_state();
    if (s == PIC_ORIGINAL) { say("  The original resource is already installed.\n"); return; }
    if (s == PIC_OTHER)
        say("  The installed file is neither the original nor KWCE's (a theme, or a\n"
            "  failed change). Restoring puts the original 4.3K Korean file back.\n");
    u8 *orig = read_original(&len, &from);
    if (!orig) { say("  No verified original on the SD (" PIC_BAK " or\n  " PIC_ORIG "). Nothing changed.\n"); return; }
    say("  Original from %s\n", from);
    if (confirm("Write the original resource back?\n  Do not power off until it says Verified."))
        replace_resource(orig, len, want_original);
    free(orig);
}

void gcpic_menu(int gamecube_ports)
{
    say("\n== GameCube pictures in Wii Settings (optional)\n");
    if (!gamecube_ports) { say("  Not available: this console has no GameCube ports.\n"); wait_any(); return; }
    if (load_config() < 0) { say("  Files missing: " PIC_DIR "/resource.txt. Run the PC patcher again.\n"); wait_any(); return; }
    if (ISFS_Initialize() < 0) { say("  NAND access failed. Nothing changed.\n"); wait_any(); return; }
    int prii = priiloader_present();
    pic_state s = current_state();
    static const char *names[] = {"unreadable", "original (no GameCube pictures)", "KWCE (GameCube pictures)",
                                  "unknown (another change; left alone)"};
    say("  Shows the GameCube memory card picture and the two-line \"Nintendo\n"
        "  GameCube\" label in Data Management / Save Data. The hacks already\n"
        "  restore the functions; this only adds the pictures.\n"
        "  It replaces ONE System Menu file, 0000009d.app, like a theme install.\n"
        "  Resource: %s\n  Priiloader: %s\n", names[s], prii ? "installed" : "NOT FOUND");
    if (!prii)
        say("  Priiloader is required: if the menu ever fails to start, hold RESET at\n"
            "  power-on > Priiloader > Homebrew Channel > this app > restore.\n"
            "  Install Priiloader first. Restore below still works.\n");
    say("\n  1(X): install the pictures   2(Y): restore the original   B: back\n");
    int k = read_choice();
    if (k == 1) {
        if (!prii) say("  Not installed: Priiloader was not found. Nothing changed.\n");
        else if (s == PIC_ORIGINAL) gcpic_install();
        else if (s == PIC_KWCE) say("  Already installed.\n");
        else say("  The resource is not the original 4.3K file. Nothing changed.\n");
    } else if (k == 2) {
        gcpic_restore();
    }
    ISFS_Deinitialize();
    if (k != -1) wait_any();
}

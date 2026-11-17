/* KWCE key probe (public patch design v2, stage 2). READ-ONLY.
 *
 * v3 (probe output "3"): NAND read path for the Korean-key problem. Real-console v2 results: OTP common
 * key works, ES_Decrypt with common-key handles is refused (-1017), Korean-key WADs need another way.
 *   N1: ES_OpenTitleContent on INSTALLED titles (IOS decrypts with the right common key, Korean too),
 *       SHA-1 of each content vs the stored TMD.
 *   N2: ISFS_Open (read flag only) of the same title's TMD/content files: return codes only.
 *   H : /dev/aes hardware AES: known-answer test, match with software AES, speed.
 * Output: screen + sd:/kwce-key-probe/report-N.txt (new file each run). No key bytes, no key
 * hashes, no console identifiers are printed or written. No NAND/IOS/network access beyond ES_Decrypt.
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
#include <ogc/es.h>
#include <ogc/lwp_watchdog.h>

#define VERSION "4"
static FILE *rep;

static void say(const char *fmt, ...)
{
    va_list ap; va_start(ap, fmt); vprintf(fmt, ap); va_end(ap);
    if (rep) { va_start(ap, fmt); vfprintf(rep, fmt, ap); va_end(ap); fflush(rep); }
}

/* ---------- AES-128 (CBC), compact ---------- */
static u8 sbox[256], inv[256];
static void aes_tables(void)
{
    u8 p = 1, q = 1;
    do {
        p = p ^ (p << 1) ^ (p & 0x80 ? 0x1B : 0);
        q ^= q << 1; q ^= q << 2; q ^= q << 4; if (q & 0x80) q ^= 0x09;
        u8 x = q ^ (q << 1 | q >> 7) ^ (q << 2 | q >> 6) ^ (q << 3 | q >> 5) ^ (q << 4 | q >> 4);
        sbox[p] = x ^ 0x63;
    } while (p != 1);
    sbox[0] = 0x63;
    for (int i = 0; i < 256; i++) inv[sbox[i]] = i;
}
static u8 xt(u8 a) { return (a << 1) ^ (a & 0x80 ? 0x1B : 0); }
static u8 mul(u8 a, u8 b) { u8 r = 0; while (b) { if (b & 1) r ^= a; a = xt(a); b >>= 1; } return r; }
static void expand(const u8 *key, u8 *rk)
{
    memcpy(rk, key, 16); u8 rc = 1;
    for (int i = 16; i < 176; i += 4) {
        u8 t[4]; memcpy(t, rk + i - 4, 4);
        if (i % 16 == 0) { u8 a = t[0]; t[0] = sbox[t[1]] ^ rc; t[1] = sbox[t[2]]; t[2] = sbox[t[3]]; t[3] = sbox[a]; rc = xt(rc); }
        for (int j = 0; j < 4; j++) rk[i + j] = rk[i - 16 + j] ^ t[j];
    }
}
static void enc_block(const u8 *rk, u8 *s)
{
    for (int i = 0; i < 16; i++) s[i] ^= rk[i];
    for (int r = 1; r <= 10; r++) {
        u8 t[16];
        for (int i = 0; i < 16; i++) t[i] = sbox[s[(i + 4 * (i % 4)) % 16]];
        if (r < 10) for (int c = 0; c < 4; c++) {
            u8 *a = t + 4 * c, b0 = a[0], b1 = a[1], b2 = a[2], b3 = a[3], e = b0 ^ b1 ^ b2 ^ b3;
            a[0] ^= e ^ xt(b0 ^ b1); a[1] ^= e ^ xt(b1 ^ b2); a[2] ^= e ^ xt(b2 ^ b3); a[3] ^= e ^ xt(b3 ^ b0);
        }
        for (int i = 0; i < 16; i++) s[i] = t[i] ^ rk[16 * r + i];
    }
}
static void dec_block(const u8 *rk, u8 *s)
{
    for (int i = 0; i < 16; i++) s[i] ^= rk[160 + i];
    for (int r = 9; r >= 0; r--) {
        u8 t[16];
        for (int i = 0; i < 16; i++) t[(i + 4 * (i % 4)) % 16] = inv[s[i]];
        for (int i = 0; i < 16; i++) t[i] ^= rk[16 * r + i];
        if (r > 0) for (int c = 0; c < 4; c++) {
            u8 *a = t + 4 * c, b0 = a[0], b1 = a[1], b2 = a[2], b3 = a[3];
            a[0] = mul(b0, 14) ^ mul(b1, 11) ^ mul(b2, 13) ^ mul(b3, 9);
            a[1] = mul(b0, 9) ^ mul(b1, 14) ^ mul(b2, 11) ^ mul(b3, 13);
            a[2] = mul(b0, 13) ^ mul(b1, 9) ^ mul(b2, 14) ^ mul(b3, 11);
            a[3] = mul(b0, 11) ^ mul(b1, 13) ^ mul(b2, 9) ^ mul(b3, 14);
        }
        memcpy(s, t, 16);
    }
}
static void cbc(const u8 *key, const u8 *iv0, u8 *buf, u32 len, int decrypt)
{
    u8 rk[176], iv[16], nxt[16]; expand(key, rk); memcpy(iv, iv0, 16);
    for (u32 o = 0; o < len; o += 16) {
        u8 *b = buf + o;
        if (decrypt) { memcpy(nxt, b, 16); dec_block(rk, b); for (int i = 0; i < 16; i++) b[i] ^= iv[i]; memcpy(iv, nxt, 16); }
        else { for (int i = 0; i < 16; i++) b[i] ^= iv[i]; enc_block(rk, b); memcpy(iv, b, 16); }
    }
    memset(rk, 0, sizeof rk);
}

/* ---------- SHA-1 ---------- */
static void sha1_block(u32 h[5], const u8 *blk)
{
    u32 w[80];
    for (int t = 0; t < 16; t++) w[t] = (u32)blk[4 * t] << 24 | blk[4 * t + 1] << 16 | blk[4 * t + 2] << 8 | blk[4 * t + 3];
    for (int t = 16; t < 80; t++) { u32 x = w[t - 3] ^ w[t - 8] ^ w[t - 14] ^ w[t - 16]; w[t] = x << 1 | x >> 31; }
    u32 a = h[0], b = h[1], c = h[2], d = h[3], e = h[4];
    for (int t = 0; t < 80; t++) {
        u32 f, k;
        if (t < 20) { f = (b & c) | (~b & d); k = 0x5A827999; }
        else if (t < 40) { f = b ^ c ^ d; k = 0x6ED9EBA1; }
        else if (t < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8F1BBCDC; }
        else { f = b ^ c ^ d; k = 0xCA62C1D6; }
        u32 tmp = (a << 5 | a >> 27) + f + e + k + w[t];
        e = d; d = c; c = b << 30 | b >> 2; b = a; a = tmp;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e;
}
static void sha1_calc(const u8 *d, u32 n, u8 out[20])
{
    u32 h[5] = {0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0}, i = 0;
    for (; i + 64 <= n; i += 64) sha1_block(h, d + i);
    u8 blk[128]; u32 rem = n - i, tot = rem + 9 <= 64 ? 64 : 128; u64 bits = (u64)n * 8;
    memset(blk, 0, sizeof blk); memcpy(blk, d + i, rem); blk[rem] = 0x80;
    for (int k = 0; k < 8; k++) blk[tot - 1 - k] = bits >> (8 * k);
    sha1_block(h, blk); if (tot == 128) sha1_block(h, blk + 64);
    for (int k = 0; k < 5; k++) { out[4 * k] = h[k] >> 24; out[4 * k + 1] = h[k] >> 16; out[4 * k + 2] = h[k] >> 8; out[4 * k + 3] = h[k]; }
}

/* ---------- OTP (method B) ---------- */
#define HW_AHBPROT (*(vu32 *)0xCD800064)
#define HW_OTPCMD  (*(vu32 *)0xCD8001EC)
#define HW_OTPDATA (*(vu32 *)0xCD8001F0)
static int otp_common(u8 key[16])
{
    if (HW_AHBPROT != 0xFFFFFFFF) return -1;
    int nonzero = 0;
    for (int w = 0; w < 4; w++) {
        HW_OTPCMD = 0x80000000 | (5 + w);       /* bytes 0x14..0x23 */
        u32 v = HW_OTPDATA;
        key[4 * w] = v >> 24; key[4 * w + 1] = v >> 16; key[4 * w + 2] = v >> 8; key[4 * w + 3] = v;
        if (v) nonzero = 1;
    }
    return nonzero ? 0 : -2;
}

/* ---------- helpers ---------- */
static u32 be32(const u8 *p) { return p[0] << 24 | p[1] << 16 | p[2] << 8 | p[3]; }

/* ---------- H: /dev/aes ---------- */
static s32 hw_aes(s32 fd, int encrypt, const u8 *key, u8 *iv, const u8 *in, u8 *out, u32 len)
{
    static ioctlv v[4] ATTRIBUTE_ALIGN(32);
    static u8 k[16] ATTRIBUTE_ALIGN(32), ivb[16] ATTRIBUTE_ALIGN(32);
    memcpy(k, key, 16); memcpy(ivb, iv, 16);
    v[0].data = (void *)in; v[0].len = len; v[1].data = k; v[1].len = 16;
    v[2].data = out; v[2].len = len; v[3].data = ivb; v[3].len = 16;
    s32 r = IOS_Ioctlv(fd, encrypt ? 2 : 3, 2, 2, v);
    memcpy(iv, ivb, 16); memset(k, 0, 16);
    return r;
}
static void test_dev_aes(void)
{
    s32 fd = IOS_Open("/dev/aes", 0);
    say("H /dev/aes open: %d\n", fd);
    if (fd < 0) return;
    static u8 z[16] ATTRIBUTE_ALIGN(32), o[16] ATTRIBUTE_ALIGN(32);
    u8 key[16] = {0}, iv[16] = {0};
    memset(z, 0, 16);
    s32 r = hw_aes(fd, 1, key, iv, z, o, 16);
    static const u8 kat[16] = {0x66,0xe9,0x4b,0xd4,0xef,0x8a,0x2c,0x3b,0x88,0x4c,0xfa,0x59,0xca,0x34,0x2b,0x2e};
    say("H KAT encrypt: ret %d, %s\n", r, (r >= 0 && !memcmp(o, kat, 16)) ? "pass" : "FAIL");
    u32 n = 1024 * 1024, chunk = 64 * 1024;
    u8 *a = memalign(32, n), *b = memalign(32, n), *c = memalign(32, n);
    if (!a || !b || !c) { say("H out of memory\n"); goto done; }
    for (u32 i = 0; i < n; i++) a[i] = i * 131 + (i >> 9);
    for (int i = 0; i < 16; i++) { key[i] = 0x10 + i * 7; iv[i] = 0xA0 ^ i; }
    u8 iv2[16]; memcpy(iv2, iv, 16);
    u64 t0 = gettime(); s32 rr = 0;
    for (u32 off = 0; off < n && rr >= 0; off += chunk) rr = hw_aes(fd, 1, key, iv2, a + off, b + off, chunk);
    u64 t1 = gettime();
    memcpy(c, a, n); cbc(key, iv, c, n, 0);           /* software reference */
    say("H 1 MiB CBC encrypt: ret %d, %u ms, %s software\n", rr, (u32)ticks_to_millisecs(t1 - t0), memcmp(b, c, n) ? "DIFFERS from" : "matches");
    memcpy(iv2, iv, 16); t0 = gettime(); rr = 0;
    for (u32 off = 0; off < n && rr >= 0; off += chunk) rr = hw_aes(fd, 0, key, iv2, b + off, c + off, chunk);
    t1 = gettime();
    say("H 1 MiB CBC decrypt: ret %d, %u ms, %s\n", rr, (u32)ticks_to_millisecs(t1 - t0), memcmp(a, c, n) ? "round-trip FAIL" : "round-trip ok");
done:
    free(a); free(b); free(c); memset(key, 0, 16);
    IOS_Close(fd);
}

/* ---------- N1/N2: installed titles ---------- */
static void test_title(u64 tid, const char *label)
{
    say("\n== %s %08x-%08x\n", label, (u32)(tid >> 32), (u32)tid);
    u32 tsz = 0; s32 r = ES_GetStoredTMDSize(tid, &tsz);
    if (r < 0) { say("  not installed / no TMD (%d)\n", r); return; }
    u8 *tmd = memalign(32, (tsz + 31) & ~31);
    r = ES_GetStoredTMD(tid, (signed_blob *)tmd, tsz);
    u16 n = (tmd[0x1DE] << 8) | tmd[0x1DF];
    say("  stored TMD %d, contents %u\n", r, n);
    u32 nv = 0; r = ES_GetNumTicketViews(tid, &nv);
    say("  ticket views: ret %d, count %u\n", r, nv);
    tikview *views = memalign(32, sizeof(tikview) * (nv ? nv : 1));
    if (nv) r = ES_GetTicketViews(tid, views, nv);
    int pass = 0, fail = 0; u32 total = 0, ms_total = 0;
    for (u16 i = 0; i < n && nv; i++) {
        const u8 *rec = tmd + 0x1E4 + 0x24 * i;
        u16 index = (rec[4] << 8) | rec[5]; u32 size = be32(rec + 12);
        if (size > 6 * 1024 * 1024 || total > 12 * 1024 * 1024) continue;
        u8 *buf = memalign(32, (size + 31) & ~31);
        if (!buf) { say("  content %u: out of memory\n", index); break; }
        u64 t0 = gettime();
        s32 cfd = ES_OpenTitleContent(tid, views, index);
        s32 got = 0;
        if (cfd >= 0) {
            while ((u32)got < size) { s32 k = ES_ReadContent(cfd, buf + got, size - got > 0x10000 ? 0x10000 : size - got); if (k <= 0) { got = k < 0 ? k : got; break; } got += k; }
            ES_CloseContent(cfd);
        }
        u32 ms = (u32)ticks_to_millisecs(gettime() - t0);
        int ok = 0;
        if (cfd >= 0 && (u32)got == size) { u8 h[20]; sha1_calc(buf, size, h); ok = !memcmp(h, rec + 16, 20); }
        say("  N1 content %u (%u B): open %d, read %d, SHA-1 %s, %u ms\n", index, size, cfd, got, ok ? "MATCH" : "no match", ms);
        ok ? pass++ : fail++; total += size; ms_total += ms;
        free(buf);
    }
    say("  N1 result: PASS %d / FAIL %d (%u KiB in %u ms)\n", pass, fail, total / 1024, ms_total);
    char path[64];
    snprintf(path, sizeof path, "/title/%08x/%08x/content/title.tmd", (u32)(tid >> 32), (u32)tid);
    s32 fd = ISFS_Open(path, ISFS_OPEN_READ); say("  N2 ISFS read-open title.tmd: %d\n", fd); if (fd >= 0) ISFS_Close(fd);
    if (n) {
        snprintf(path, sizeof path, "/title/%08x/%08x/content/%08x.app", (u32)(tid >> 32), (u32)tid, be32(tmd + 0x1E4));
        fd = ISFS_Open(path, ISFS_OPEN_READ); say("  N2 ISFS read-open first .app: %d\n", fd); if (fd >= 0) ISFS_Close(fd);
    }
    free(views); free(tmd);
}

int main(void)
{
    VIDEO_Init(); WPAD_Init(); PAD_Init();
    GXRModeObj *mode = VIDEO_GetPreferredMode(NULL);
    void *xfb = MEM_K0_TO_K1(SYS_AllocateFramebuffer(mode));
    console_init(xfb, 20, 20, mode->fbWidth, mode->xfbHeight, mode->fbWidth * VI_DISPLAY_PIX_SZ);
    VIDEO_Configure(mode); VIDEO_SetNextFramebuffer(xfb); VIDEO_SetBlack(false); VIDEO_Flush(); VIDEO_WaitVSync();
    printf("\x1b[2;0HKWCE key probe v" VERSION " (read-only)\n");
    char name[64] = "(none)";
    if (fatInitDefault()) {
        mkdir("sd:/kwce-key-probe", 0777);
        for (int i = 1; i < 1000; i++) { snprintf(name, sizeof name, "sd:/kwce-key-probe/report-%d.txt", i); FILE *t = fopen(name, "rb"); if (!t) break; fclose(t); }
        rep = fopen(name, "wb");
    } else printf("SD not readable: screen only.\n");
    aes_tables();
    { u8 z[16] = {0}, k[16] = {0}; u8 rk[176]; expand(k, rk); enc_block(rk, z);
      static const u8 kat[16] = {0x66,0xe9,0x4b,0xd4,0xef,0x8a,0x2c,0x3b,0x88,0x4c,0xfa,0x59,0xca,0x34,0x2b,0x2e};
      say("AES self-test: %s\n", memcmp(z, kat, 16) ? "FAIL" : "pass"); }
    { u8 h[20]; sha1_calc((const u8 *)"abc", 3, h);
      static const u8 kat[20] = {0xa9,0x99,0x3e,0x36,0x47,0x06,0x81,0x6a,0xba,0x3e,0x25,0x71,0x78,0x50,0xc2,0x6c,0x9c,0xd0,0xd8,0x9d};
      say("SHA-1 self-test: %s\n", memcmp(h, kat, 20) ? "FAIL" : "pass"); }
    say("IOS %d (rev %d), AHBPROT %s\n", IOS_GetVersion(), IOS_GetRevision(), HW_AHBPROT == 0xFFFFFFFF ? "open" : "closed");
    { u8 k[16]; int otp = otp_common(k); memset(k, 0, 16);
      say("OTP common key: %s\n", otp == 0 ? "read (non-zero)" : otp == -1 ? "AHBPROT closed" : "all zero (no OTP here)"); }
    s32 isfs = ISFS_Initialize(); say("ISFS_Initialize: %d\n", isfs);
    test_dev_aes();
    test_title(0x000100014843464bULL, "Wii Speak (Korean key)");
    test_title(0x0001000248414645ULL, "Forecast (common key)");
    test_title(0x0001000148414a45ULL, "Everybody Votes");
    if (isfs >= 0) ISFS_Deinitialize();
    say("\nDone. Report: %s%s\n", name, rep ? "" : " (not writable)");
    if (rep) fclose(rep);
    printf("Press HOME (or GC START) to exit.\n");
    for (;;) { WPAD_ScanPads(); if (WPAD_ButtonsDown(0) & (WPAD_BUTTON_HOME | WPAD_CLASSIC_BUTTON_HOME)) break;
        PAD_ScanPads(); if (PAD_ButtonsDown(0) & PAD_BUTTON_START) break; VIDEO_WaitVSync(); }
    return 0;
}

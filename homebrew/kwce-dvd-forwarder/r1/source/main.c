/* KWCE DVD forwarder r1.
 *
 * Why: the disc-channel hook used to keep the whole 7.5 MiB player resident in
 * the System Menu's Mem2App heap. Ordinary channels then failed to create
 * their own work heaps and the menu froze. This small program is the only
 * thing the menu keeps resident; it loads the reviewed player from SD after
 * the menu has shut down, verifies it and hands over.
 *
 * Scope: reads one pinned file, appends numeric stage lines to the existing
 * player log, never touches NAND, IOS selection, the drive or the network.
 * On any failure it returns to the Wii Menu without retrying.
 */
#include <gccore.h>
#include <fat.h>
#include <sdcard/wiisd_io.h>
#include <stdio.h>
#include <string.h>
#include <ogc/machine/processor.h>
#include "pin.h" /* PLAYER_SIZE, PLAYER_SHA1[20], RELOCATOR[], PLAYER_REVISION */

extern void __exception_closeall(void);

typedef struct { u32 h[5]; u64 bits; u8 block[64]; u32 used; } Sha1;
static u32 rol(u32 v, int n) { return (v << n) | (v >> (32 - n)); }
static void sha1_block(Sha1 *s, const u8 *p) {
    u32 w[80], a = s->h[0], b = s->h[1], c = s->h[2], d = s->h[3], e = s->h[4];
    for (int i = 0; i < 16; i++)
        w[i] = ((u32)p[4*i] << 24) | ((u32)p[4*i+1] << 16) | ((u32)p[4*i+2] << 8) | p[4*i+3];
    for (int i = 16; i < 80; i++) w[i] = rol(w[i-3] ^ w[i-8] ^ w[i-14] ^ w[i-16], 1);
    for (int i = 0; i < 80; i++) {
        u32 f, k;
        if (i < 20) { f = (b & c) | (~b & d); k = 0x5a827999; }
        else if (i < 40) { f = b ^ c ^ d; k = 0x6ed9eba1; }
        else if (i < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8f1bbcdc; }
        else { f = b ^ c ^ d; k = 0xca62c1d6; }
        u32 t = rol(a, 5) + f + e + k + w[i];
        e = d; d = c; c = rol(b, 30); b = a; a = t;
    }
    s->h[0] += a; s->h[1] += b; s->h[2] += c; s->h[3] += d; s->h[4] += e;
}
static void kwce_sha1(const u8 *data, u32 size, u8 out[20]) {
    Sha1 s = {{0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0}, 0, {0}, 0};
    u32 at = 0;
    for (; at + 64 <= size; at += 64) sha1_block(&s, data + at);
    u8 tail[128]; u32 rest = size - at, n = rest < 56 ? 64 : 128;
    memset(tail, 0, sizeof tail); memcpy(tail, data + at, rest); tail[rest] = 0x80;
    u64 bits = (u64)size * 8;
    for (int i = 0; i < 8; i++) tail[n - 1 - i] = (u8)(bits >> (8 * i));
    sha1_block(&s, tail); if (n == 128) sha1_block(&s, tail + 64);
    for (int i = 0; i < 5; i++) {
        out[4*i] = s.h[i] >> 24; out[4*i+1] = s.h[i] >> 16; out[4*i+2] = s.h[i] >> 8; out[4*i+3] = s.h[i];
    }
}

/* Same numeric format as the player's log; no media content or identifiers. */
static void trace(int stage, int value) {
    FILE *f = fopen("sd:/kwce/dvd/playback-r21.log", "ab");
    if (!f) return;
    fprintf(f, "forwarder %d %d\n", stage, value);
    fclose(f);
}

static void fail(int mounted, int code) {
    if (mounted) { trace(-code, PLAYER_REVISION); fatUnmount("sd"); }
    __io_wiisd.shutdown(&__io_wiisd);
    SYS_ResetSystem(SYS_RETURNTOMENU, 0, 0);
    for (;;) ;
}

int main(void) {
    /* Reserve the image and the relocation stub at the bottom of MEM2: the
     * player's own sections cover MEM1, so nothing here may live there. */
    u8 *image = (u8 *)(((u32)SYS_GetArena2Lo() + 31) & ~31u);
    u32 stub_size = (sizeof RELOCATOR + 31) & ~31u;
    u8 *stub = image + ((PLAYER_SIZE + 31) & ~31u);
    if ((u32)image < 0x90000000u || stub + stub_size > (u8 *)SYS_GetArena2Hi()) fail(0, 1);
    SYS_SetArena2Lo(stub + stub_size);

    if (!fatMountSimple("sd", &__io_wiisd)) fail(0, 2);
    FILE *f = fopen("sd:/kwce/dvd/player.dol", "rb");
    if (!f) fail(1, 3);
    setvbuf(f, NULL, _IONBF, 0); /* whole-cluster reads straight into MEM2 */
    u32 got = 0;
    while (got < PLAYER_SIZE) {
        u32 want = PLAYER_SIZE - got; if (want > 0x100000) want = 0x100000;
        u32 n = fread(image + got, 1, want, f);
        if (n != want) { fclose(f); fail(1, 4); }
        got += n;
    }
    u8 extra; int at_end = fread(&extra, 1, 1, f) == 0;
    if (fclose(f) != 0 || !at_end) fail(1, 5);
    u8 digest[20]; kwce_sha1(image, PLAYER_SIZE, digest);
    if (memcmp(digest, PLAYER_SHA1, 20) != 0) fail(1, 6);
    trace(1, PLAYER_REVISION);
    fatUnmount("sd");
    __io_wiisd.shutdown(&__io_wiisd);

    memcpy(stub, RELOCATOR, sizeof RELOCATOR);
    DCFlushRange(stub, stub_size);
    ICInvalidateRange(stub, stub_size);
    SYS_ResetSystem(SYS_SHUTDOWN, 0, 0);
    u32 level; _CPU_ISR_Disable(level); (void)level;
    __exception_closeall();
    ((void (*)(void *))stub)(image); /* copies sections to MEM1, clears BSS, enters */
    for (;;) ;
}

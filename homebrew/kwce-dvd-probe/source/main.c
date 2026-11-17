/* Read-only DVD metadata probe. No title/content/identity bytes are logged. */
#include <gccore.h>
#include <wiiuse/wpad.h>
#include <ogc/ios.h>
#include <ogc/lwp_watchdog.h>
#include <di/di.h>
#include <fat.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static FILE *report;
static unsigned sequence;
static int log_ok = 1;
static unsigned char buffer[26 * 2048] ATTRIBUTE_ALIGN(32);

static unsigned elapsed(u64 start) { return ticks_to_millisecs(gettime() - start); }

static int trace(const char *tag, int a, int b, unsigned ms)
{
    printf("%u %s %d %d %u\n", ++sequence, tag, a, b, ms);
    if (log_ok && (fprintf(report, "%u %s %d %d %u\n", sequence, tag, a, b, ms) < 0 ||
        fflush(report) || fsync(fileno(report)))) log_ok = 0;
    if (!log_ok) printf("SD log failed. Further drive commands stopped.\n");
    return log_ok;
}

static int new_report(void)
{
    if (!fatInitDefault()) return 0;
    if (mkdir("sd:/kwce-rc", 0777) && errno != EEXIST) return 0;
    for (unsigned i = 1; i <= 9999; ++i) {
        char name[80];
        snprintf(name, sizeof name, "sd:/kwce-rc/dvd-probe-%04u.txt", i);
        int fd = open(name, O_WRONLY | O_CREAT | O_EXCL, 0666);
        if (fd < 0) { if (errno == EEXIST) continue; return 0; }
        report = fdopen(fd, "w");
        if (!report) { close(fd); return 0; }
        printf("New SD report #%u\n", i);
        return 1;
    }
    return 0;
}

/* Return a bit mask only; never print or persist the read buffer. */
static int metadata_kind(const unsigned char *p, unsigned lba)
{
    int result = 0;
    if (lba == 16) {
        if (!memcmp(p + 1, "CD001", 5)) result |= 1;
        if (!memcmp(p + 1, "BEA01", 5)) result |= 2;
        if (!memcmp(p + 1, "NSR02", 5) || !memcmp(p + 1, "NSR03", 5)) result |= 4;
    }
    if (lba == 256 && p[0] == 2 && p[1] == 0) {
        unsigned char checksum = 0;
        for (unsigned i = 0; i < 16; ++i) if (i != 4) checksum += p[i];
        if (checksum == p[4] && (unsigned)p[12] + ((unsigned)p[13] << 8) +
            ((unsigned)p[14] << 16) + ((unsigned)p[15] << 24) == lba) result |= 8;
    }
    return result;
}

static void probe(void)
{
    u64 start;
    int rc, ready = 0;
    if (!trace("start", 1, IOS_GetVersion(), 0)) return;
    int ahb = *(vu32 *)0xcd800064 == 0xffffffff;
    if (!trace("ahb", ahb, 0, 0) || !ahb) return;
    /* Same pinned libdi as R51; cache disabled to control physical read size. */
    DI_UseCache(false);
    if (!trace("init-begin", 0, 0, 0)) return;
    start = gettime(); rc = DI_Init();
    if (!trace("init-end", rc, di_fd >= 0, elapsed(start)) || rc < 0 || di_fd < 0) return;
    if (!trace("mount-begin", 0, 0, 0)) return;
    start = gettime(); DI_Mount();
    while (elapsed(start) < 15000) {
        int state = DI_GetStatus();
        if (state & DVD_READY) { ready = 1; break; }
        if (!(state & DVD_INIT)) break;
        usleep(10000);
    }
    if (!trace("mount-end", ready, DI_GetStatus(), elapsed(start)) || !ready) {
        /* Do not close while the SDK's mount callback may still be pending. */
        return;
    }
    /* Both 1 and 26 sectors matter: WiiMC's default libdi cache fetch is 26. */
    const unsigned sectors[] = {0, 16, 256};
    for (unsigned size = 1; size <= 26; size += 25) {
        for (unsigned i = 0; i < 3; ++i) {
            /* i is a public probe index, not a disc-derived address. */
            if (!trace("read-begin", (int)i, (int)size, 0)) return;
            memset(buffer, 0, sizeof buffer);
            start = gettime(); rc = DI_ReadDVD(buffer, size, sectors[i]);
            if (!trace("read-end", rc, DI_GetStatus(), elapsed(start))) return;
            if (rc == 0) {
                if (!trace("metadata", (int)i, metadata_kind(buffer, sectors[i]), 0)) return;
            } else {
                uint32_t error = 0;
                if (!trace("error-begin", 0, 0, 0)) return;
                start = gettime(); int er = DI_GetError(&error);
                if (!trace("error-end", er, (int)error, elapsed(start))) return;
            }
        }
    }
    trace("complete", 1, 0, 0);
    /* No outstanding mount callback after READY and synchronous reads. */
    DI_Close();
}

int main(void)
{
    VIDEO_Init();
    GXRModeObj *mode = VIDEO_GetPreferredMode(NULL);
    void *frame = MEM_K0_TO_K1(SYS_AllocateFramebuffer(mode));
    console_init(frame, 20, 20, mode->fbWidth, mode->xfbHeight, mode->fbWidth * 2);
    VIDEO_Configure(mode); VIDEO_SetNextFramebuffer(frame); VIDEO_SetBlack(false);
    VIDEO_Flush(); VIDEO_WaitVSync(); if (mode->viTVMode & VI_NON_INTERLACE) VIDEO_WaitVSync();
    WPAD_Init(); PAD_Init();
    printf("KWCE DVD Read Probe v1\nInsert the SAME DVD used in the failed test.\n");
    if (!new_report()) { printf("Cannot create new SD report. No drive test.\n"); }
    else {
        printf("A: start once   HOME/START: return\n");
        int ran = 0;
        for (;;) {
            WPAD_ScanPads(); PAD_ScanPads();
            u32 w = WPAD_ButtonsDown(0); u16 g = PAD_ButtonsDown(0);
            if ((w & WPAD_BUTTON_HOME) || (g & PAD_BUTTON_START)) break;
            if (!ran && ((w & WPAD_BUTTON_A) || (g & PAD_BUTTON_A))) {
                ran = 1; probe();
                printf("Test ended. HOME/START: return.\n");
            }
            VIDEO_WaitVSync();
        }
        fclose(report);
        return 0;
    }
    for (;;) {
        WPAD_ScanPads(); PAD_ScanPads();
        if ((WPAD_ButtonsDown(0) & WPAD_BUTTON_HOME) || (PAD_ButtonsDown(0) & PAD_BUTTON_START)) return 0;
        VIDEO_WaitVSync();
    }
}

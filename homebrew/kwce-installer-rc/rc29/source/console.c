/*
 * KWCE unified installer -- console model detection (read-only).
 *
 * Reads the System Menu's /title/00000001/00000002/data/setting.txt over ISFS,
 * decrypts its rolling-XOR obfuscation (key seed 0x73B5DBFA, rotate-left 1 per
 * byte) and reports the MODEL field. Only RVL-001 vs RVL-101 vs vWii and the AREA
 * (console region, RC4+) are derived; the serial number and every other field are
 * never copied out or logged. On
 * any failure the model is UNKNOWN and the caller keeps the full feature set
 * with an on-screen note, so a read error never silently hides GameCube tools.
 */
#include <gccore.h>
#include <ogc/isfs.h>
#include <malloc.h>
#include <string.h>

#include "kwce.h"

#define SETTING_PATH "/title/00000001/00000002/data/setting.txt"
#define SETTING_MAX 1024

static char area[8];

/* AREA=KOR etc.: letters only, so nothing else from the file can leak into this copy. */
static void read_area(const char *body)
{
    area[0] = 0;
    const char *a = strstr(body, "AREA=");
    if (!a) return;
    a += 5;
    unsigned n = 0;
    while (n + 1 < sizeof area && a[n] >= 'A' && a[n] <= 'Z') {
        area[n] = a[n];
        n++;
    }
    area[n] = 0;
}

const char *console_area(void)
{
    return area;
}

/* __OSCheckTmdCountryCode: the System Menu starts a channel whose TMD region is 3 (any) or
   the console's own region. AUS/BRA-style areas share the EUR/USA region. */
int console_tmd_region(void)
{
    static const struct { const char *area; int region; } map[] = {
        { "JPN", 0 }, { "USA", 1 }, { "BRA", 1 }, { "LTN", 1 }, { "EUR", 2 }, { "AUS", 2 }, { "KOR", 4 },
    };
    for (unsigned i = 0; i < sizeof map / sizeof map[0]; i++)
        if (!strcmp(area, map[i].area)) return map[i].region;
    return -1;
}

/* Parse the decrypted "KEY=VALUE\r\n" body for MODEL and classify it. */
static console_model classify(const char *body)
{
    const char *m = strstr(body, "MODEL=");
    if (!m) return CONSOLE_UNKNOWN;
    m += 6;
    /* vWii's System Menu reports RVL-100; a real GameCube-capable Wii is RVL-001. */
    if (!strncmp(m, "RVL-001", 7)) return CONSOLE_RVL001;
    if (!strncmp(m, "RVL-101", 7)) return CONSOLE_RVL101;
    if (!strncmp(m, "RVL-100", 7)) return CONSOLE_VWII;
    return CONSOLE_UNKNOWN;
}

console_model read_console_model(void)
{
    console_model result = CONSOLE_UNKNOWN;
    if (ISFS_Initialize() < 0) return result;
    s32 fd = ISFS_Open(SETTING_PATH, ISFS_OPEN_READ);
    if (fd >= 0) {
        u8 *buf = memalign(32, SETTING_MAX);
        if (buf) {
            s32 n = ISFS_Read(fd, buf, SETTING_MAX);
            if (n > 0 && n <= SETTING_MAX) {
                char plain[SETTING_MAX + 1];
                u32 key = 0x73B5DBFAu;
                for (s32 i = 0; i < n; i++) {
                    plain[i] = (char)(buf[i] ^ (key & 0xFF));
                    key = (key << 1) | (key >> 31);
                }
                plain[n] = 0;
                result = classify(plain);
                read_area(plain);
                /* Do not leave the decrypted serial number in memory. */
                memset(plain, 0, sizeof plain);
            }
            memset(buf, 0, SETTING_MAX);
            free(buf);
        }
        ISFS_Close(fd);
    }
    ISFS_Deinitialize();
    return result;
}

const char *console_model_name(console_model model)
{
    switch (model) {
        case CONSOLE_RVL001: return "RVL-001 (GameCube ports)";
        case CONSOLE_RVL101: return "RVL-101 (no GameCube ports)";
        case CONSOLE_VWII:   return "vWii / RVL-100";
        default:             return "unknown";
    }
}

/* GameCube disc-channel + save-menu features need the physical GC ports of RVL-001.
   RVL-101 and vWii have none, so the installer offers channel titles only there.
   UNKNOWN keeps the features (with a note) rather than hiding them on a read error. */
int console_supports_gamecube(console_model model)
{
    return model == CONSOLE_RVL001 || model == CONSOLE_UNKNOWN;
}

#ifndef KWCE_H
#define KWCE_H

#include <gctypes.h>

void say(const char *fmt, ...);
int confirm(const char *what);
void wait_any(void);

typedef enum { CONSOLE_UNKNOWN = 0, CONSOLE_RVL001, CONSOLE_RVL101, CONSOLE_VWII } console_model;

console_model read_console_model(void);
const char *console_model_name(console_model model);
int console_supports_gamecube(console_model model);
/* AREA field of setting.txt read by read_console_model() ("KOR", "JPN", ...); "" when unknown. */
const char *console_area(void);
/* TMD region the System Menu accepts besides 3 (any region) on this console; -1 when unknown. */
int console_tmd_region(void);

/* Read-only WiiConnect24 status snapshot to SD (wc24report.c). Returns 0 when saved. */
int wc24_report(console_model model, const char *version);

/* wiilink.c: 1 = WiiLink mail/download settings present, 0 = not, -1 = unreadable (read only). */
int wiilink_state(void);
/* Offers the bundled WiiLink Mail Patcher (SD copy only); does nothing when WiiLink is detected.
   startup=1 stays silent when the user skipped before. */
void wiilink_setup(int startup);

/* versions.c: build identity of a channel title and the version list sd:/kwce-rc/versions.txt. */
typedef struct {
    u64 fp;         /* FNV-1a 64 over the TMD fields that define the build (never 0) */
    u64 tid;
    u32 ios;        /* low half of the IOS title id */
    u16 version;
    u16 region;     /* TMD region: 0 JPN, 1 USA, 2 EUR, 3 any, 4 KOR */
    u16 contents;
    u16 shared;     /* contents of type 0x8001 (kept in /shared1 by every title using them) */
    u8 complete;    /* 1 = boot content present (always 1 for a WAD); 0 = only a leftover TMD */
} identity;

typedef struct {
    u64 fp;
    int chan;
    int rank;       /* KWCE release (RC number) that first shipped it; 0 = earlier test package */
    char kind;      /* 'K' = KWCE Korean build, 'O' = original channel */
    char label[24];
} known_build;

int tmd_identity(const u8 *tmd, u32 len, identity *out);
/* 0 = identity of the TMD inside a WAD on SD; -1 = missing or not a WAD. */
int wad_identity(const char *path, identity *out);
/* 0 = the title has a stored TMD (identity filled, *kwce_marks = contents only KWCE builds have);
   -1 = no TMD. A deleted channel keeps its TMD: out->complete is 0 when its boot content is gone. */
int installed_identity(u64 tid, const char *id, identity *out, int *kwce_marks);
/* Number of builds loaded; -1 = no list on SD; -2 = unknown list format. */
int versions_load(const char *path);
int versions_release(void);
const known_build *versions_lookup(const char *id, u64 fp);

#endif

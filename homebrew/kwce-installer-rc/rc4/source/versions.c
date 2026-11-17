/*
 * KWCE RC installer -- build identity and the version list (read only).
 *
 * A channel build is identified by the TMD fields that decide what runs: the IOS, title id,
 * region, access rights, title version, content count, boot index and every content record
 * (id, index, type, size, SHA-1). The signature block and the two fakesign bytes at 0x1E2
 * are left out, so re-signing the same build keeps its identity. The value is FNV-1a 64.
 * The PC packager (kwce/rc_hardware.py version_list) computes the same value for every KWCE
 * build and channel original it knows and writes sd:/kwce-rc/versions.txt:
 *
 *   kwce-versions|1|<release>|<version>          first line
 *   build|<channel id>|<16 hex>|<K or O>|<rank>|<label>
 *   mark|<channel id>|<16 hex>                   first 8 bytes of a content SHA-1 that only
 *                                                KWCE builds contain (never an original)
 *
 * K = KWCE Korean build, O = original channel. rank = the RC release that first shipped the
 * build, 0 = an earlier test package. Every new package lists all older releases, so an older
 * KWCE build on the console is recognised as an update. A build the list does not know but
 * whose contents carry a mark is a KWCE build this list predates (for example a newer one).
 *
 * The installed TMD is read with ES_GetStoredTMD only: no NAND write, no ISFS.
 */
#include <gccore.h>
#include <malloc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "kwce.h"

#define MAX_BUILDS 2048
#define MAX_MARKS 8192
#define MAX_IDS 32
#define TMD_MAX 0x10000u
#define A64(x) (((x) + 63) & ~63u)

typedef struct {
    u64 prefix;
    int chan;
} mark;

static char ids[MAX_IDS][32];
static int nids;
static known_build *builds;
static int nbuilds;
static mark *marks;
static int nmarks;
static int release_no;

static u16 rd16(const u8 *p) { return (u16)((p[0] << 8) | p[1]); }
static u32 rd32(const u8 *p) { return ((u32)p[0] << 24) | ((u32)p[1] << 16) | ((u32)p[2] << 8) | p[3]; }
static u64 rd64(const u8 *p) { return ((u64)rd32(p) << 32) | rd32(p + 4); }

static u64 fnv(u64 h, const u8 *p, u32 n)
{
    while (n--) {
        h ^= *p++;
        h *= 0x100000001b3ULL;
    }
    return h;
}

int tmd_identity(const u8 *tmd, u32 len, identity *out)
{
    if (len < 0x1E4) return -1;
    u16 count = rd16(tmd + 0x1DE);
    if (len < 0x1E4 + 36u * count) return -1;
    u64 h = 0xcbf29ce484222325ULL;
    h = fnv(h, tmd + 0x184, 0x10);          /* IOS + title id */
    h = fnv(h, tmd + 0x19C, 2);             /* region */
    h = fnv(h, tmd + 0x1D8, 0x0A);          /* access rights, title version, contents, boot index */
    h = fnv(h, tmd + 0x1E4, 36u * count);   /* content records */
    out->fp = h ? h : 1;
    out->tid = rd64(tmd + 0x18C);
    out->ios = rd32(tmd + 0x188);
    out->version = rd16(tmd + 0x1DC);
    out->region = rd16(tmd + 0x19C);
    out->contents = count;
    return 0;
}

int wad_identity(const char *path, identity *out)
{
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    u8 h[32];
    int ret = -1;
    if (fread(h, 1, sizeof h, f) == sizeof h) {
        u32 hdr = rd32(h), certs = rd32(h + 8), crl = rd32(h + 12), tik = rd32(h + 16), len = rd32(h + 20);
        if (hdr == 0x20 && len >= 0x1E4 && len <= TMD_MAX) {
            u8 *tmd = malloc(len);
            if (tmd) {
                long off = (long)(A64(hdr) + A64(certs) + A64(crl) + A64(tik));
                if (!fseek(f, off, SEEK_SET) && fread(tmd, 1, len, f) == len) ret = tmd_identity(tmd, len, out);
                free(tmd);
            }
        }
    }
    fclose(f);
    return ret;
}

static int chan_index(const char *id)
{
    for (int i = 0; i < nids; i++)
        if (!strcmp(ids[i], id)) return i;
    return -1;
}

static int intern(const char *id)
{
    int i = chan_index(id);
    if (i >= 0 || nids >= MAX_IDS) return i;
    snprintf(ids[nids], sizeof ids[nids], "%s", id);
    return nids++;
}

static int marked(int chan, u64 prefix)
{
    for (int i = 0; i < nmarks; i++)
        if (marks[i].chan == chan && marks[i].prefix == prefix) return 1;
    return 0;
}

int installed_identity(u64 tid, const char *id, identity *out, int *kwce_marks)
{
    u32 size = 0;
    if (kwce_marks) *kwce_marks = 0;
    if (ES_GetStoredTMDSize(tid, &size) < 0 || size < 0x1E4 || size > TMD_MAX) return -1;
    signed_blob *tmd = memalign(32, A64(size));
    if (!tmd) return -1;
    int ret = -1;
    if (ES_GetStoredTMD(tid, tmd, size) >= 0 && tmd_identity((const u8 *)tmd, size, out) == 0 && out->tid == tid) {
        ret = 0;
        int chan = chan_index(id);
        if (kwce_marks && chan >= 0)
            for (u32 i = 0; i < out->contents; i++)
                if (marked(chan, rd64((const u8 *)tmd + 0x1E4 + 36u * i + 16))) (*kwce_marks)++;
    }
    free(tmd);
    return ret;
}

int versions_load(const char *path)
{
    nbuilds = nmarks = 0;
    release_no = 0;
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    if (!builds) builds = malloc(sizeof(known_build) * MAX_BUILDS);
    if (!marks) marks = malloc(sizeof(mark) * MAX_MARKS);
    if (!builds || !marks) {
        fclose(f);
        return -1;
    }
    char line[192];
    int header = 0;
    while (fgets(line, sizeof line, f)) {
        line[strcspn(line, "\r\n")] = 0;
        if (header && (!line[0] || line[0] == '#')) continue;
        char *field[6];
        int n = 0;
        for (char *s = line; n < 6;) {
            field[n++] = s;
            char *bar = strchr(s, '|');
            if (!bar) break;
            *bar = 0;
            s = bar + 1;
        }
        if (!header) {
            if (n < 3 || strcmp(field[0], "kwce-versions") || atoi(field[1]) != 1) break;
            release_no = atoi(field[2]);
            header = 1;
            continue;
        }
        if (n == 6 && !strcmp(field[0], "build") && strlen(field[2]) == 16 && nbuilds < MAX_BUILDS) {
            int chan = intern(field[1]);
            if (chan < 0) continue;
            known_build *b = &builds[nbuilds++];
            b->fp = strtoull(field[2], NULL, 16);
            b->chan = chan;
            b->kind = field[3][0] == 'O' ? 'O' : 'K';
            b->rank = atoi(field[4]);
            snprintf(b->label, sizeof b->label, "%s", field[5]);
        } else if (n == 3 && !strcmp(field[0], "mark") && strlen(field[2]) == 16 && nmarks < MAX_MARKS) {
            int chan = intern(field[1]);
            if (chan < 0) continue;
            marks[nmarks].prefix = strtoull(field[2], NULL, 16);
            marks[nmarks].chan = chan;
            nmarks++;
        }
    }
    fclose(f);
    if (!header) {
        nbuilds = nmarks = 0;
        return -2;
    }
    return nbuilds;
}

int versions_release(void)
{
    return release_no;
}

const known_build *versions_lookup(const char *id, u64 fp)
{
    int chan = chan_index(id);
    if (chan < 0) return NULL;
    for (int i = 0; i < nbuilds; i++)
        if (builds[i].chan == chan && builds[i].fp == fp) return &builds[i];
    return NULL;
}

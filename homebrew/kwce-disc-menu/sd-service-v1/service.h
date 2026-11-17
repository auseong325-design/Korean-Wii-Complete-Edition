/* Local research component, not a loadable module or a hardware patch. */
#ifndef KWCE_SD_SERVICE_H
#define KWCE_SD_SERVICE_H
typedef unsigned int u32;
typedef unsigned char u8;
typedef struct { u32 size; u8 sha1[20]; } KwceAsset;
typedef struct {
    void *data[2];
    void *heap;
    u32 size[2];
} KwceAssets;
enum { KWCE_WAITING, KWCE_QUEUED, KWCE_READING, KWCE_READY,
       KWCE_FAILED, KWCE_CANCELLED, KWCE_TAKEN };
#define KWCE_SD_MESSAGE 0x4b574345u

/* Main-thread API. Init once, before BoardSD's first READY handoff.
 * Two immutable descriptors, icon.arc then menu.arc; no player payload.
 * State/storage and original worker must outlive close/drain. */
int kwce_sd_init(const KwceAsset assets[2]);
void kwce_sd_board_update(void *board_sd);
void kwce_sd_cancel(void);
int kwce_sd_drained(void);
int kwce_sd_status(void);
int kwce_sd_take(KwceAssets *out);
void kwce_sd_release(KwceAssets *assets);
/* Worker-thread adapter: replaces ONLY run()'s call to wait_work(). */
u32 kwce_sd_wait(void *worker);
#endif

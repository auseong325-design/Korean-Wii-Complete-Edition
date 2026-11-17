/* Pinned 43K ABI. No mount, reset, format, NAND or IOS write calls.
 * NOT installed: code placement and full Board/Settings lifetime are pending.
 * One small batch per service lifetime prevents starving the CDB handoff.
 */
#include "service.h"
#define FN(a,t) ((t)(a))
#define PTR(p,o) (*(void **)((u8 *)(p)+(o)))
static struct {
    u8 mutex[24];
    int initialized, closing, active, state;
    void *worker, *work, *heap;
    KwceAsset spec[2];
    void *data[2];
} service;

static void lock(void) { FN(0x8150A9C0,void (*)(void *))(service.mutex); }
static void unlock(void) { FN(0x8150AA9C,void (*)(void *))(service.mutex); }
static void dispose(void *data,void *heap) {
    if(data) FN(0x815D0B6C,void (*)(void *,void *))(data,heap);
}
static int eligible(void *worker) {
    void *cdb=*(void **)0x81089084;
    return cdb && worker==(u8 *)cdb+0x18 &&
        PTR(worker,0)==service.work && service.work && !*((u8 *)cdb+0x14) &&
        FN(0x8135E408,int (*)(void *))(worker)==5;
}
static int cancelled(void) {
    int result; lock(); result=service.closing; unlock(); return result;
}
int kwce_sd_init(const KwceAsset assets[2]) {
    /* No re-init of a live mutex or worker storage, including after drain. */
    if(service.initialized || !assets || !*(void **)0x81089084 ||
       !*(void **)0x81089030)return 0;
    for(u32 i=0;i<2;i++)
        if(!assets[i].size || assets[i].size>256u*1024u)return 0;
    service.worker=(u8 *)*(void **)0x81089084+0x18;
    service.work=PTR(service.worker,0);
    if(!service.work)return 0;
    service.heap=*(void **)0x81089030;
    for(u32 i=0;i<2;i++) {
        service.spec[i].size=assets[i].size;
        for(u32 j=0;j<20;j++)service.spec[i].sha1[j]=assets[i].sha1[j];
    }
    FN(0x8150A988,void (*)(void *))(service.mutex);
    service.state=KWCE_WAITING;
    service.initialized=1;
    return 1;
}
void kwce_sd_board_update(void *board_sd) {
    if(service.initialized) {
        lock();
        /* Main thread is the sole queue producer. Hold our lock over submit;
         * the worker may wake immediately, but cannot publish before QUEUED.
         * Preserve BoardSD's own states; never take SD back from CDB. */
        if(!service.closing && service.state==KWCE_WAITING &&
           *(u32 *)board_sd==0 && eligible(service.worker) &&
           !FN(0x8135E38C,int (*)(void *))(service.worker)) {
            service.active=1; service.state=KWCE_QUEUED;
            FN(0x8135ED70,void (*)(void *,int))(service.worker,1);
            int sent=FN(0x81509E38,int (*)(void *,u32,int))(
                (u8 *)service.work+0x21490,KWCE_SD_MESSAGE,0);
            if(!sent) {
                service.active=0; service.state=KWCE_FAILED;
                FN(0x8135ED70,void (*)(void *,int))(service.worker,0);
            }
        }
        unlock();
    }
    FN(0x81395338,void (*)(void *))(board_sd);
}
static void *read_asset(u32 index) {
    static const char names[2][24]={"?:/kwce/dvd/icon.arc","?:/kwce/dvd/menu.arc"};
    char path[24];
    void *file=0,*data=0;
    u32 size=service.spec[index].size,offset=0;
    if(cancelled() || !eligible(service.worker))return 0;
    for(u32 i=0;i<sizeof(path);i++)path[i]=names[index][i];
    path[0]=*((char *)service.work+0x1148);
    file=FN(0x815C0DA4,void *(*)(const char *,const char *))(path,"r");
    if(!file)return 0;
    data=FN(0x815D0A08,void *(*)(u32,int,void *))(size,32,service.heap);
    if(!data)goto fail;
    while(offset<size) {
        if(cancelled() || !eligible(service.worker))goto fail;
        u32 count=size-offset;
        if(count>16384)count=16384;
        if(FN(0x815C0E00,u32 (*)(void *,u32,u32,void *))(
               (u8 *)data+offset,1,count,file)!=count)goto fail;
        offset+=count;
    }
    u8 tail;
    if(cancelled() || !eligible(service.worker) ||
       FN(0x815C0E00,u32 (*)(void *,u32,u32,void *))(&tail,1,1,file))goto fail;
    int closed=FN(0x815C0D4C,int (*)(void *))(file); file=0;
    if(closed)goto fail;
    u8 sha[96] __attribute__((aligned(32))),hash[20];
    FN(0x8146CCCC,void (*)(void *))(sha);
    FN(0x8146CD1C,void (*)(void *,const void *,u32))(sha,data,size);
    FN(0x8146CDD0,void (*)(void *,void *))(sha,hash);
    for(u32 i=0;i<20;i++)if(hash[i]!=service.spec[index].sha1[i])goto fail;
    /* Publish cache lines before the UI can obtain the immutable bundle. */
    FN(0x8150671C,void (*)(void *,u32))(data,size);
    return data;
fail:
    if(file)FN(0x815C0D4C,int (*)(void *))(file);
    dispose(data,service.heap); return 0;
}
static void read_batch(void *worker) {
    void *data[2]={0,0};
    lock();
    if(!service.active || service.state!=KWCE_QUEUED ||
       worker!=service.worker) { unlock(); return; }
    service.state=KWCE_READING;
    unlock();
    data[0]=read_asset(0);
    if(data[0])data[1]=read_asset(1);
    lock();
    int ready=!service.closing && eligible(worker) && data[0] && data[1];
    if(ready) {
        service.data[0]=data[0]; service.data[1]=data[1];
        service.state=KWCE_READY;
        /* No unpublished allocation remains after active becomes false. */
        service.active=0;
        unlock();
    } else {
        unlock();
        dispose(data[0],service.heap); dispose(data[1],service.heap);
        lock();
        service.state=service.closing?KWCE_CANCELLED:KWCE_FAILED;
        service.active=0;
        unlock();
    }
}
u32 kwce_sd_wait(void *worker) {
    u32 message=FN(0x8135ECCC,u32 (*)(void *))(worker);
    if(message!=KWCE_SD_MESSAGE)return message;
    read_batch(worker);
    /* Original run() still checks its stack and resets WORKING -> IDLE. */
    return 0;
}
void kwce_sd_cancel(void) {
    if(!service.initialized)return;
    lock(); service.closing=1;
    /* The UI owns results already taken. Only unclaimed buffers live here. */
    void *a=service.data[0],*b=service.data[1];
    service.data[0]=0; service.data[1]=0;
    if(!service.active)service.state=KWCE_CANCELLED;
    unlock();
    dispose(a,service.heap); dispose(b,service.heap);
}
int kwce_sd_drained(void) {
    if(!service.initialized)return 1;
    lock(); int result=service.closing && !service.active &&
        (!PTR(service.worker,0) ||
         !FN(0x8135E38C,int (*)(void *))(service.worker));
    unlock(); return result;
}
int kwce_sd_status(void) {
    if(!service.initialized)return KWCE_CANCELLED;
    lock(); int result=service.state; unlock(); return result;
}
int kwce_sd_take(KwceAssets *out) {
    if(!service.initialized || !out)return 0;
    lock();
    if(service.closing || service.state!=KWCE_READY) { unlock(); return 0; }
    out->heap=service.heap;
    for(u32 i=0;i<2;i++) {
        out->data[i]=service.data[i]; out->size[i]=service.spec[i].size;
        service.data[i]=0;
    }
    service.state=KWCE_TAKEN;
    unlock(); return 1;
}
void kwce_sd_release(KwceAssets *assets) {
    if(!assets)return;
    for(u32 i=0;i<2;i++) {
        dispose(assets->data[i],assets->heap);
        assets->data[i]=0; assets->size[i]=0;
    }
    assets->heap=0;
}

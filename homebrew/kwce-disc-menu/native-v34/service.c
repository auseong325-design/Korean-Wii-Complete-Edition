/* 43K internal service. FA access is confined to the existing SDVF worker.
 * One validated, immutable bundle belongs to the menu process, not a scene.
 * Both Mem2Sys (control) and Mem2App (bundle) persist across Settings scenes.
 * The bundle survives media/scene changes: it contains code/UI, no disc data.
 */
typedef unsigned int u32;
typedef unsigned char u8;
#define FN(a,t) ((t)(a))
#define PTR(p,o) (*(void **)((u8 *)(p)+(o)))
#define FIELD(p,o) (*(u32 *)((u8 *)(p)+(o)))
#define MESSAGE 0x4b574345u
#include "service-payload.h"
enum {WAITING,QUEUED,READING,READY,FAILED};
typedef struct {
    u32 mutex[6];
    void *worker,*work,*heap,*image;
    u32 phase,cancel,active,attempt;
} Service;
static Service *service=(void *)-1;
static void lock(void) {FN(0x8150A9C0,void (*)(void *))(service->mutex);}
static void unlock(void) {FN(0x8150AA9C,void (*)(void *))(service->mutex);}
static int live(void) {return service && service!=(void *)-1;}
static int eligible(void *worker) {
    void *cdb=*(void **)0x81089084;
    return cdb && worker==(u8 *)cdb+0x18 && service->work &&
        PTR(worker,0)==service->work && !*((u8 *)cdb+0x14) &&
        FN(0x8135E408,int (*)(void *))(worker)==5;
}
static int cancelled(void) {
    lock();int result=service->cancel;unlock();return result;
}
static void cancel(void) {
    if(live()) {lock();service->cancel=1;unlock();}
}
/* Call site immediately after a Board creates the original SD worker.
 * Only this main-thread callback creates/resets control state. */
void kwce_start_sd(void *cdb) {
    FN(0x8133F624,void (*)(void *))(cdb);
    if(!live()) {
        service=FN(0x815D0A08,void *(*)(u32,int,void *))(
            sizeof(Service),32,*(void **)0x81089014);
        if(!service)return;
        for(u32 i=0;i<sizeof(Service)/4;i++)((u32 *)service)[i]=0;
        FN(0x8150A988,void (*)(void *))(service->mutex);
    }
    lock();
    /* Board::destroy waits for termination before a new Board can be made.
     * Never reset an in-flight request, even if that contract is violated. */
    if(!service->active) {
        service->worker=(u8 *)cdb+0x18;service->work=PTR(service->worker,0);
        service->cancel=0;
        if(service->phase!=READY)service->phase=WAITING;
        service->attempt++;
    }
    unlock();
}
void kwce_board_update(void *board) {
    if(live()) {
        lock();
        if(!service->cancel && service->phase==WAITING &&
           FIELD(board,0)==0 && eligible(service->worker) &&
           !FN(0x8135E38C,int (*)(void *))(service->worker)) {
            service->phase=QUEUED;service->active=1;
            FN(0x8135ED70,void (*)(void *,int))(service->worker,1);
            if(!FN(0x81509E38,int (*)(void *,u32,int))(
                    (u8 *)service->work+0x21490,MESSAGE,0)) {
                service->phase=FAILED;service->active=0;
                FN(0x8135ED70,void (*)(void *,int))(service->worker,0);
            }
        }
        unlock();
    }
    FN(0x81395338,void (*)(void *))(board);
}
extern void kwce_board_calc_original(void *);
extern void kwce_board_destroy_original(void *);
void kwce_board_calc(void *board) {
    u32 state=FIELD(board,0x60);
    if(state==13 || state==14 || state==16)cancel();
    kwce_board_calc_original(board);
}
void kwce_board_destroy(void *board) {
    cancel();
    /* Original code drains/terminates SDVF, then unmounts CDB. */
    kwce_board_destroy_original(board);
}
static int read_one(int index,u8 *dest,u32 size) {
    static const char *const names[3]={
        "?:/kwce/dvd/boot.ash","?:/kwce/dvd/menu.arc","?:/kwce/dvd/icon.arc"};
    char path[24];u32 i=0;
    do {path[i]=names[index][i];} while(path[i++]);
    path[0]=*((char *)service->work+0x1148);
    if(cancelled() || !eligible(service->worker))return 0;
    void *file=FN(0x815C0DA4,void *(*)(const char *,const char *))(path,"r");
    if(!file)return 0;
    int ok=0;
    for(u32 offset=0;offset<size;) {
        if(cancelled() || !eligible(service->worker))goto close;
        u32 n=size-offset;if(n>16384)n=16384;
        if(FN(0x815C0E00,u32 (*)(void *,u32,u32,void *))(dest+offset,1,n,file)!=n)goto close;
        offset+=n;
    }
    u8 extra;
    if(cancelled() || !eligible(service->worker) ||
       FN(0x815C0E00,u32 (*)(void *,u32,u32,void *))(&extra,1,1,file))goto close;
    u8 sha[96] __attribute__((aligned(32))),hash[20];
    FN(0x8146CCCC,void (*)(void *))(sha);
    FN(0x8146CD1C,void (*)(void *,const void *,u32))(sha,dest,size);
    FN(0x8146CDD0,void (*)(void *,void *))(sha,hash);
    ok=1;
    for(u32 i=0;i<20;i++)if(hash[i]!=(asset_hash[index][i]^0xa5))ok=0;
close:
    if(FN(0x815C0D4C,int (*)(void *))(file))ok=0;
    return ok;
}
u32 kwce_sd_wait(void *worker) {
    u32 message=FN(0x8135ECCC,u32 (*)(void *))(worker);
    if(message!=MESSAGE)return message;
    if(!live())return 0;
    lock();
    int valid=service->active && service->phase==QUEUED && worker==service->worker;
    if(valid)service->phase=READING;
    unlock();
    if(!valid)return 0;
    void *heap=*(void **)0x81089030;u8 *image=0;int ok=0;
    /* Keep a contiguous 4 MiB headroom for other Mem2App consumers. Failed
     * admission retains normal menu behavior and does not retry each frame. */
    if(!cancelled() && eligible(worker) && heap &&
       FN(0x815D03BC,u32 (*)(void *,int))(heap,32)>=BUNDLE_SIZE+0x400000) {
        image=FN(0x815D0A08,void *(*)(u32,int,void *))(BUNDLE_SIZE,32,heap);
        if(image) {
            u32 end=FIELD(PTR(heap,0x10),0x1c);
            if((u32)image>=0x90000000 && end<=0x94000000 &&
               end>=BUNDLE_SIZE && (u32)image<=end-BUNDLE_SIZE)
                ok=read_one(0,image,PLAYER_SIZE) &&
                   read_one(1,image+BANNER_OFFSET,BANNER_SIZE) &&
                   read_one(2,image+ICON_OFFSET,ICON_SIZE);
        }
    }
    if(ok) {
        for(u32 i=0;i<sizeof(relocator);i++)image[STAGE_SIZE+i]=relocator[i]^0xa5;
        FN(0x815066EC,void (*)(void *,u32))(image,BUNDLE_SIZE);
        FN(0x815067A4,void (*)(void *,u32))(image+STAGE_SIZE,sizeof(relocator));
    }
    lock();
    if(ok && !service->cancel && eligible(worker)) {
        service->heap=heap;service->image=image;service->phase=READY;service->active=0;
        unlock();
    } else {
        unlock();
        if(image)FN(0x815D0B6C,void (*)(void *,void *))(image,heap);
        lock();service->phase=FAILED;service->active=0;unlock();
    }
    /* Let the original run() perform its stack guard and IDLE transition. */
    return 0;
}
void *kwce_resource(int index) {
    if(!live())return 0;
    lock();u8 *p=service->phase==READY?service->image:0;unlock();
    if(!p || index<0 || index>2)return 0;
    return p+(index==1?BANNER_OFFSET:index==2?ICON_OFFSET:0);
}

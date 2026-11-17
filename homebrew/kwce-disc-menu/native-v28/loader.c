/* 43K RAM-only integration. Generated payload.h pins one reviewed player. */
typedef unsigned int u32;
typedef unsigned char u8;
#define FN(a,t) ((t)(a))
#define FIELD(p,o) (*(u32 *)((u8 *)(p)+(o)))
#define PTR(p,o) (*(void **)((u8 *)(p)+(o)))
#include "payload.h"
#include "icon-payload.h"
extern int kwce_enable_original(void *,int,int);
extern void kwce_reserve_original(void *);
extern int kwce_fade_original(void *);
struct {void *image,*owner; int ready,failed; u32 wait;} loader_ctx = {(void *)-1,(void *)-1,-1,-1,0xffffffff};
__attribute__((section(".text.stub"))) int kwce_loader_debug(void) {return 0;}
static void copy(u8 *d,const u8 *s,u32 n) {while(n--)*d++=*s++^0xa5;}
static int match(const u8 *a,const u8 *b,u32 n) {while(n--)if(*a++!=(*b++^0xa5))return 0;return 1;}
static int dvd(void *s) {
    if(FIELD(s,0x74)!=16)return 0;
    return FN(0x813B1564,int (*)(void *,int,int))(*(void **)0x8108908c,FIELD(s,0x60),FIELD(s,0x64))==15;
}
/* FAT itself serializes its calls. No writes or implicit SD format/mount. */
void *kwce_open(int banner) {
    void *cdb=*(void **)0x81089084;
    if(!cdb)return 0;
    void *worker=(u8 *)cdb+0x18,*work=PTR(worker,0);
    if(!work || FN(0x8135E38C,int (*)(void *))(worker))return 0;
    int state=FN(0x8135E408,int (*)(void *))(worker);
    if(state!=5) {
        if(state==0 || state==2)FN(0x8135E47C,void (*)(void *))(worker);
        return 0;
    }
    char path[sizeof(path_template)];copy((u8 *)path,path_template,sizeof(path_template));
    if(banner) {
        path[12]=banner==2?'i':'m';path[13]=banner==2?'c':'e';path[14]=banner==2?'o':'n';path[15]=banner==2?'n':'u';
        path[17]='a';path[18]='r';path[19]='c';
    }
    path[0]=*((char *)work+0x1148);
    return FN(0x815C0DA4,void *(*)(const char *,const char *))(path,"r");
}
static void close_file(void *f) {FN(0x815C0D4C,int (*)(void *))(f);}
static int prepare(void *s);
extern int kwce_prefetch_banner(void);
int kwce_module_available(void) {
    /* Retain verified resources before ChannelTitle changes SD ownership. */
    return prepare(0) && kwce_prefetch_banner();
}
static int prepare(void *s) {
    if(loader_ctx.image && loader_ctx.image!=(void *)-1) {
        if(s)loader_ctx.owner=s;
        return 1;
    }
    loader_ctx.wait=1;
    void *f=kwce_open(0);if(!f)return 0;
    void *heap=*(void **)0x81089030; /* System::smArg.mpMem2App (+0x28) */
    u8 *image=FN(0x815D0A08,void *(*)(u32,int,void *))(STAGE_SIZE+STACK_SIZE,32,heap);
    loader_ctx.wait=2;
    if(!image) {close_file(f);return 0;}
    loader_ctx.wait=3;
    u32 heap_end=FIELD(PTR(heap,0x10),0x1c);
    if((u32)image<0x90000000 || heap_end>0x94000000 ||
       (u32)image>heap_end-STAGE_SIZE-STACK_SIZE)goto bad;
    u32 n=FN(0x815C0E00,u32 (*)(void *,u32,u32,void *))(image,1,PLAYER_SIZE,f);
    u8 extra;
    u32 tail=FN(0x815C0E00,u32 (*)(void *,u32,u32,void *))(&extra,1,1,f);
    close_file(f);f=0;
    if(n!=PLAYER_SIZE || tail || !match(image,player_header,256))goto bad;
    loader_ctx.wait=4;
    u8 hash[20],sha[96] __attribute__((aligned(32)));
    FN(0x8146CCCC,void (*)(void *))(sha);
    FN(0x8146CD1C,void (*)(void *,const void *,u32))(sha,image,PLAYER_SIZE);
    FN(0x8146CDD0,void (*)(void *,void *))(sha,hash);
    if(!match(hash,player_sha1,20))goto bad;
    loader_ctx.wait=5;
    copy(image+STAGE_SIZE,relocator,sizeof(relocator));
    FN(0x815066EC,void (*)(void *,u32))(image,STAGE_SIZE+STACK_SIZE);
    FN(0x815067A4,void (*)(void *,u32))(image+STAGE_SIZE,sizeof(relocator));
    loader_ctx.image=image;loader_ctx.owner=s;loader_ctx.wait=0;
    return 1;
bad:
    if(f)close_file(f);
    FN(0x815D0B6C,void (*)(void *,void *))(image,heap);return 0;
}
/* Temporary diagnostic: preserve stock Wii/GC dispatch; DVD launch blocked. */
int kwce_enable(void *s,int page,int index) {return dvd(s)?0:kwce_enable_original(s,page,index);}
void kwce_reserve(void *s) {if(!dvd(s))kwce_reserve_original(s);}
int kwce_fade(void *s) {return kwce_fade_original(s);}
void kwce_native_bind_reset(void) {if(loader_ctx.image==(void *)-1)loader_ctx.image=0;loader_ctx.owner=0;loader_ctx.failed=0;loader_ctx.wait=0;loader_ctx.ready=0;}

int kwce_icon_hash(const void *data) {
    u8 sha[96] __attribute__((aligned(32))),hash[20];
    FN(0x8146CCCC,void (*)(void *))(sha);
    FN(0x8146CD1C,void (*)(void *,const void *,u32))(sha,data,ICON_SIZE);
    FN(0x8146CDD0,void (*)(void *,void *))(sha,hash);
    return match(hash,icon_sha1,20);
}

static volatile void *icon_data=(void *)-1;
void *kwce_load_icon(void) {
    if(icon_data==(void *)-1)icon_data=0;
    if(icon_data)return (void *)icon_data;
    void *f=kwce_open(2);if(!f)return 0;
    void *heap=*(void **)0x81089030;
    u8 *data=FN(0x815D0A08,void *(*)(u32,int,void *))(ICON_SIZE,32,heap);
    u32 n=data?FN(0x815C0E00,u32 (*)(void *,u32,u32,void *))(data,1,ICON_SIZE,f):0;
    u8 extra;u32 tail=FN(0x815C0E00,u32 (*)(void *,u32,u32,void *))(&extra,1,1,f);
    FN(0x815C0D4C,int (*)(void *))(f);
    int ok=n==ICON_SIZE && !tail && kwce_icon_hash(data);
    if(!ok){if(data)FN(0x815D0B6C,void (*)(void *,void *))(data,heap);return 0;}
    icon_data=data;return data;
}

/* Hide only the transition-disc pane after the insertion/ejection ends. */
void kwce_disk_anim_visible(void *s,int yes) {
    void *layout=PTR(s,0x9c),*root=layout?PTR(layout,0x14):0;
    if(!root)return;
    u8 *pane=FN(0x814F7E64,void *(*)(void *,const char *,int))(root,"DiskIn",1);
    if(pane) {u8 *flags=pane+0xcf;*flags=(*flags&~1)|(yes!=0);}
}

void visible(void *layout,int yes) {
    if(layout) {void *root=PTR(layout,0x14);if(root) {
        u8 *flags=(u8 *)root+0xcf;*flags=(*flags&~1)|(yes!=0);
    }}
}

void kwce_icon_finish(void *s,void *o,void *layout) {
    if(o && PTR(o,0x40)==layout) {
        FN(0x813B13B8,void (*)(void *))(o);
        FN(0x813B1464,void (*)(void *))(o);
    }
    kwce_disk_anim_visible(s,0);
}
/* Preserve FAAttach's result and its thread-local errno at the failing call,
   before another task or the original logging path can replace it. */
static volatile int attach_error=98;
int kwce_sd_attach(int device,void *path,u32 size,void *table) {
    int r=FN(0x815C09E8,int (*)(int,void *,u32,void *))(device,path,size,table);
    attach_error=r?FN(0x815C0D0C,int (*)(void))():0;
    return r;
}

void kwce_sd_trace(void *s) {
    void *l=*(void **)((u8 *)s+0x254),*root=l?*(void **)((u8 *)l+0x14):0;
    if(!root)return;
    void *pane=FN(0x814F7E64,void *(*)(void *,const char *,int))(root,"T_Bar",1);
    if(!pane)return;
    unsigned short text[]={'S','2','8',' ', '0',' ', 'E','0','0',0};
    text[4]='0'+loader_ctx.wait%10;
    u32 e=attach_error<0?99:(u32)attach_error%100;
    text[7]='0'+e/10;text[8]='0'+e%10;
    FN(0x814FB5F0,void (*)(void *,const unsigned short *,unsigned short))(pane,text,0);
}

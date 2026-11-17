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
static struct {void *image,*owner; int ready,failed; u32 wait;} loader_ctx = {(void *)-1,(void *)-1,-1,-1,0xffffffff};
__attribute__((section(".text.stub"))) int kwce_loader_debug(void) {return 0;}
static volatile u32 trace_io=0;
static void copy(u8 *d,const u8 *s,u32 n) {while(n--)*d++=*s++^0xa5;}
static int match(const u8 *a,const u8 *b,u32 n) {while(n--)if(*a++!=(*b++^0xa5))return 0;return 1;}
static int dvd(void *s) {
    if(FIELD(s,0x74)!=16)return 0;
    return FN(0x813B1564,int (*)(void *,int,int))(*(void **)0x8108908c,FIELD(s,0x60),FIELD(s,0x64))==15;
}
/* FAT itself serializes its calls. No writes or implicit SD format/mount. */
void *kwce_open(int banner) {
    void *cdb=*(void **)0x81089084;
    if(!cdb){trace_io=1;return 0;}
    void *worker=(u8 *)cdb+0x18,*work=PTR(worker,0);
    if(!work){trace_io=2;return 0;}
    if(FN(0x8135E38C,int (*)(void *))(worker)){trace_io=3;return 0;}
    int state=FN(0x8135E408,int (*)(void *))(worker);
    trace_io=10+state;
    /* Preserve the completed mount result before the next request replaces it. */
    if(state==0) {
        int result=FN(0x8135E3B8,int (*)(void *))(worker);
        if(result<0 && result>=-11)trace_io=40-result;
    }
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
    void *f=FN(0x815C0DA4,void *(*)(const char *,const char *))(path,"r");trace_io=f?30:20+banner;return f;
}
static void close_file(void *f) {FN(0x815C0D4C,int (*)(void *))(f);}
int kwce_module_available(void) {
    u8 header[256] __attribute__((aligned(32)));
    void *f=kwce_open(0);if(!f) {loader_ctx.ready=-1;return 0;}
    u32 n=FN(0x815C0E00,u32 (*)(void *,u32,u32,void *))(header,1,256,f);
    close_file(f);
    loader_ctx.ready=n==256 && match(header,player_header,256);trace_io=loader_ctx.ready?32:31;return loader_ctx.ready;
}
/* Diagnostic only: DVD launch disabled; stock Wii/GC dispatch preserved. */
int kwce_enable(void *s,int page,int index) {return dvd(s)?0:kwce_enable_original(s,page,index);}
void kwce_reserve(void *s) {if(!dvd(s))kwce_reserve_original(s);}
int kwce_fade(void *s) {return kwce_fade_original(s);}
void kwce_native_bind_reset(void) {loader_ctx.ready=0;}
void kwce_trace(void *s,int active,int stage) {
    void *layout=PTR(s,0x254),*root=layout?PTR(layout,0x14):0;
    if(!root)return;
    void *pane=FN(0x814F7E64,void *(*)(void *,const char *,int))(root,"T_Bar",1);
    if(!pane)return;
    void *b=*(void **)0x810890b0;
    u32 vals[5]={b?FIELD(b,4):0,FIELD(s,0x74),active,stage,trace_io};
    unsigned short text[20];text[0]='D';text[1]='V';text[2]='D';text[3]=' ';
    for(int i=0;i<5;i++){u32 v=vals[i]%100;text[4+3*i]='0'+v/10;text[5+3*i]='0'+v%10;text[6+3*i]=' ';}
    text[19]=0;
    FN(0x814FB5F0,void (*)(void *,const unsigned short *,unsigned short))(pane,text,0);
}

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


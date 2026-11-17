/* Read a pinned, local banner archive into ordinary SDK-owned objects.
 * No title lookup and no NAND file operations. Native destructors own the
 * archive, File and LayoutFile after they are attached to ChannelTitle.
 */
typedef unsigned int u32;
typedef unsigned char u8;
#define FN(a,t) ((t)(a))
#define FIELD(p,o) (*(u32 *)((u8 *)(p)+(o)))
extern void *kwce_open(int);
#include "banner-payload.h"
static void release(void *p,void *heap) {if(p)FN(0x815D0B6C,void (*)(void *,void *))(p,heap);}
/* Korean stock resources hide these two panes. Apply only to the active
   three-disc DVD layout; this modifies the loaded layout in memory. */
__attribute__((section(".panevis"),noinline))
static void show_group(void *group) {
    u8 *end=(u8 *)group+0x10,*node=*(u8 **)end;
    for(int j=0;node && node!=end && j<16;j++,node=*(u8 **)node) {
        u8 *pane=*(u8 **)(node+8);if(pane)pane[0xcf]|=1;
    }
}
void *kwce_prepare_discs(void *layout) {
    void *groups=*(void **)((u8 *)layout+0x18),*dvd=0;
    if(!groups)return 0;
    const char *names[]={"G_DVD","G_GC"};
    for(int i=0;i<2;i++) {
        void *group=FN(0x814F8BF4,void *(*)(void *,const char *))(groups,names[i]);
        if(!group)continue;
        if(i==0)dvd=group;
        show_group(group);
    }
    return dvd;
}
static void *banner_cache=(void *)-1;
int kwce_prefetch_banner(void) {
    if(banner_cache==(void *)-1)banner_cache=0;
    if(banner_cache)return 1;
    void *heap=*(void **)0x81089030,*f=kwce_open(1);
    if(!f)return 0;
    u8 *data=FN(0x815D0A08,void *(*)(u32,int,void *))(BANNER_SIZE,32,heap);
    u32 n=data?FN(0x815C0E00,u32 (*)(void *,u32,u32,void *))(data,1,BANNER_SIZE,f):0;
    u8 extra;
    u32 tail=FN(0x815C0E00,u32 (*)(void *,u32,u32,void *))(&extra,1,1,f);
    FN(0x815C0D4C,int (*)(void *))(f);
    if(n!=BANNER_SIZE || tail) {release(data,heap);return 0;}
    u8 sha[96] __attribute__((aligned(32))),hash[20];
    FN(0x8146CCCC,void (*)(void *))(sha);
    FN(0x8146CD1C,void (*)(void *,const void *,u32))(sha,data,BANNER_SIZE);
    FN(0x8146CDD0,void (*)(void *,void *))(sha,hash);
    for(int i=0;i<20;i++)if(hash[i]!=(banner_sha1[i]^0xa5)) {release(data,heap);return 0;}
    banner_cache=data;
    return 1;
}
void *kwce_load_banner(void) {
    if(!kwce_prefetch_banner())return 0;
    void *heap=*(void **)0x81089030;
    u8 *data=FN(0x815D0A08,void *(*)(u32,int,void *))(BANNER_SIZE,32,heap);
    if(!data)return 0;
    /* The stock destructor owns this copy, never the retained archive. */
    for(u32 i=0;i<BANNER_SIZE;i++)data[i]=((const u8 *)banner_cache)[i];
    void *file=FN(0x815D0A08,void *(*)(u32,int,void *))(0x190,32,heap);
    void *layout=FN(0x815D0A08,void *(*)(u32,int,void *))(0x0c,32,heap);
    if(!file || !layout) {release(file,heap);release(layout,heap);release(data,heap);return 0;}
    for(int i=0;i<0x190;i+=4)FIELD(file,i)=0;
    FIELD(file,0)=0x8160cf08;FIELD(file,4)=(u32)heap;
    FIELD(file,0x98)=BANNER_SIZE;*((u8 *)file+0x9c)=1;
    FIELD(file,0xa0)=(u32)data;FIELD(file,0xa8)=1;FIELD(file,0xac)=1;
    FIELD(layout,0)=0x8160cec8;FIELD(layout,4)=(u32)file;FIELD(layout,8)=0;
    return layout;
}

/* The stock FA SD driver can fail before mounting when the card has not
   completed IOS initialization. Probe/reset only after EIO, then retry once.
   ISD_ProbeCard closes its temporary handle on every completed branch. */
int kwce_sd_attach(int device,void *path,u32 size,void *table) {
    int r=FN(0x815C09E8,int (*)(int,void *,u32,void *))(device,path,size,table);
    if(r && FN(0x815C0D0C,int (*)(void))()==5 &&
       FN(0x815C7638,int (*)(u32))(0)==0)
        r=FN(0x815C09E8,int (*)(int,void *,u32,void *))(0,0,0,table);
    return r;
}

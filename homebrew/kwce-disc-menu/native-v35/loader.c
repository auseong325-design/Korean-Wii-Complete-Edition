typedef unsigned int u32;
typedef unsigned char u8;
#define FN(a,t) ((t)(a))
#define FIELD(p,o) (*(u32 *)((u8 *)(p)+(o)))
#define PTR(p,o) (*(void **)((u8 *)(p)+(o)))
#include "sizes.h"
extern int kwce_enable_original(void *,int,int);
extern void kwce_reserve_original(void *);
extern int kwce_fade_original(void *);
extern void *kwce_resource(int);
static void *launch_owner=(void *)-1;
static int dvd(void *s) {
    return FIELD(s,0x74)==16 &&
        FN(0x813B1564,int (*)(void *,int,int))(*(void **)0x8108908c,FIELD(s,0x60),FIELD(s,0x64))==15;
}
int kwce_module_available(void) {return kwce_resource(0)!=0;}
void *kwce_load_icon(void) {return kwce_resource(2);}
int kwce_enable(void *s,int page,int index) {
    return dvd(s)?kwce_module_available():kwce_enable_original(s,page,index);
}
void kwce_reserve(void *s) {
    if(!dvd(s)) {kwce_reserve_original(s);return;}
    if(!kwce_module_available()) {FN(0x813B8ED0,void (*)(void *))(s);return;}
    launch_owner=s;
    FN(0x813B8BB8,void (*)(void *,int))(s,15);
    FIELD(s,0x6c)=15;FIELD(s,0x360)=0;FIELD(s,0x58)=4;
}
int kwce_fade(void *s) {
    int result=kwce_fade_original(s);
    if(launch_owner!=s)return result;
    u32 image=(u32)kwce_resource(0);if(!image)return result;
    if(result!=1 || FN(0x81552564,int (*)(void))()!=0 ||
       !FN(0x813332D0,int (*)(void))() || FN(0x815410FC,int (*)(void))()==1)return 0;
    /* Unchanged reviewed R51 handoff: SDK shutdown before MEM1 relocation.
     * Resources are already resident; no FA access during scene fade. */
    FN(0x8151D16C,void (*)(void))();
    FN(0x81516EE0,void (*)(int))(1);FN(0x81516D58,void (*)(void))();
    FN(0x8150B050,void (*)(u32))(6);
    u32 stack=image+STAGE_SIZE+STACK_SIZE-32,target=image+STAGE_SIZE;
    __asm__ volatile("mr 1,%0; mr 3,%1; mtctr %2; bctr"::"r"(stack),"r"(image),"r"(target):"memory");
    __builtin_unreachable();
}
void kwce_native_bind_reset(void) {launch_owner=0;}
void kwce_disk_anim_visible(void *s,int yes) {
    void *layout=PTR(s,0x9c),*root=layout?PTR(layout,0x14):0;
    if(root) {
        u8 *pane=FN(0x814F7E64,void *(*)(void *,const char *,int))(root,"DiskIn",1);
        if(pane)pane[0xcf]=(pane[0xcf]&~1)|(yes!=0);
    }
}
void visible(void *layout,int yes) {
    if(layout && PTR(layout,0x14)) {
        u8 *flags=(u8 *)PTR(layout,0x14)+0xcf;*flags=(*flags&~1)|(yes!=0);
    }
}
void kwce_icon_finish(void *s,void *o,void *layout) {
    if(o && PTR(o,0x40)==layout) {
        FN(0x813B13B8,void (*)(void *))(o);FN(0x813B1464,void (*)(void *))(o);
    }
    kwce_disk_anim_visible(s,0);
}

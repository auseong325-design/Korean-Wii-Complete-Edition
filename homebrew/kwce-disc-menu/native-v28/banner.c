/* 43K only. Native animator binding/state transitions, no pane/matrix copying.
 * Called at ordinary call sites; the compiler supplies complete EABI frames.
 * Unused ALL-group slots 1..5 belong to DVD; native layout owns the animators.
 */
typedef unsigned int u32;
typedef unsigned char u8;
#define FIELD(p,o) (*(u32 *)((u8 *)(p)+(o)))
#define PTR(p,o) (*(void **)((u8 *)(p)+(o)))
#define FN(a,t) ((t)(a))
extern int kwce_module_available(void);
extern void kwce_sd_trace(void *);
extern void *kwce_open(int);
extern int kwce_icon_hash(const void *);
#include "icon-payload.h"
extern void kwce_native_bind_reset(void);
extern void *kwce_load_banner(void);
extern void *kwce_prepare_discs(void *);
static volatile unsigned int cached_disc = 0xffffffff;
static volatile struct { void *owner,*file; int active,failed; u32 ticks,stage; } banner_ctx = {(void *)-1,(void *)-1,-1,-1,0xffffffff,0xffffffff};
__attribute__((section(".text.stub"))) int kwce_unused_debug(void) {return 0;}
static void *anim(void *s,int group,int index) { return PTR(s,0x258+40*group+4*index); }
__attribute__((section(".aux"),noinline)) static void stop(void *a) { if(a) FIELD(a,0x14)=0; }
__attribute__((section(".aux"),noinline)) static int playing(void *a) { return a && FIELD(a,0x14)==1; }
__attribute__((section(".auxnative"),noinline)) static void play(void *a) {
    if(a) { FN(0x81368FB8,void (*)(void *))(a); FIELD(a,0x14)=1; }
}
extern void visible(void *,int);
static int drive(void) { void *b=*(void **)0x810890b0;return b?FIELD(b,4):0; }
static void start_button(void *s) { FN(0x813B8ED0,void (*)(void *))(s); }
static int finished(void *f) { return f && FN(0x8133BA54,int (*)(void *))(f); }
static void native_update(void *s,int page,int index) { FN(0x813B7A00,void (*)(void *,int,int))(s,page,index); }

void kwce_bind(void *s) {
    FN(0x813B78B0,void (*)(void *))(s);
    kwce_native_bind_reset();
    banner_ctx.owner=s;banner_ctx.file=0;banner_ctx.active=0;banner_ctx.failed=0;banner_ctx.ticks=0;banner_ctx.stage=0;
    void *layout=PTR(s,0x254);
    if(!layout || !PTR(layout,0x18))return;
    void *group=kwce_prepare_discs(layout);
    if(!group)return; /* Older resources fall back to the proven launch hook. */
    static const char *const names[]={
        (const char *)0x8162387e,(const char *)0x8162389c,(const char *)0x816238b9,
        (const char *)0x816238d5,(const char *)0x816238f2
    };
    for(int i=0;i<5;i++) {
        void *a=FN(0x813698D4,void *(*)(void *,const char *,void *,int,int))(layout,names[i],group,0,0);
        PTR(s,0x2fc+4*i)=a;
        if(!a)return;
    }
    FIELD(anim(s,4,2),0x18)=2; /* original loop type */
    banner_ctx.active=1;
    if(cached_disc==1 && drive()==7 && kwce_module_available())visible(layout,0);
}

static void forget(void) {banner_ctx.file=0;banner_ctx.stage=0;}
static void discard(void *s) {
    u32 at=4*FIELD(s,0x218);
    void *layout=PTR(s,0x23c);
    if(layout && layout!=PTR(s,0x254))FN(0x8136A194,void (*)(void *))(layout);
    PTR(s,0x23c)=0;PTR(s,0x240)=0;PTR(s,0x244)=0;PTR(s,0x248)=0;
    if(banner_ctx.file)FN(0x8133BB18,void (*)(void *,int))((void *)banner_ctx.file,1);
    void *sound=PTR(s,0x22c+at);
    if(sound)FN(0x8133A94C,void (*)(void *,int))(sound,1);
    PTR(s,0x21c+at)=PTR(s,0x250);PTR(s,0x224+at)=0;PTR(s,0x22c+at)=0;PTR(s,0x234+at)=0;
    forget();
}
static void original_disc(void *s,int error) {
    discard(s);
    for(int i=1;i<=5;i++)stop(anim(s,4,i));
    FN(0x813B55BC,void (*)(void *))(s);
    visible(PTR(s,0x254),1);
    FIELD(s,0x74)=error?15:0;FIELD(s,0x78)=error?0:14;
    if(error) {banner_ctx.failed=1;play(anim(s,4,7));}
    start_button(s);
}
static int begin_banner(void *s) {
    void *file=kwce_load_banner();if(!file)return 0;
    u32 at=4*FIELD(s,0x218);banner_ctx.file=file;
    PTR(s,0x21c+at)=file;PTR(s,0x224+at)=0;PTR(s,0x22c+at)=0;PTR(s,0x234+at)=0;
    FN(0x813B57A8,void (*)(void *))(s);
    if(!PTR(s,0x23c))return 0;
    FN(0x813699C8,void (*)(void *))(PTR(s,0x23c));
    if(PTR(s,0x244))play(PTR(s,0x244));
    else if(PTR(s,0x248))play(PTR(s,0x248));
    else if(PTR(s,0x240))play(PTR(s,0x240));
    visible(PTR(s,0x254),0);
    FIELD(s,0x74)=16;FIELD(s,0x8c)=0;banner_ctx.stage=2;cached_disc=1;start_button(s);return 1;
}

void kwce_update(void *s,int page,int index) {
    kwce_sd_trace(s);
    int state=FIELD(s,0x74),d=drive();
    if(d!=7)cached_disc=0;
    if(banner_ctx.owner!=s || !banner_ctx.active) {native_update(s,page,index);return;}
    banner_ctx.ticks++;
    /* Native channel changes own/free the old buffers; never dereference them. */
    if(banner_ctx.file && PTR(s,0x21c+4*FIELD(s,0x218))!=banner_ctx.file)forget();
    if((state>=18 && state<=20) || (state==16 && banner_ctx.file)) {
        if(d!=7) {
            if(banner_ctx.file && !finished((void *)banner_ctx.file))return;
            original_disc(s,0);native_update(s,page,index);return;
        }
        if(state==18) {
            if(!playing(anim(s,1,4)) && !playing(anim(s,2,4))) {
                stop(anim(s,4,2));play(anim(s,4,5));play(anim(s,3,5));
                FIELD(s,0x74)=19;banner_ctx.stage=3;
            }
        } else if(state==19) {
            if(!playing(anim(s,4,5)) && !playing(anim(s,3,5))) {
                if(!begin_banner(s))original_disc(s,1);
            }
        }
        return;
    }
    /* The already recognized disc remains present across scene changes.
       Reload the banner as soon as the new scene is idle, without replaying
       the first-insertion disc choreography. Removal clears the marker. */
    if((state==0 || state==1 || state==2 || state==6 || state==7) && d==7 && cached_disc==1 &&
       !banner_ctx.failed && kwce_module_available()) {
        for(int group=1;group<=4;group++)
            for(int index=1;index<=5;index++)stop(anim(s,group,index));
        if(!begin_banner(s))original_disc(s,1);
        return;
    }
    /* SD initialization is asynchronous. Keep the spinning state until the
       module header is available, otherwise the stock invalid-disc animation
       can begin before we switch to the DVD animation. Bound the wait so a
       missing SD/module eventually uses the normal unreadable-disc path. */
    if(state==7 && d==7 && !banner_ctx.failed && !kwce_module_available()) {
        if(banner_ctx.stage!=5) {banner_ctx.stage=5;banner_ctx.ticks=0;}
        if(banner_ctx.ticks<300)return;
        banner_ctx.failed=1;banner_ctx.stage=0;
    }
    if((state==7 || (state==16 && banner_ctx.stage==0)) && d==7 && !banner_ctx.failed && kwce_module_available()) {
        stop(anim(s,4,7));stop(anim(s,4,8));
        stop(anim(s,1,2));stop(anim(s,2,2));
        play(anim(s,1,4));play(anim(s,2,4));
        FIELD(s,0x74)=18;FIELD(s,0x78)=0;banner_ctx.stage=4;return;
    }
    native_update(s,page,index);
    int now=FIELD(s,0x74);
    if(cached_disc==1 && d==7 && (now==0 || now==1))visible(PTR(s,0x254),0);
    if(state==2 && now==6)play(anim(s,4,1));
    else if(state==6 && now==7)play(anim(s,4,2));
    else if(state==7 && now==9) {stop(anim(s,4,2));play(anim(s,4,4));}
    else if(state==7 && now==8) {stop(anim(s,4,2));play(anim(s,4,3));}
}

/* Thumbnail code runs only from ChannelSelect's per-frame call site. The
   image is immutable and retained once for the lifetime of the menu. */
static volatile void *icon_owner=(void *)-1,*icon_layout=(void *)-1;
static volatile int icon_phase=-1; /* 0 idle, 1 disc entering, 2 ejecting, 3 DVD shown */
extern void *kwce_load_icon(void);
extern void kwce_disk_anim_visible(void *,int);
extern void kwce_icon_finish(void *,void *,void *);
void kwce_select_update(void *s) {
    int d=drive();void *o=PTR(s,0x90),*fade=PTR(s,0x8c),*in=PTR(s,0xa0),*out=PTR(s,0xa4);
    if(d!=7)cached_disc=0;
    if(icon_owner!=s) {icon_owner=s;icon_layout=0;icon_phase=0;}
    if(icon_layout && (!o || PTR(o,0x40)!=icon_layout)) {icon_layout=0;icon_phase=0;}
    if(icon_phase==2) {
        if(playing(fade) || playing(out))return;
        kwce_icon_finish(s,o,(void *)icon_layout);icon_layout=0;icon_phase=0;
    }
    if(icon_phase==1 || icon_phase==3) {
        if(d!=7) {
            kwce_disk_anim_visible(s,1);
            FN(0x813AC680,void (*)(void *))(s);
            if(o)FN(0x813B1408,void (*)(void *))(o);
            icon_phase=2;return;
        }
        if(icon_phase==1 && !playing(in)) {
            /* Keep the stock insertion disc at its final, partially inserted position. */
            icon_phase=3;
        }
        return;
    }
    if(d==7 && o && in && out && FIELD(s,0xf0)==0 && !playing(out) && !PTR(o,0x40) && kwce_module_available()) {
        void *data=kwce_load_icon();
        if(data) {
            FN(0x813B12D8,void (*)(void *,void *))(o,data);
            icon_layout=PTR(o,0x40);
            if(icon_layout) {
                kwce_disk_anim_visible(s,1);
                FN(0x813AC620,void (*)(void *))(s);
                icon_phase=1;return;
            }
        }
    }
    FN(0x813AC288,void (*)(void *))(s);
}

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
void *kwce_load_banner(void) {
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

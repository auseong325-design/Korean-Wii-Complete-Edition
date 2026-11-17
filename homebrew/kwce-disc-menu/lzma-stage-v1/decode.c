/* Experimental fixed-address decoder. No SDK heap, device or NAND access.
 * LZMA SDK implementation remains in the pinned, unmodified vendor tree.
 * The caller authenticates the entire package before shutting down the SDK.
 */
#include "LzmaDec.h"
#include <stddef.h>
typedef unsigned int u32;
typedef unsigned char u8;
typedef struct { ISzAlloc api; u8 *arena; int used; } Arena;
static void *take(ISzAllocPtr api, size_t size) {
    Arena *a=(Arena *)api;
    if(a->used || size>16384)return 0;
    a->used=1;return a->arena;
}
static void give(ISzAllocPtr api,void *p) {(void)api;(void)p;}
static u32 be32(const u8 *p) {
    return ((u32)p[0]<<24)|((u32)p[1]<<16)|((u32)p[2]<<8)|p[3];
}
__attribute__((section(".entry")))
int kwce_decode(const u8 *package,u32 package_size,u8 *output,u32 capacity) {
    if(package_size<32 || be32(package)!=0x4b574c31)return 0;
    u32 raw=be32(package+4),offset=be32(package+8),size=be32(package+12);
    if(!raw || raw>capacity || offset<32 || offset>package_size ||
       size<13 || size!=package_size-offset)return 0;
    const u8 *src=package+offset;
    /* Fixed lc=3, lp=0, pb=2: bounded probability arena. */
    if(src[0]!=0x5d)return 0;
    u8 arena[16384] __attribute__((aligned(32)));
    Arena a={{take,give},arena,0};
    SizeT out=raw,in=size-13;ELzmaStatus status;
    int result=LzmaDecode(output,&out,src+13,&in,src,5,
                          LZMA_FINISH_END,&status,&a.api);
    return result==SZ_OK && status==LZMA_STATUS_FINISHED_WITH_MARK &&
           out==raw && in==size-13;
}
#ifndef KWCE_HOST_TEST
void *memcpy(void *d,const void *s,size_t n) {
    u8 *a=d;const u8 *b=s;for(size_t i=0;i<n;i++)a[i]=b[i];return d;
}
void *memset(void *d,int v,size_t n) {
    u8 *a=d;for(size_t i=0;i<n;i++)a[i]=(u8)v;return d;
}
#endif

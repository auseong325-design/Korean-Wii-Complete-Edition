/* HOME uses MPlayer's DMA callback, never a competing ASND engine.
 * Immutable native UI samples are mixed in the IRQ: no I/O, allocation or GX.
 * Movie buffers remain queued while HOME owns the paused audio output. */
#include "kwce_sound.h"
#include <string.h>
static const u8 *pack;
static u32 packSize;
static volatile int menuActive,nativeActive;
static const s16 *voice;
static u32 frames;
static u64 position;
static int outputRate=48000;
static u8 mix[2][4096] ATTRIBUTE_ALIGN(32);
static int buffer;
static u32 word(const u8 *p) { return (p[0]<<24)|(p[1]<<16)|(p[2]<<8)|p[3]; }
void KwceSoundLoad(const u8 *p,u32 n) {
    if(!p || n<16+22*16 || memcmp(p,"KWFX",4) || word(p+4)!=1 || word(p+8)!=22) return;
    for(int i=0;i<22;i++) { const u8 *r=p+16+i*16;u32 o=word(r),f=word(r+4);
        if(o>n || f>(n-o)/4 || word(r+8)!=32000 || o%4) return; }
    pack=p;packSize=n;
}
int KwceSoundOwnsAudio(void) { return menuActive; }
void KwceSoundNative(int rate,int active) { u32 level=IRQ_Disable();nativeActive=active;outputRate=rate;
    IRQ_Restore(level); }
int KwceSoundDma(const void *base,int rate) {
    if(!menuActive && !voice) return 0;
    s16 *dst=(s16 *)mix[buffer^=1];
    if(base && !menuActive)memcpy(dst,base,4096);else memset(dst,0,4096);
    u32 inc=(32000u<<16)/(rate==32000?32000:48000);
    for(int i=0;i<1024 && voice;i++) {
        u32 at=position>>16;
        if(at>=frames){voice=0;break;}
        for(int c=0;c<2;c++) {int s=dst[i*2+c]+voice[at*2+c];dst[i*2+c]=s>32767?32767:s<-32768?-32768:s;}
        position+=inc;
    }
    DCFlushRange(dst,4096);AUDIO_InitDMA((u32)dst,4096);return 1;
}
static void fallback() {
    if(nativeActive)return;
    if(!KwceSoundDma(0,outputRate))AUDIO_StopDMA();
}
static void start_fallback() {
    if(nativeActive)return;
    AUDIO_StopDMA();outputRate=48000;AUDIO_SetDSPSampleRate(AI_SAMPLERATE_48KHZ);
    AUDIO_RegisterDMACallback(fallback);KwceSoundDma(0,48000);AUDIO_StartDMA();
}
void KwceSoundPlay(int id) {
    if(!pack || id<0 || id>=22)return;
    const u8 *r=pack+16+id*16;u32 o=word(r),f=word(r+4);
    if(o>packSize || f>(packSize-o)/4)return;
    u32 level=IRQ_Disable();voice=(const s16 *)(pack+o);frames=f;position=0;
    if(!nativeActive && !AUDIO_GetDMAEnableFlag())start_fallback();IRQ_Restore(level);
}
void KwceSoundMenu(int active) {
    u32 level=IRQ_Disable();menuActive=active;
    if(active && !nativeActive)start_fallback();IRQ_Restore(level);
}

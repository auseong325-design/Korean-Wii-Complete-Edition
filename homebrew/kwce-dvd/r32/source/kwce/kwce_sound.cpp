/* HOME uses MPlayer's DMA callback, never a competing ASND engine.
 * Immutable native UI samples are mixed in the IRQ: no I/O, allocation or GX.
 * Movie buffers remain queued while HOME owns the paused audio output. */
#include "kwce_sound.h"
#include <string.h>
static const u8 *pack;
static u32 packSize;
static volatile int menuActive,nativeActive;
/* Short effects can overlap: a hover must not cut off the previous button sound. */
static const int MAX_VOICES=6;
struct Voice { const s16 *samples; u32 frames; u64 position; u32 serial; };
static Voice voices[MAX_VOICES];
static u32 nextSerial;
static bool has_voice() { for(int v=0;v<MAX_VOICES;v++) if(voices[v].samples)return true; return false; }
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
    if(!menuActive && !has_voice()) return 0;
    s16 *dst=(s16 *)mix[buffer^=1];
    if(base && !menuActive)memcpy(dst,base,4096);else memset(dst,0,4096);
    u32 inc=(32000u<<16)/(rate==32000?32000:48000);
    for(int i=0;i<1024;i++) {
        int sample[2]={dst[i*2],dst[i*2+1]};
        for(int v=0;v<MAX_VOICES;v++) {
            Voice &voice=voices[v];
            if(!voice.samples)continue;
            u32 at=voice.position>>16;
            if(at>=voice.frames){voice.samples=0;continue;}
            sample[0]+=voice.samples[at*2];sample[1]+=voice.samples[at*2+1];
            voice.position+=inc;
        }
        for(int c=0;c<2;c++)dst[i*2+c]=sample[c]>32767?32767:sample[c]<-32768?-32768:sample[c];
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
    u32 level=IRQ_Disable();
    int slot=0;
    for(int v=0;v<MAX_VOICES;v++) {
        if(!voices[v].samples){slot=v;break;}
        if(voices[v].serial<voices[slot].serial)slot=v;
    }
    voices[slot].samples=(const s16 *)(pack+o);voices[slot].frames=f;
    voices[slot].position=0;voices[slot].serial=++nextSerial;
    if(!nativeActive && !AUDIO_GetDMAEnableFlag())start_fallback();
    IRQ_Restore(level);
}
void KwceSoundMenu(int active) {
    u32 level=IRQ_Disable();menuActive=active;
    if(active && !nativeActive)start_fallback();
    else if(active && !AUDIO_GetDMAEnableFlag()){KwceSoundDma(0,outputRate);AUDIO_StartDMA();}
    IRQ_Restore(level);
}

#ifndef KWCE_SOUND_H
#define KWCE_SOUND_H
#include <gccore.h>
#ifdef __cplusplus
extern "C" {
#endif
void KwceSoundLoad(const u8 *data,u32 size);
void KwceSoundPlay(int id);
void KwceSoundMenu(int active);
void KwceSoundNative(int rate,int active);
int KwceSoundOwnsAudio(void);
int KwceSoundDma(const void *base,int rate);
#ifdef __cplusplus
}
#endif
#endif

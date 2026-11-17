/* KWCE DVD player: Wii system font (RFNA wbf1) glyph source for FreeTypeGX.
 *
 * The font file is not part of this source tree. On a console it is read from
 * the player channel's own content (a copy of the 43K Korean shared font);
 * the emulator DOL test bed reads it from the test SD.
 */
#ifndef KWCE_FONT_H
#define KWCE_FONT_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
	uint8_t *buffer;   /* 8-bit coverage, pitch == width */
	int width, rows;
	int left, top;     /* bearing from pen position / baseline (pixels) */
	int advance;       /* pen advance (pixels) */
} KwceGlyph;

/* Takes ownership of a malloc'd RFNA (or U8 containing wbf1.brfna) buffer. */
bool KwceFontLoad(uint8_t *data, uint32_t size);
bool KwceFontReady(void);
/* Font metrics scaled to a pixel size (Wii semantics: size / FINF height). */
void KwceFontMetrics(int pixelSize, int *ascent, int *descent);
/* Renders one character; returns false if the font has no glyph for it. */
bool KwceFontGlyph(uint32_t code, int pixelSize, KwceGlyph *out);
void KwceFontFreeGlyph(KwceGlyph *glyph);
/* The loaded RFNA file itself (inside the buffer given to KwceFontLoad), for the layout engine. */
const uint8_t *KwceFontFile(uint32_t *len);

#ifdef __cplusplus
}
#endif

#endif

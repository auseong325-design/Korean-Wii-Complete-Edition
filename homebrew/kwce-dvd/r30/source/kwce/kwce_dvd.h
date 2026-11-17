/* KWCE DVD player: startup integration for the WiiMC fork. */
#ifndef KWCE_DVD_H
#define KWCE_DVD_H

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Set by the no-CSS libdvdcss build when a scrambled sector is read. */
extern volatile int kwce_css_scrambled;

#ifdef __cplusplus
}

/* appPath fallback: sd1:/kwce/dvd (created when an SD card is present). */
void KwceDvdSetupPaths();
/* Loads the Wii system font: player channel content, else <appPath>/wbf1.brfna. */
bool KwceDvdLoadFont();
/* Emulator test bed only: <appPath>/test-disc.iso is played like a DVD. */
bool KwceDvdTestDisc(char *path, unsigned size);
/* Korean UI strings (UTF-8). */
namespace kwce {
	extern const char *msgNoDisc, *msgNoAccess, *msgUnsupportedDrive, *msgNotVideo, *msgCss, *msgLoading;
}
#endif

#endif

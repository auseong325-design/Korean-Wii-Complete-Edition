/* KWCE DVD player: the Wii HOME Menu during DVD playback.
 *
 * Renders the System Menu's own HOME Menu layout (th_HomeBtn_d with the DVD
 * buttons added by kwce/dvd_home_ui.py) with the ported layout engine in
 * lyt/, plays its original animations, and draws the Wii cursor (P1..P4_Def).
 * Buttons: 타이틀 메뉴 (DVD title menu), DVD 메뉴 (root menu), 정지 (stop dialog:
 * 처음부터 재생 / Wii 메뉴로), Wii 메뉴로 (confirm dialog, then exit).
 * All functions run in the MPlayer draw thread (DrawMPlayerGui).
 */
#ifndef KWCE_HOME_H
#define KWCE_HOME_H

#include <stdbool.h>

/* Loads the UI archive: player channel content 3, else <appPath>/home.arc. */
bool KwceHomeLoad();
bool KwceHomeReady();
/* true while the HOME Menu is on screen (input and drawing belong to it). */
bool KwceHomeActive();
/* HOME pressed during playback. */
void KwceHomeOpen();
/* Per frame while active: reads userInput[], advances animations. */
void KwceHomeInput();
/* Per frame while active, after ResetVideo_Menu(): draws menu and cursors. */
void KwceHomeDraw();
/* Wii cursor for remote `chan` at screen position (x, y), rotated by `angle` degrees. */
void KwceCursorDraw(int chan, float x, float y, float angle);

#endif

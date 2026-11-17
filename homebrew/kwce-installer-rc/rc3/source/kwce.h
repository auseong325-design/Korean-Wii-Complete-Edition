#ifndef KWCE_H
#define KWCE_H

void say(const char *fmt, ...);
int confirm(const char *what);
void wait_any(void);

typedef enum { CONSOLE_UNKNOWN = 0, CONSOLE_RVL001, CONSOLE_RVL101, CONSOLE_VWII } console_model;

console_model read_console_model(void);
const char *console_model_name(console_model model);
int console_supports_gamecube(console_model model);

/* Read-only WiiConnect24 status snapshot to SD (wc24report.c). Returns 0 when saved. */
int wc24_report(console_model model, const char *version);

/* wiilink.c: 1 = WiiLink mail/download settings present, 0 = not, -1 = unreadable (read only). */
int wiilink_state(void);
/* Offers the bundled WiiLink Mail Patcher (SD copy only); does nothing when WiiLink is detected.
   startup=1 stays silent when the user skipped before. */
void wiilink_setup(int startup);

#endif

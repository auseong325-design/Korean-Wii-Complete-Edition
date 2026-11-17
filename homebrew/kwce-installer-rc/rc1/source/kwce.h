#ifndef KWCE_H
#define KWCE_H

void say(const char *fmt, ...);
int confirm(const char *what);
void wait_any(void);

typedef enum { CONSOLE_UNKNOWN = 0, CONSOLE_RVL001, CONSOLE_RVL101, CONSOLE_VWII } console_model;

console_model read_console_model(void);
const char *console_model_name(console_model model);
int console_supports_gamecube(console_model model);

#endif

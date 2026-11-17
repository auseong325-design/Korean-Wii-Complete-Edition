#ifndef KWCE_H
#define KWCE_H

void say(const char *fmt, ...);
int confirm(const char *what);
void wait_any(void);

int menu_available(void);
const char *menu_state(void);
void menu_install(void);
void menu_restore(void);

#endif
